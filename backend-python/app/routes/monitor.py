from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.utils.auth import get_current_user, verify_token
from app.controllers.monitor_controller import monitor_controller

router = APIRouter(prefix="/api/monitor", tags=["Monitoring"])


# ─── Status ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/status")
async def get_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get overall monitoring and health status of a project's deployments.
    Includes Kubernetes pod health, AWS state, recent k8s events, and all pods.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_project_monitoring_status(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── Self-Heal ────────────────────────────────────────────────────────────────

@router.post("/{project_id}/heal")
async def trigger_healing(
    project_id: str, current_user: dict = Depends(get_current_user)
):
    """Trigger a pod restart/rollback via kubectl rollout restart."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.heal_project(project_id, user_id)
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


# ─── Pod log snapshot ─────────────────────────────────────────────────────────

@router.get("/{project_id}/logs")
async def get_pod_logs(
    project_id: str,
    tail: int = Query(default=100, ge=10, le=1000, description="Number of recent log lines"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return a recent snapshot of pod logs (non-streaming).
    Use the /logs/stream endpoint for live tailing.
    """
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_pod_logs(project_id, user_id, tail=tail)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── k8s Events ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/events")
async def get_k8s_events(
    project_id: str,
    limit: int = Query(default=50, ge=5, le=200, description="Max number of events"),
    current_user: dict = Depends(get_current_user),
):
    """Return recent Kubernetes events for the project's deployment."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_k8s_events(project_id, user_id, limit=limit)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


# ─── All Pods ─────────────────────────────────────────────────────────────────

@router.get("/pods/all")
async def get_all_pods(current_user: dict = Depends(get_current_user)):
    """Return status of ALL pods in the default Kubernetes namespace."""
    user_id = str(current_user["_id"])
    return await monitor_controller.get_all_pods(user_id)


# ─── Live log stream (SSE) ─────────────────────────────────────────────────────

@router.get("/{project_id}/logs/stream")
async def stream_pod_logs(project_id: str, request: Request):
    """
    Stream live pod logs using Server-Sent Events (SSE).

    Auth: pass `?token=<jwt>` in the query string because EventSource in
    browsers cannot set custom headers.
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
