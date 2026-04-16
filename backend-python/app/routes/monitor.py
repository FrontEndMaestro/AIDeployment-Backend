from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.utils.auth import get_current_user, verify_token
from app.controllers.monitor_controller import monitor_controller

router = APIRouter(
    prefix="/api/monitor",
    tags=["Monitoring"]
)

@router.get("/{project_id}/status")
async def get_status(project_id: str, current_user: dict = Depends(get_current_user)):
    """Get overall monitoring and health status of a project's deployments."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.get_project_monitoring_status(project_id, user_id)
    if not result.get("success", True):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result

@router.post("/{project_id}/heal")
async def trigger_healing(project_id: str, current_user: dict = Depends(get_current_user)):
    """Trigger a pod restart/rollback."""
    user_id = str(current_user["_id"])
    result = await monitor_controller.heal_project(project_id, user_id)
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result

@router.get("/{project_id}/logs/stream")
async def stream_docker_logs(project_id: str, request: Request):
    """
    Stream logs using Server-Sent Events (SSE). 
    Note: Can't easily use JWT Dependency in standard SSE EventSource since it doesn't allow custom headers.
    In a real app, use a short-lived token in query params, or cookies. 
    Here we extract user from token param if provided.
    """
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    
    # Simple manual token verify for SSE stream
    user = await verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user_id = str(user["_id"])
    
    # Get generator and return StreamingResponse
    log_generator = await monitor_controller.stream_logs(project_id, user_id)
    
    return StreamingResponse(
        log_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
