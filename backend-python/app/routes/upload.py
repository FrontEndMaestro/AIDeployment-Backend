from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional
from ..controllers.upload_controller import (
    upload_file_handler,
    get_all_projects,
    get_project_by_id,
    delete_project
)
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/upload", tags=["Upload"])


@router.post("/")
async def upload_project(
    file: UploadFile = File(...),
    project_name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Upload a project ZIP file
    
    **Requires Authentication**: Bearer token in Authorization header
    """
    return await upload_file_handler(file, project_name, current_user)


@router.get("/projects")
async def list_projects(current_user: dict = Depends(get_current_active_user)):
    """
    Get all projects for current user
    
    **Requires Authentication**
    """
    return await get_all_projects(current_user)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, current_user: dict = Depends(get_current_active_user)):
    """
    Get single project by ID
    
    **Requires Authentication** and project ownership
    """
    return await get_project_by_id(project_id, current_user)


@router.delete("/projects/{project_id}")
async def remove_project(project_id: str, current_user: dict = Depends(get_current_active_user)):
    """
    Delete project
    
    **Requires Authentication** and project ownership
    """
    return await delete_project(project_id, current_user)