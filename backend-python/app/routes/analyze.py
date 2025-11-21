from fastapi import APIRouter, Query, Depends
from ..controllers.analyze_controller import (
    analyze_project_handler,
    get_analysis_results_handler,
    get_full_project_details_handler,
    get_project_metadata_handler,
    get_all_metadata_handler,
    get_metadata_statistics_handler,
    export_metadata_handler
)
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/analyze", tags=["Analyze"])


@router.post("/{project_id}")
async def analyze_project(
    project_id: str,
    force: bool = Query(False, description="Force re-analysis"),
    use_ml: bool = Query(True, description="Use ML-based detection"),
    current_user: dict = Depends(get_current_active_user)
):
    """Analyze project and detect framework"""
    return await analyze_project_handler(project_id, force, use_ml, current_user)


@router.get("/{project_id}")
async def get_analysis_results(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get analysis results for a project"""
    return await get_analysis_results_handler(project_id, current_user)


@router.get("/{project_id}/full")
async def get_full_details(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get complete project details"""
    return await get_full_project_details_handler(project_id, current_user)


@router.get("/{project_id}/metadata")
async def get_project_metadata(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get only metadata for a project
    
    Returns framework, language, dependencies, etc.
    """
    return await get_project_metadata_handler(project_id, current_user)


@router.get("/metadata/all")
async def get_all_metadata(
    framework: str = Query(None, description="Filter by framework"),
    language: str = Query(None, description="Filter by language"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get metadata for all analyzed projects with optional filters
    
    - **framework**: Filter by framework (e.g., Flask, Express.js)
    - **language**: Filter by language (e.g., Python, JavaScript)
    """
    return await get_all_metadata_handler(current_user, framework, language)


@router.get("/metadata/statistics")
async def get_metadata_statistics(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get statistics of all analyzed projects
    
    Returns framework distribution, language stats, Docker usage, etc.
    """
    return await get_metadata_statistics_handler(current_user)


@router.get("/{project_id}/export")
async def export_metadata(
    project_id: str,
    format: str = Query("json", description="Export format: json or yaml"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Export project metadata in different formats
    
    - **format**: json or yaml
    """
    return await export_metadata_handler(project_id, format, current_user)