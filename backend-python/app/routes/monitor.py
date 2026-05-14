from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.utils.auth import get_current_user, verify_token
from app.controllers.monitor_controller import monitor_controller
from app.utils.port_forward_manager import port_forward_manager

router = APIRouter(prefix="/api/monitor", tags=["Monitoring"])


# ─── Status ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/status")
async def get_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Overall monitoring status: K8s health, AWS state, pods, recent events.
    Reads k8s_deployment_name saved during deploy — no more naming mismatch.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_project_monitoring_status(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Access URL (port-forward tunnel) ────────────────────────────────────────

@router.get("/{project_id}/access")
async def get_access_url(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Returns the localhost URL for the deployed project.
    If the port-forward tunnel died, automatically restarts it.
    """
    from app.config.database import get_projects_collection
    from bson import ObjectId

    user_id = str(current_user["_id"])

    # Check if tunnel is already alive
    tunnel = port_forward_manager.get(project_id)
    if tunnel:
        return {
            "success": True,
            "url": tunnel["url"],
            "local_port": tunnel["local_port"],
            "port_forward_active": True,
            "source": "running_tunnel",
        }

    # Tunnel is not alive — look up project to restart it
    collection = get_projects_collection()
    project = await collection.find_one(
        {"_id": ObjectId(project_id), "user_id": user_id}
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    deployment = project.get("deployment") or {}
    service_name = deployment.get("deployment_name") or project.get("k8s_deployment_name")
    namespace = deployment.get("k8s_namespace") or project.get("k8s_namespace") or "default"
    container_port = deployment.get("node_port")

    # Try to recover port from stored local_port or node_port
    if not service_name:
        raise HTTPException(status_code=400, detail="Project has not been deployed to Kubernetes")

    # Detect container port from K8s service spec
    from app.services.monitor_service import MonitorService
    svcs = MonitorService.get_services(namespace)
    container_port = next(
        (
            int(str(p).split("/")[0].split(":")[0])
            for s in svcs if s.get("name") == service_name
            for p in s.get("ports", [])
        ),
        deployment.get("node_port", 8000),
    )

    pf_result = port_forward_manager.start(
        project_id=project_id,
        service_name=service_name,
        container_port=container_port,
        namespace=namespace,
    )

    if pf_result["success"]:
        # Persist the new URL back to DB
        from datetime import datetime
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"access_url": pf_result["url"], "updated_at": datetime.now()}}
        )
        return {
            "success": True,
            "url": pf_result["url"],
            "local_port": pf_result["local_port"],
            "port_forward_active": True,
            "source": "restarted_tunnel",
        }

    # Fallback: return NodePort URL even if unreachable on kind
    fallback = deployment.get("service_url") or project.get("access_url")
    return {
        "success": False,
        "url": fallback,
        "local_port": None,
        "port_forward_active": False,
        "message": pf_result.get("message", "Port-forward unavailable"),
        "source": "fallback",
    }


# ─── Cluster overview ─────────────────────────────────────────────────────────

@router.get("/cluster/overview")
async def cluster_overview(current_user: dict = Depends(get_current_user)):
    """Nodes, namespaces, total deployments/services/pods counts."""
    user_id = str(current_user["_id"])
    return await monitor_controller.get_cluster_overview(user_id)


# ─── Deployment detail ────────────────────────────────────────────────────────

@router.get("/{project_id}/deployment")
async def get_deployment_detail(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Full deployment detail: replicas, readyReplicas, health classification
    (HEALTHY/DEGRADED/FAILED/SCALING/RECOVERING/PENDING), pod list.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_deployment_detail(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Rollout status ───────────────────────────────────────────────────────────

@router.get("/{project_id}/rollout")
async def get_rollout_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """Run kubectl rollout status (30s timeout) and return output."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_rollout_status(project_id, user_id)
    return result


# ─── Services ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/services")
async def get_services(project_id: str, current_user: dict = Depends(get_current_user)):
    """List Kubernetes services in the project's namespace."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_services(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Resource metrics ─────────────────────────────────────────────────────────

@router.get("/{project_id}/metrics")
async def get_metrics(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    CPU/memory via kubectl top pods/nodes.
    Returns metrics_server_available=false if metrics-server is not installed.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_resource_metrics(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Self-Heal ────────────────────────────────────────────────────────────────

@router.post("/{project_id}/heal")
async def trigger_healing(project_id: str, current_user: dict = Depends(get_current_user)):
    """kubectl rollout restart deployment/<name> — uses saved k8s_deployment_name."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.heal_project(project_id, user_id)
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


# ─── Pod log snapshot ─────────────────────────────────────────────────────────

@router.get("/{project_id}/logs")
async def get_pod_logs(
    project_id: str,
    tail: int = Query(default=100, ge=10, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Snapshot of recent pod logs. Use /logs/stream for live tailing."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_pod_logs(project_id, user_id, tail=tail)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── k8s Events ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/events")
async def get_k8s_events(
    project_id: str,
    limit: int = Query(default=50, ge=5, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    Recent K8s events for this deployment — namespace-wide with name-prefix filter.
    Shows scheduling failures, ImagePullBackOff, CrashLoopBackOff, HPA events etc.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_k8s_events(project_id, user_id, limit=limit)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── All Pods ─────────────────────────────────────────────────────────────────

@router.get("/pods/all")
async def get_all_pods(
    namespace: str = Query(default="default"),
    current_user: dict = Depends(get_current_user),
):
    """All pods in the given namespace with state/ready/restarts/IP."""
    user_id = str(current_user["_id"])
    return await monitor_controller.get_all_pods(user_id)


# ─── Live log stream (SSE) ─────────────────────────────────────────────────────

@router.get("/{project_id}/logs/stream")
async def stream_pod_logs(project_id: str, request: Request):
    """
    Live pod logs via SSE (kubectl logs -f).
    Pass ?token=<jwt> because EventSource cannot set headers.
    Automatically discovers the correct pod using saved k8s_deployment_name.
    """
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")

    user = await verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = str(user["_id"])
    log_generator = await monitor_controller.stream_logs(project_id, user_id)

    return StreamingResponse(
        log_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



# ─── Status ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/status")
async def get_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Overall monitoring status: K8s health, AWS state, pods, recent events.
    Reads k8s_deployment_name saved during deploy — no more naming mismatch.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_project_monitoring_status(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Cluster overview ─────────────────────────────────────────────────────────

@router.get("/cluster/overview")
async def cluster_overview(current_user: dict = Depends(get_current_user)):
    """Nodes, namespaces, total deployments/services/pods counts."""
    user_id = str(current_user["_id"])
    return await monitor_controller.get_cluster_overview(user_id)


# ─── Deployment detail ────────────────────────────────────────────────────────

@router.get("/{project_id}/deployment")
async def get_deployment_detail(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Full deployment detail: replicas, readyReplicas, health classification
    (HEALTHY/DEGRADED/FAILED/SCALING/RECOVERING/PENDING), pod list.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_deployment_detail(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Rollout status ───────────────────────────────────────────────────────────

@router.get("/{project_id}/rollout")
async def get_rollout_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """Run kubectl rollout status (30s timeout) and return output."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_rollout_status(project_id, user_id)
    return result


# ─── Services ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/services")
async def get_services(project_id: str, current_user: dict = Depends(get_current_user)):
    """List Kubernetes services in the project's namespace."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_services(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Resource metrics ─────────────────────────────────────────────────────────

@router.get("/{project_id}/metrics")
async def get_metrics(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    CPU/memory via kubectl top pods/nodes.
    Returns metrics_server_available=false if metrics-server is not installed.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_resource_metrics(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Self-Heal ────────────────────────────────────────────────────────────────

@router.post("/{project_id}/heal")
async def trigger_healing(project_id: str, current_user: dict = Depends(get_current_user)):
    """kubectl rollout restart deployment/<name> — uses saved k8s_deployment_name."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.heal_project(project_id, user_id)
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


# ─── Pod log snapshot ─────────────────────────────────────────────────────────

@router.get("/{project_id}/logs")
async def get_pod_logs(
    project_id: str,
    tail: int = Query(default=100, ge=10, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Snapshot of recent pod logs. Use /logs/stream for live tailing."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_pod_logs(project_id, user_id, tail=tail)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── k8s Events ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/events")
async def get_k8s_events(
    project_id: str,
    limit: int = Query(default=50, ge=5, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    Recent K8s events for this deployment — namespace-wide with name-prefix filter.
    Shows scheduling failures, ImagePullBackOff, CrashLoopBackOff, HPA events etc.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_k8s_events(project_id, user_id, limit=limit)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── All Pods ─────────────────────────────────────────────────────────────────

@router.get("/pods/all")
async def get_all_pods(
    namespace: str = Query(default="default"),
    current_user: dict = Depends(get_current_user),
):
    """All pods in the given namespace with state/ready/restarts/IP."""
    user_id = str(current_user["_id"])
    return await monitor_controller.get_all_pods(user_id)


# ─── Live log stream (SSE) ─────────────────────────────────────────────────────

@router.get("/{project_id}/logs/stream")
async def stream_pod_logs(project_id: str, request: Request):
    """
    Live pod logs via SSE (kubectl logs -f).
    Pass ?token=<jwt> because EventSource cannot set headers.
    Automatically discovers the correct pod using saved k8s_deployment_name.
    """
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")

    user = await verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = str(user["_id"])
    log_generator = await monitor_controller.stream_logs(project_id, user_id)

    return StreamingResponse(
        log_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
