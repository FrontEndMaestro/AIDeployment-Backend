"""
monitor_controller.py

Key fix: deployment_name now reads from project["k8s_deployment_name"] (saved by
k8s_deploy_stream after apply), falling back to the sanitized project_name.
This eliminates the "Pod Not Found" caused by the old devops-autopilot-{name} prefix mismatch.
"""
import re
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from bson import ObjectId

from app.config.database import get_projects_collection
from app.services.monitor_service import MonitorService, monitor_service
from app.utils.k8s_deployer import stream_pod_logs


def _sanitize_k8s_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")[:50]


class MonitorController:

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deployment_name(project: Dict) -> str:
        """
        Read the actual K8s deployment name saved during k8s_deploy_stream.
        Falls back to sanitized project_name if not yet deployed.
        """
        # Preferred: what was actually applied to the cluster
        saved = project.get("k8s_deployment_name")
        if saved:
            return saved
        # Fallback: replicate k8s_deploy_stream sanitization logic
        raw = project.get("project_name", "app").lower().replace(" ", "-")
        return _sanitize_k8s_name(raw)

    @staticmethod
    def _namespace(project: Dict) -> str:
        return project.get("k8s_namespace") or "default"

    @staticmethod
    async def _get_project(project_id: str, user_id: str) -> Optional[Dict]:
        collection = get_projects_collection()
        return await collection.find_one(
            {"_id": ObjectId(project_id), "user_id": user_id}
        )

    # ── Status ────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_project_monitoring_status(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}

        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)

        k8s_health = monitor_service.get_k8s_health(deployment_name, namespace)
        aws_health = monitor_service.get_aws_health(project_id)
        recent_events = monitor_service.get_recent_k8s_events(deployment_name, namespace, limit=30)
        all_pods = monitor_service.get_all_pods_status(namespace)

        overall_healthy = k8s_health.get("healthy", False) or aws_health.get("healthy", False)

        return {
            "success": True,
            "project_name": project.get("project_name"),
            "deployment_name": deployment_name,
            "namespace": namespace,
            "overall_healthy": overall_healthy,
            "kubernetes": k8s_health,
            "aws": aws_health,
            "recent_events": recent_events,
            "pods": all_pods,
            "last_analysis": project.get("analysis_date"),
            "deployment": project.get("deployment") or {},
            "deployment_status": project.get("deployment_status", "not_deployed"),
        }

    # ── Cluster overview ──────────────────────────────────────────────────────

    @staticmethod
    async def get_cluster_overview(user_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            **monitor_service.get_cluster_overview(),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Deployment detail ─────────────────────────────────────────────────────

    @staticmethod
    async def get_deployment_detail(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}
        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)
        detail = monitor_service.get_deployment_detail(deployment_name, namespace)
        return {"success": True, **detail, "timestamp": datetime.utcnow().isoformat()}

    # ── Resource metrics ──────────────────────────────────────────────────────

    @staticmethod
    async def get_resource_metrics(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}
        namespace = MonitorController._namespace(project)
        metrics = monitor_service.get_resource_metrics(namespace)
        return {"success": True, **metrics, "timestamp": datetime.utcnow().isoformat()}

    # ── Services ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_services(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}
        namespace = MonitorController._namespace(project)
        svcs = monitor_service.get_services(namespace)
        return {"success": True, "services": svcs, "count": len(svcs),
                "timestamp": datetime.utcnow().isoformat()}

    # ── Rollout status ────────────────────────────────────────────────────────

    @staticmethod
    async def get_rollout_status(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}
        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)
        result = monitor_service.get_rollout_status(deployment_name, namespace, timeout_s=30)
        return {"success": True, **result, "timestamp": datetime.utcnow().isoformat()}

    # ── Heal ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def heal_project(project_id: str, user_id: str) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found"}
        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)
        return monitor_service.trigger_self_healing(deployment_name, namespace)

    # ── Pod log snapshot ──────────────────────────────────────────────────────

    @staticmethod
    async def get_pod_logs(project_id: str, user_id: str, tail: int = 100) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found", "logs": []}
        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)
        log_lines = monitor_service.get_pod_logs(deployment_name, namespace, tail_lines=tail)
        return {
            "success": True,
            "deployment_name": deployment_name,
            "logs": log_lines,
            "count": len(log_lines),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── k8s Events ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_k8s_events(project_id: str, user_id: str, limit: int = 50) -> Dict[str, Any]:
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            return {"success": False, "message": "Project not found", "events": []}
        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)
        events = monitor_service.get_recent_k8s_events(deployment_name, namespace, limit=limit)
        return {
            "success": True,
            "deployment_name": deployment_name,
            "events": events,
            "count": len(events),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── All Pods ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_all_pods(user_id: str) -> Dict[str, Any]:
        pods = monitor_service.get_all_pods_status()
        return {
            "success": True,
            "pods": pods,
            "count": len(pods),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Streaming pod logs ────────────────────────────────────────────────────

    @staticmethod
    async def stream_logs(project_id: str, user_id: str):
        project = await MonitorController._get_project(project_id, user_id)
        if not project:
            async def error_stream():
                yield "data: {\"type\": \"error\", \"message\": \"Project not found\"}\n\n"
            return error_stream()

        deployment_name = MonitorController._deployment_name(project)
        namespace = MonitorController._namespace(project)

        # Find actual pod name
        detail = monitor_service.get_deployment_detail(deployment_name, namespace)
        pods = detail.get("pods") or []
        if not pods:
            pods = monitor_service.get_pods_by_name_prefix(deployment_name, namespace)

        if pods:
            running = [p for p in pods if "running" in p.get("status", "").lower()]
            pod_name = (running or pods)[0]["name"]
        else:
            pod_name = None

        return stream_pod_logs(pod_name or deployment_name, namespace=namespace)


monitor_controller = MonitorController()
