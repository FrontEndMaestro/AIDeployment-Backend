import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from bson import ObjectId

from app.config.database import get_projects_collection
from app.services.monitor_service import monitor_service
from app.utils.k8s_deployer import stream_pod_logs


class MonitorController:

    # ─── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _deployment_name(project: Dict) -> str:
        project_name = project.get("project_name", "app").lower().replace(" ", "-")
        return f"devops-autopilot-{project_name}".replace("_", "-")

    @staticmethod
    async def _get_project(project_id: str, user_id: str) -> Optional[Dict]:
        collection = get_projects_collection()
        return await collection.find_one(
            {"_id": ObjectId(project_id), "user_id": user_id}
        )

    # ─── Status ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_project_monitoring_status(project_id: str, user_id: str) -> Dict[str, Any]:
        """Fetch the overall monitoring status for a project."""
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}

        deployment_name = MonitorController._deployment_name(project)

        k8s_health = monitor_service.get_k8s_health(deployment_name)
        aws_health = monitor_service.get_aws_health(project_id)
        recent_events = monitor_service.get_recent_k8s_events(deployment_name, limit=20)
        all_pods = monitor_service.get_all_pods_status()

        overall_healthy = k8s_health.get("healthy", False) or aws_health.get("healthy", False)

        return {
            "success": True,
            "project_name": project.get("project_name"),
            "deployment_name": deployment_name,
            "overall_healthy": overall_healthy,
            "kubernetes": k8s_health,
            "aws": aws_health,
            "recent_events": recent_events,
            "pods": all_pods,
            "last_analysis": project.get("analysis_date"),
            "deployment": project.get("deployment") or {},
            "deployment_status": project.get("deployment_status", "not_deployed"),
        }

    # ─── Heal ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def heal_project(project_id: str, user_id: str) -> Dict[str, Any]:
        """Attempt to auto-recover standard Kubernetes deployment."""
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}

        deployment_name = MonitorController._deployment_name(project)
        return monitor_service.trigger_self_healing(deployment_name)

    # ─── Pod log snapshot ─────────────────────────────────────────────────────

    @staticmethod
    async def get_pod_logs(
        project_id: str, user_id: str, tail: int = 100
    ) -> Dict[str, Any]:
        """Return a snapshot of recent pod logs (non-streaming)."""
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found", "logs": []}

        deployment_name = MonitorController._deployment_name(project)
        log_lines = monitor_service.get_pod_logs(deployment_name, tail_lines=tail)

        return {
            "success": True,
            "deployment_name": deployment_name,
            "logs": log_lines,
            "count": len(log_lines),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ─── k8s Events ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_k8s_events(
        project_id: str, user_id: str, limit: int = 50
    ) -> Dict[str, Any]:
        """Return recent Kubernetes events for the project's deployment."""
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found", "events": []}

        deployment_name = MonitorController._deployment_name(project)
        events = monitor_service.get_recent_k8s_events(deployment_name, limit=limit)

        return {
            "success": True,
            "deployment_name": deployment_name,
            "events": events,
            "count": len(events),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ─── All Pods ─────────────────────────────────────────────────────────────

    @staticmethod
    async def get_all_pods(user_id: str) -> Dict[str, Any]:
        """Return status of all pods in the default namespace."""
        pods = monitor_service.get_all_pods_status()
        return {
            "success": True,
            "pods": pods,
            "count": len(pods),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ─── Streaming pod logs ───────────────────────────────────────────────────

    @staticmethod
    async def stream_logs(project_id: str, user_id: str):
        """Returns the streaming generator for Server-Sent Events (live kubectl logs -f)."""
        project = await MonitorController._get_project(project_id, user_id)

        if not project:
            async def error_stream():
                yield "data: {\"type\": \"error\", \"message\": \"Project not found\"}\n\n"
            return error_stream()

        deployment_name = MonitorController._deployment_name(project)
        return stream_pod_logs(deployment_name)


monitor_controller = MonitorController()
