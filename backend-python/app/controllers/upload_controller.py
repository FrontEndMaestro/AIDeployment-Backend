from fastapi import UploadFile, HTTPException
from datetime import datetime
from bson import ObjectId
import os
import shutil
from ..config.database import get_projects_collection
from ..config.settings import settings
from ..schemas.project import format_file_size


async def upload_file_handler(file: UploadFile, project_name: str = None, current_user: dict = None):
    try:
        # Validate file type
        allowed_extensions = ['.zip', '.tar', '.gz', '.tgz']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Only {', '.join(allowed_extensions)} allowed"
            )
        
        # Use user's workspace folder
        user_workspace = current_user.get("workspace_path", os.path.join(settings.UPLOAD_DIR, f"user_{current_user['username']}"))
        os.makedirs(user_workspace, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}-{file.filename}"
        file_path = os.path.join(user_workspace, unique_filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(file_path)
        
        # Prepare project data
        project_data = {
            "user_id": str(current_user["_id"]),
            "username": current_user["username"],
            "project_name": project_name or file.filename.rsplit('.', 1)[0],
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "upload_date": datetime.now(),
            "status": "uploaded",
            "extracted_path": None,
            "extraction_date": None,
            "files_count": 0,
            "folders_count": 0,
            "extraction_logs": [],
            "metadata": {
                "framework": "Unknown",
                "language": "Unknown",
                "runtime": None,
                "dependencies": [],
                "port": None,
                "build_command": None,
                "start_command": None,
                "env_variables": [],
                "dockerfile": False,
                "docker_compose": False,
                "detected_files": []
            },
            "analysis_date": None,
            "analysis_logs": [],
            "logs": [{"message": "File uploaded successfully", "timestamp": datetime.now()}],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # Save to database
        collection = get_projects_collection()
        result = await collection.insert_one(project_data)
        
        print(f"✅ File uploaded: {file.filename} ({format_file_size(file_size)})")
        
        return {
            "success": True,
            "message": "File uploaded successfully! ✅",
            "data": {
                "project_id": str(result.inserted_id),
                "project_name": project_data["project_name"],
                "file_name": file.filename,
                "file_size": format_file_size(file_size),
                "upload_date": project_data["upload_date"]
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        # Cleanup file if database save fails
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"❌ Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


async def get_all_projects(current_user: dict):
    try:
        collection = get_projects_collection()
        # Filter projects by current user
        projects = await collection.find({"user_id": str(current_user["_id"])}).sort("upload_date", -1).to_list(length=100)
        
        for project in projects:
            project["_id"] = str(project["_id"])
        
        return {
            "success": True,
            "count": len(projects),
            "projects": projects
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")


async def get_project_by_id(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({
            "_id": ObjectId(project_id),
            "user_id": str(current_user["_id"])
        })
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        project["_id"] = str(project["_id"])
        
        return {
            "success": True,
            "project": project
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch project: {str(e)}")


async def delete_project(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({
            "_id": ObjectId(project_id),
            "user_id": str(current_user["_id"])
        })
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        # Delete uploaded file
        if os.path.exists(project["file_path"]):
            os.remove(project["file_path"])
        
        # Delete extracted folder
        if project.get("extracted_path") and os.path.exists(project["extracted_path"]):
            shutil.rmtree(project["extracted_path"])
        
        # Delete from database
        await collection.delete_one({"_id": ObjectId(project_id)})
        
        return {
            "success": True,
            "message": "Project deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")