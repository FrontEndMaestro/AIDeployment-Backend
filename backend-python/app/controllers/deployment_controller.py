from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId
import os
import sys
from ..config.database import get_projects_collection
from ..config.settings import settings
from ..utils.docker_builder import build_docker_image
from ..utils.docker_pusher import push_docker_image
from ..utils.k8s_deployer import deploy_to_kubernetes, get_deployment_status, cleanup_deployment
from ..utils.k8s_manifest_generator import generate_k8s_manifests
from ..utils.port_forward_manager import port_forward_manager


def _safe_print(msg: str):
    try:
        print(msg)
        sys.stdout.flush()
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))
        sys.stdout.flush()


async def deploy_project_handler(project_id: str, current_user: dict):
    """Deploy extracted & analyzed project to local Kubernetes"""
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        if project.get("deployment_status") == "deploying":
            raise HTTPException(status_code=400, detail="Deployment already in progress")
        
        if project["status"] not in ["analyzed", "completed"]:
            return {
                "success": False,
                "message": "Project must be analyzed first",
                "current_status": project["status"]
            }
        
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {"deployment_status": "deploying", "updated_at": datetime.now()},
                "$push": {"logs": {"message": "Deployment started", "timestamp": datetime.now()}}
            }
        )
        
        _safe_print(f"[DEPLOY] Deployment started: {project_id}")
        
        metadata = project.get("metadata", {})
        language = metadata.get("language", "Unknown")
        framework = metadata.get("framework", "Unknown")
        port = metadata.get("port", 8000)
        env_variables = metadata.get("env_variables", [])
        project_name = project.get("project_name", "app").replace(" ", "-").lower()
        extracted_path = project.get("extracted_path")
        
        if not extracted_path or not os.path.exists(extracted_path):
            raise HTTPException(status_code=400, detail="Extracted project files not found")
        
        _safe_print(f"[DEPLOY] Detected language: {language}")
        
        # Step 1: Build Docker image
        _safe_print(f"[DEPLOY] Building Docker image...")
        image_name = f"hamzafarooqi/devops-autopilot-{project_name}"
        image_tag = f"{image_name}:latest"
        
        build_result = build_docker_image(
            project_path=extracted_path,
            image_tag=image_tag,
            language=language,
            port=port,
            start_command=metadata.get("start_command"),
            build_command=metadata.get("build_command")
        )
        # Around line 50, after build_result:


        if build_result.get("detected_port"):
            port = build_result["detected_port"]
            _safe_print(f"[DEPLOY] Using detected port: {port}")
        
        if not build_result["success"]:
            raise Exception(f"Docker build failed: {build_result['message']}")
        
        _safe_print("[DEPLOY] Docker image built")
        
        # Step 2: Push to Docker Hub
        _safe_print("[DEPLOY] Pushing to Docker Hub...")
        push_result = push_docker_image(image_tag)
        
        if not push_result["success"]:
            raise Exception(f"Docker push failed: {push_result['message']}")
        
        _safe_print("[DEPLOY] Docker image pushed")
        
        # Step 3: Generate K8s manifests
        _safe_print("[DEPLOY] Generating K8s manifests...")
        deployment_name = f"devops-autopilot-{project_name}".replace("_", "-").lower()
        node_port = 30000 + (hash(project_id) % 2767)
        
        manifests = generate_k8s_manifests(
            deployment_name=deployment_name,
            image=image_tag,
            port=port,
            node_port=node_port,
            env_variables=env_variables,
            mongodb_url=f"mongodb://host.docker.internal:27017/{project_name}",
            labels={"project_id": project_id, "created_by": current_user.get("username", "user")}
        )
        
        if "deployment" in manifests:
            manifests["deployment"] = manifests["deployment"].replace(
                "imagePullPolicy: Always", "imagePullPolicy: IfNotPresent"
            )
        
        _safe_print("[DEPLOY] K8s manifests generated")
        
        # Step 4: Deploy to Kubernetes
        _safe_print("[DEPLOY] Deploying to K8s...")
        k8s_result = deploy_to_kubernetes(manifests)
        
        if not k8s_result["success"]:
            raise Exception(f"K8s deployment failed: {k8s_result['message']}")
        
        _safe_print("[DEPLOY] Deployed to K8s")
        
        # Step 5: Auto port-forward so app is reachable on localhost immediately
        _safe_print(f"[DEPLOY] Starting auto port-forward for {deployment_name}...")
        pf_result = port_forward_manager.start(
            project_id=project_id,
            service_name=deployment_name,
            container_port=port,
            namespace="default",
        )
        
        if pf_result["success"]:
            access_url = pf_result["url"]
            _safe_print(f"[DEPLOY] App accessible at: {access_url}")
        else:
            # Port-forward failed but deploy succeeded — fall back to NodePort URL
            _safe_print(f"[DEPLOY-WARN] Port-forward failed: {pf_result.get('message')}")
            access_url = f"http://localhost:{node_port}"
        
        # Step 6: Update database with access URL
        deployment_info = {
            "deployment_name": deployment_name,
            "pod_name": k8s_result.get("pod_name"),
            "service_url": access_url,
            "node_port": node_port,
            "local_port": pf_result.get("local_port"),
            "port_forward_active": pf_result["success"],
            "image": image_tag,
            "status": "running",
            "deployed_at": datetime.now(),
            "k8s_namespace": "default",
            "k8s_deployment_name": deployment_name,
            "language": language,
            "framework": framework
        }
        
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "deployment_status": "deployed",
                    "deployment": deployment_info,
                    "k8s_deployment_name": deployment_name,
                    "k8s_namespace": "default",
                    "status": "completed",
                    "updated_at": datetime.now(),
                    "access_url": access_url,
                },
                "$push": {"logs": {"message": f"Deployment complete. Access at: {access_url}", "timestamp": datetime.now()}}
            }
        )
        
        _safe_print(f"[DEPLOY] Complete — {access_url}")
        
        return {
            "success": True,
            "message": "Project deployed successfully!",
            "data": {
                "project_id": project_id,
                "project_name": project_name,
                "deployment": deployment_info,
                "access_url": access_url,
                "port_forward_active": pf_result["success"],
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        _safe_print(f"[DEPLOY-ERROR] {str(e)}")
        
        if ObjectId.is_valid(project_id):
            collection = get_projects_collection()
            await collection.update_one(
                {"_id": ObjectId(project_id)},
                {
                    "$set": {"deployment_status": "failed", "updated_at": datetime.now()},
                    "$push": {"logs": {"message": f"Deployment failed: {str(e)}", "timestamp": datetime.now()}}
                }
            )
        
        raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")


async def get_deployment_status_handler(project_id: str, current_user: dict):
    """Get deployment status"""
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied")
        
        deployment = project.get("deployment", {})
        deployment_status = project.get("deployment_status", "not_deployed")
        
        return {
            "success": True,
            "project_id": project_id,
            "deployment_status": deployment_status,
            "deployment": deployment
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


async def undeploy_project_handler(project_id: str, current_user: dict):
    """Remove deployment from K8s"""
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied")
        
        deployment = project.get("deployment", {})
        deployment_name = deployment.get("deployment_name")
        
        if not deployment_name:
            return {
                "success": False,
                "message": "No deployment found"
            }
        
        _safe_print(f"[UNDEPLOY] Removing: {deployment_name}")
        # Stop port-forward tunnel before cluster cleanup
        port_forward_manager.stop(project_id)
        cleanup_deployment(deployment_name)
        
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "deployment_status": "undeployed",
                    "deployment": None,
                    "updated_at": datetime.now()
                },
                "$push": {"logs": {"message": "Deployment removed", "timestamp": datetime.now()}}
            }
        )
        
        return {
            "success": True,
            "message": "Deployment removed"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Undeploy failed: {str(e)}")