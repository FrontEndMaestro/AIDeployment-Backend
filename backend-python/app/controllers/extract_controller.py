from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId
from ..config.database import get_projects_collection
from ..utils.extractor import extract_file, get_files_list, cleanup_extracted_files
from ..utils.auth import get_current_active_user


async def extract_project_handler(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check ownership
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        if project["status"] == "extracted":
            return {
                "success": False,
                "message": "Project already extracted",
                "data": {
                    "extracted_path": project.get("extracted_path"),
                    "files_count": project.get("files_count"),
                    "folders_count": project.get("folders_count")
                }
            }
        
        # Update status to extracting
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {"status": "extracting", "updated_at": datetime.now()},
                "$push": {"logs": {"message": "Extraction started", "timestamp": datetime.now()}}
            }
        )
        
        print(f"📦 Starting extraction for project: {project_id}")
        
        # Extract file with user-specific extraction path
        user_workspace = current_user.get("workspace_path")
        result = extract_file(project["file_path"], project_id, user_workspace)
        
        # Update project with extraction data
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "extracted",
                    "extracted_path": result["extracted_path"],
                    "extraction_date": datetime.now(),
                    "files_count": result["files_count"],
                    "folders_count": result["folders_count"],
                    "extraction_logs": result["logs"],
                    "updated_at": datetime.now()
                },
                "$push": {"logs": {"message": "Extraction completed successfully", "timestamp": datetime.now()}}
            }
        )
        
        print(f"✅ Extraction completed for project: {project_id}")
        
        return {
            "success": True,
            "message": "Project extracted successfully! ✅",
            "data": {
                "project_id": project_id,
                "project_name": project["project_name"],
                "extracted_path": result["extracted_path"],
                "files_count": result["files_count"],
                "folders_count": result["folders_count"],
                "extraction_date": datetime.now()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        if ObjectId.is_valid(project_id):
            collection = get_projects_collection()
            await collection.update_one(
                {"_id": ObjectId(project_id)},
                {
                    "$set": {"status": "failed", "updated_at": datetime.now()},
                    "$push": {"logs": {"message": f"Failed: {str(e)}", "timestamp": datetime.now()}}
                }
            )
        print(f"❌ Extraction error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


async def get_extracted_files_handler(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check ownership
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        if project["status"] not in ["extracted", "analyzing", "analyzed", "completed"]:
            return {
                "success": False,
                "message": "Project not yet extracted. Please extract first.",
                "current_status": project["status"]
            }
        
        files_list = get_files_list(project["extracted_path"])
        
        return {
            "success": True,
            "project_id": project_id,
            "project_name": project["project_name"],
            "extracted_path": project["extracted_path"],
            "total_files": project["files_count"],
            "total_folders": project["folders_count"],
            "files": files_list
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get files list: {str(e)}")


async def get_extraction_status_handler(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check ownership
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        project["_id"] = str(project["_id"])
        
        return {
            "success": True,
            "data": {
                "project_id": project["_id"],
                "project_name": project["project_name"],
                "status": project["status"],
                "upload_date": project["upload_date"],
                "extraction_date": project.get("extraction_date"),
                "files_count": project["files_count"],
                "folders_count": project["folders_count"],
                "extracted_path": project.get("extracted_path"),
                "logs": project["logs"],
                "extraction_logs": project["extraction_logs"]
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


async def cleanup_extraction_handler(project_id: str, current_user: dict):
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check ownership
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        user_workspace = current_user.get("workspace_path")
        cleaned = cleanup_extracted_files(project_id, user_workspace)
        
        if cleaned:
            await collection.update_one(
                {"_id": ObjectId(project_id)},
                {
                    "$set": {
                        "extracted_path": None,
                        "extraction_date": None,
                        "files_count": 0,
                        "folders_count": 0,
                        "status": "uploaded",
                        "updated_at": datetime.now()
                    },
                    "$push": {"logs": {"message": "Extracted files cleaned up", "timestamp": datetime.now()}}
                }
            )
            
            return {
                "success": True,
                "message": "Extracted files cleaned up successfully"
            }
        else:
            return {
                "success": False,
                "message": "No extracted files found to cleanup"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")