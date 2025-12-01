from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..controllers.docker_ai_controller import (
    create_project_folder_handler,
    delete_project_path_handler,
    docker_chat_handler,
    get_docker_context_handler,
    read_project_file_handler,
    stream_docker_logs_handler,
    write_project_file_handler,
)
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/docker", tags=["Docker Deploy (Llama 3.1)"])


class DockerChatRequest(BaseModel):
    message: str = Field(..., description="User message for the Docker deploy chat")
    logs: Optional[List[str]] = Field(default=None, description="Recent build/run logs")
    instructions: Optional[str] = Field(
        default=None, description="Optional high-level deployment instructions"
    )

class WriteFileRequest(BaseModel):
    path: str
    content: str


class CreateFolderRequest(BaseModel):
    path: str


@router.get("/{project_id}/context")
async def docker_context(project_id: str, current_user: dict = Depends(get_current_active_user)):
    """
    Fetch Docker deploy context for a project:
    - detector metadata
    - discovered Dockerfiles / docker-compose
    - file tree (truncated)
    """
    return await get_docker_context_handler(project_id, current_user)


@router.post("/{project_id}/chat")
async def docker_chat(
    project_id: str,
    payload: DockerChatRequest = Body(...),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Send a message to the Docker deploy Llama 3.1 agent.
    """
    return await docker_chat_handler(
        project_id=project_id,
        current_user=current_user,
        user_message=payload.message,
        logs=payload.logs,
        instructions=payload.instructions,
    )


@router.get("/{project_id}/file")
async def read_project_file(
    project_id: str,
    path: str = Query(..., description="Relative path from project root"),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Read a project file (for the deploy file viewer).
    """
    return await read_project_file_handler(project_id, current_user, path)


@router.post("/{project_id}/file")
async def write_project_file(
    project_id: str,
    payload: WriteFileRequest = Body(...),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Write a project file (for editing in the deploy file viewer).
    """
    return await write_project_file_handler(project_id, current_user, payload.path, payload.content)


@router.post("/{project_id}/folder")
async def create_project_folder(
    project_id: str,
    payload: CreateFolderRequest = Body(...),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Create a folder (and parents) under the project root.
    """
    return await create_project_folder_handler(project_id, current_user, payload.path)


@router.delete("/{project_id}/path")
async def delete_project_path(
    project_id: str,
    path: str = Query(..., description="Relative path from project root to delete"),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Delete a file or directory (recursive) under the project root.
    """
    return await delete_project_path_handler(project_id, current_user, path)


@router.get("/{project_id}/logs")
async def stream_docker_logs(
    project_id: str,
    request: Request,
    action: str = Query(..., regex="^(build|run|push)$"),
    token: Optional[str] = Query(None, description="Optional bearer token for EventSource"),
):
    """
    Stream docker build/run logs as SSE.
    """
    auth_header = request.headers.get("authorization") if request else None
    generator = await stream_docker_logs_handler(project_id, action, token, auth_header)

    def event_stream():
        import json

        for event in generator:
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
