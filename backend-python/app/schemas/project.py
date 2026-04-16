from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ProjectUploadResponse(BaseModel):
    success: bool
    message: str
    data: dict


class ProjectResponse(BaseModel):
    project_id: str
    project_name: str
    file_name: str
    file_size: str
    upload_date: datetime
    status: str


class ProjectListResponse(BaseModel):
    success: bool
    count: int
    projects: List[dict]


class ExtractionResponse(BaseModel):
    success: bool
    message: str
    data: dict


class AnalysisResponse(BaseModel):
    success: bool
    message: str
    data: dict


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: Optional[str] = None


def format_file_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"