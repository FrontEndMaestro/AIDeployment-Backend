from fastapi import APIRouter, Depends
from ..controllers.deployment_controller import (
    deploy_project_handler,
    get_deployment_status_handler,
    undeploy_project_handler
)
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/deploy", tags=["Deployment"])


@router.post("/{project_id}")
async def deploy_project(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Deploy project to Kubernetes
    
    Process:
    1. Build Docker image
    2. Push to Docker Hub
    3. Generate K8s manifests
    4. Deploy to K8s
    5. Return service URL
    """
    return await deploy_project_handler(project_id, current_user)


@router.get("/{project_id}/status")
async def get_deployment_status(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get deployment status"""
    return await get_deployment_status_handler(project_id, current_user)


@router.delete("/{project_id}")
async def undeploy_project(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Remove deployment from K8s"""
    return await undeploy_project_handler(project_id, current_user)