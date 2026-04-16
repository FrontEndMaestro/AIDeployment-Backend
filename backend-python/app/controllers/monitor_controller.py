from typing import Dict, Any
from bson import ObjectId
from app.config.database import get_projects_collection
from app.services.monitor_service import monitor_service
from app.utils.k8s_deployer import stream_pod_logs

class MonitorController:
    @staticmethod
    async def get_project_monitoring_status(project_id: str, user_id: str) -> Dict[str, Any]:
        """Fetch the overall monitoring status for a project."""
        projects_collection = get_projects_collection()
        project = await projects_collection.find_one({"_id": ObjectId(project_id), "user_id": user_id})
        
        if not project:
            return {"success": False, "message": "Project not found"}
            
        # Get standardized docker registry name which is used for deployments
        project_name = project.get("name", "app").lower().replace(" ", "-")
        deployment_name = f"devops-autopilot-{project_name}"
        
        # Gather health metrics
        k8s_health = monitor_service.get_k8s_health(deployment_name)
        aws_health = monitor_service.get_aws_health(project_id)
        
        # Calculate uptime proxy or overall health
        overall_healthy = k8s_health.get("healthy", False) or aws_health.get("healthy", False)
        
        return {
            "success": True,
            "project_name": project.get("name"),
            "deployment_name": deployment_name,
            "overall_healthy": overall_healthy,
            "kubernetes": k8s_health,
            "aws": aws_health,
            "last_analysis": project.get("analysis_date")
        }

    @staticmethod
    async def heal_project(project_id: str, user_id: str) -> Dict[str, Any]:
        """Attempt to auto-recover standard Kubernetes deployment."""
        projects_collection = get_projects_collection()
        project = await projects_collection.find_one({"_id": ObjectId(project_id), "user_id": user_id})
        
        if not project:
            return {"success": False, "message": "Project not found"}
            
        project_name = project.get("name", "app").lower().replace(" ", "-")
        deployment_name = f"devops-autopilot-{project_name}"
        
        return monitor_service.trigger_self_healing(deployment_name)

    @staticmethod
    async def stream_logs(project_id: str, user_id: str):
        """Returns the streaming generator for Server-Sent Events."""
        projects_collection = get_projects_collection()
        project = await projects_collection.find_one({"_id": ObjectId(project_id), "user_id": user_id})
        
        if not project:
            async def error_stream():
                yield "data: {\"type\": \"error\", \"message\": \"Project not found\"}\n\n"
            return error_stream()
            
        project_name = project.get("name", "app").lower().replace(" ", "-")
        deployment_name = f"devops-autopilot-{project_name}"
        
        return stream_pod_logs(deployment_name)

monitor_controller = MonitorController()
