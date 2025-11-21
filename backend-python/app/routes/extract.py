from fastapi import APIRouter, Depends
from ..controllers.extract_controller import (
    extract_project_handler,
    get_extracted_files_handler,
    get_extraction_status_handler,
    cleanup_extraction_handler
)
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/extract", tags=["Extract"])


@router.post("/{project_id}")
async def extract_project(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Extract uploaded project
    
    **Requires Authentication** and project ownership
    """
    return await extract_project_handler(project_id, current_user)


@router.get("/{project_id}/files")
async def get_extracted_files(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of extracted files
    
    **Requires Authentication** and project ownership
    """
    return await get_extracted_files_handler(project_id, current_user)


@router.get("/{project_id}/status")
async def get_extraction_status(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get extraction status
    
    **Requires Authentication** and project ownership
    """
    return await get_extraction_status_handler(project_id, current_user)


@router.delete("/{project_id}/cleanup")
async def cleanup_extraction(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Cleanup extracted files
    
    **Requires Authentication** and project ownership
    """
    return await cleanup_extraction_handler(project_id, current_user)