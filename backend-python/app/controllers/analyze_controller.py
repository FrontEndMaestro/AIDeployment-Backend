from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId
from ..config.database import get_projects_collection
from ..utils.detector import detect_framework, detect_env_variables
from ..utils.auth import get_current_active_user


async def analyze_project_handler(
    project_id: str, 
    force: bool = False, 
    use_ml: bool = True,
    current_user: dict = None
):
    """
    Analyze project with optional ML toggle
    
    Args:
        project_id: Project ID to analyze
        force: Force re-analysis
        use_ml: Use ML-based detection (default: True)
        current_user: Current authenticated user
    """
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

        
        if project["status"] not in ["extracted", "analyzed"]:
            return {
                "success": False,
                "message": "Project must be extracted first",
                "current_status": project["status"]
            }
        
        if project["status"] == "analyzed" and not force:
            return {
                "success": False,
                "message": "Project already analyzed. Use ?force=true to re-analyze",
                "data": {
                    "framework": project["metadata"]["framework"],
                    "language": project["metadata"]["language"],
                    "dependencies": project["metadata"]["dependencies"],
                    # keep old field name, but it may be None if only detection_confidence exists
                    "ml_confidence": project["metadata"].get("ml_confidence") or project["metadata"].get("detection_confidence")
                }
            }
        
        # Update status to analyzing
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {"status": "analyzing", "updated_at": datetime.now()},
                "$push": {"logs": {"message": f"Analysis started (ML: {use_ml})", "timestamp": datetime.now()}}
            }
        )
        
        print(f"📦 Starting analysis for project: {project_id}")
        print(f"🤖 ML Mode: {'Enabled' if use_ml else 'Disabled'}")
        
        # Detect framework with ML toggle
        detection = detect_framework(project["extracted_path"], use_ml=use_ml)

        # ---- Compatibility shim for confidence fields ----
        # detector.py now uses "detection_confidence".
        # For backward compatibility with existing code & API, we mirror it
        # into "ml_confidence" if that key is missing.
        if "ml_confidence" not in detection and "detection_confidence" in detection:
            detection["ml_confidence"] = detection["detection_confidence"]
        # -------------------------------------------------
        
        # Detect environment variables (extra pass using original extracted path)
        env_vars = detect_env_variables(project["extracted_path"])
        if env_vars:
            detection["env_variables"] = env_vars
        
        # Build analysis logs
        analysis_logs = [
            f"Framework detected: {detection['framework']}",
            f"Language: {detection['language']}",
            f"Runtime: {detection['runtime']}",
            f"Dependencies: {len(detection['dependencies'])} found",
            f"Docker support: {'Yes' if detection['dockerfile'] else 'No'}",
        ]
        
        if detection.get("ml_confidence"):
            # ml_confidence now points to detection_confidence internally
            analysis_logs.append(
                f"ML Confidence - Language: {detection['ml_confidence'].get('language')}, "
                f"Framework: {detection['ml_confidence'].get('framework')}"
            )
        
        # Update project with analysis data
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "analyzed",
                    "metadata": detection,
                    "analysis_date": datetime.now(),
                    "analysis_logs": analysis_logs,
                    "ml_enabled": use_ml,
                    "updated_at": datetime.now()
                },
                "$push": {"logs": {"message": "Analysis completed successfully", "timestamp": datetime.now()}}
            }
        )
        
        print(f"✅ Analysis completed for project: {project_id}")
        print(f"   Framework: {detection['framework']}")
        print(f"   Language: {detection['language']}")
        print(f"   Dependencies: {len(detection['dependencies'])} found")
        if detection.get("ml_confidence"):
            print(f"   ML Confidence: {detection['ml_confidence']}")
        
        return {
            "success": True,
            "message": "Project analyzed successfully! ✅",
            "data": {
                "project_id": project_id,
                "project_name": project["project_name"],
                **detection,
                "analysis_date": datetime.now(),
                "ml_enabled": use_ml
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        # Mark as failed
        if ObjectId.is_valid(project_id):
            collection = get_projects_collection()
            await collection.update_one(
                {"_id": ObjectId(project_id)},
                {
                    "$set": {"status": "failed", "updated_at": datetime.now()},
                    "$push": {"logs": {"message": f"Failed: {str(e)}", "timestamp": datetime.now()}}
                }
            )
        print(f"❌ Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def get_analysis_results_handler(project_id: str, current_user: dict):
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
        
        if project["status"] not in ["analyzed", "completed"]:
            return {
                "success": False,
                "message": "Project not yet analyzed. Please analyze first.",
                "current_status": project["status"]
            }
        
        metadata = project.get("metadata", {})
        # Normalize confidence for output as well
        ml_conf = metadata.get("ml_confidence") or metadata.get("detection_confidence")
        
        return {
            "success": True,
            "project_id": str(project["_id"]),
            "project_name": project["project_name"],
            "status": project["status"],
            "metadata": metadata,
            "analysis_date": project.get("analysis_date"),
            "analysis_logs": project.get("analysis_logs", []),
            "ml_enabled": project.get("ml_enabled", True),
            "ml_confidence": ml_conf
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analysis results: {str(e)}")


async def get_full_project_details_handler(project_id: str, current_user: dict):
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
            "data": project
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project details: {str(e)}")
    

async def get_project_metadata_handler(project_id: str, current_user: dict):
    """Get only metadata for a project"""
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
        
        metadata = project.get("metadata", {})
        ml_conf = metadata.get("ml_confidence") or metadata.get("detection_confidence")
        
        return {
            "success": True,
            "project_id": str(project["_id"]),
            "project_name": project["project_name"],
            "metadata": metadata,
            "analysis_date": project.get("analysis_date"),
            "ml_enabled": project.get("ml_enabled", True),
            "ml_confidence": ml_conf
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


async def get_all_metadata_handler(current_user: dict, framework: str = None, language: str = None):
    """Get metadata for all projects with optional filters - for current user only"""
    try:
        collection = get_projects_collection()
        
        # Build query - filter by user AND status
        query = {
            "user_id": str(current_user["_id"]),
            "status": {"$in": ["analyzed", "completed"]}
        }
        
        if framework:
            query["metadata.framework"] = framework
        
        if language:
            query["metadata.language"] = language
        
        projects = await collection.find(query).to_list(length=100)
        
        # Format results
        results = []
        for project in projects:
            results.append({
                "project_id": str(project["_id"]),
                "project_name": project["project_name"],
                "framework": project["metadata"]["framework"],
                "language": project["metadata"]["language"],
                "runtime": project["metadata"]["runtime"],
                "dependencies_count": len(project["metadata"]["dependencies"]),
                "analysis_date": project.get("analysis_date"),
                "has_docker": project["metadata"].get("dockerfile", False)
            })
        
        return {
            "success": True,
            "count": len(results),
            "filters": {
                "framework": framework,
                "language": language
            },
            "projects": results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


async def get_metadata_statistics_handler(current_user: dict):
    """Get statistics of all analyzed projects for current user"""
    try:
        collection = get_projects_collection()
        
        # Get all analyzed projects for current user
        projects = await collection.find({
            "user_id": str(current_user["_id"]),
            "status": {"$in": ["analyzed", "completed"]}
        }).to_list(length=1000)
        
        # Calculate statistics
        total_projects = len(projects)
        
        if total_projects == 0:
            return {
                "success": True,
                "statistics": {
                    "total_projects": 0,
                    "frameworks": {},
                    "languages": {},
                    "runtimes": {},
                    "docker_usage": {
                        "has_dockerfile": 0,
                        "has_compose": 0,
                        "percentage": 0
                    }
                }
            }
        
        # Framework distribution
        frameworks = {}
        languages = {}
        runtimes = {}
        
        docker_count = 0
        compose_count = 0
        
        for project in projects:
            metadata = project.get("metadata", {})
            
            fw = metadata.get("framework", "Unknown")
            lang = metadata.get("language", "Unknown")
            runtime = metadata.get("runtime")
            
            frameworks[fw] = frameworks.get(fw, 0) + 1
            languages[lang] = languages.get(lang, 0) + 1
            
            if runtime:
                runtimes[runtime] = runtimes.get(runtime, 0) + 1
            
            if metadata.get("dockerfile"):
                docker_count += 1
            
            if metadata.get("docker_compose"):
                compose_count += 1
        
        return {
            "success": True,
            "statistics": {
                "total_projects": total_projects,
                "frameworks": frameworks,
                "languages": languages,
                "runtimes": runtimes,
                "docker_usage": {
                    "has_dockerfile": docker_count,
                    "has_compose": compose_count,
                    "percentage": round((docker_count / total_projects * 100), 2) if total_projects > 0 else 0
                }
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


async def export_metadata_handler(project_id: str, format: str = "json", current_user: dict = None):
    """Export project metadata in different formats"""
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
        
        if project["status"] not in ["analyzed", "completed"]:
            raise HTTPException(status_code=400, detail="Project not yet analyzed")
        
        # Prepare export data
        metadata = project.get("metadata", {}) or {}
        ml_conf = metadata.get("ml_confidence") or metadata.get("detection_confidence")

        export_data = {
            "project_name": project["project_name"],
            "framework": metadata.get("framework"),
            "language": metadata.get("language"),
            "runtime": metadata.get("runtime"),
            "dependencies": metadata.get("dependencies", []),

            # legacy single port (kept for backwards compatibility)
            "port": metadata.get("port"),

            # NEW: explicit ports
            "backend_port": metadata.get("backend_port"),
            "frontend_port": metadata.get("frontend_port"),
            "database": metadata.get("database"),
            "database_port": metadata.get("database_port"),

            # NEW: docker-aware ports (may be None / missing)
            "docker_backend_ports": metadata.get("docker_backend_ports"),
            "docker_frontend_ports": metadata.get("docker_frontend_ports"),
            "docker_database_ports": metadata.get("docker_database_ports"),
            "docker_other_ports": metadata.get("docker_other_ports"),
            "docker_expose_ports": metadata.get("docker_expose_ports"),

            "build_command": metadata.get("build_command"),
            "start_command": metadata.get("start_command"),
            "env_variables": metadata.get("env_variables", []),
            "dockerfile": metadata.get("dockerfile", False),
            "docker_compose": metadata.get("docker_compose", False),
            "detected_files": metadata.get("detected_files", []),
            "ml_confidence": ml_conf,
            "analysis_date": str(project.get("analysis_date")),
        }
        
        if format == "json":
            return {
                "success": True,
                "format": "json",
                "data": export_data
            }
        
        elif format == "yaml":
            import yaml
            yaml_data = yaml.dump(export_data, default_flow_style=False)
            return {
                "success": True,
                "format": "yaml",
                "data": yaml_data
            }
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported format. Use 'json' or 'yaml'")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export metadata: {str(e)}")
