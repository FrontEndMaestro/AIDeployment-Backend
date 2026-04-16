from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..controllers.docker_ai_controller import (
    create_project_folder_handler,
    delete_project_path_handler,
    docker_chat_handler,
    docker_chat_stream_setup,
    docker_chat_stream_generator,
    get_docker_context_handler,
    read_project_file_handler,
    stream_docker_logs_handler,
    write_project_file_handler,
)
from ..utils.auth import get_current_active_user, decode_access_token

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


@router.get("/{project_id}/chat/stream")
async def docker_chat_stream(
    project_id: str,
    request: Request,
    message: str = Query(..., description="User message for the Docker deploy chat"),
    logs: Optional[str] = Query(None, description="Newline-separated build/run logs"),
    instructions: Optional[str] = Query(None, description="Optional high-level deployment instructions"),
    token: Optional[str] = Query(None, description="Bearer token for EventSource auth"),
):
    """
    Stream LLM response as Server-Sent Events (SSE).
    Tokens are sent as they're generated for real-time display.
    """
    import json
    
    # Handle authentication (similar to logs endpoint)
    auth_header = request.headers.get("authorization")
    actual_token = token 
    if auth_header and auth_header.startswith("Bearer "):
        actual_token = auth_header.split(" ")[1]
    
    if not actual_token:
        def error_stream():
            yield f"data: {json.dumps({'error': 'Authentication required', 'done': True})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    # Decode token to get user
    payload = decode_access_token(actual_token)
    if not payload:
        def error_stream():
            yield f"data: {json.dumps({'error': 'Invalid token', 'done': True})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    current_user = {"_id": payload.get("sub"), "email": payload.get("email")}
    
    # Parse logs from query string (newline-separated)
    logs_list = logs.split("\n") if logs else None
    
    # First: run async setup (validation, data preparation)
    try:
        prepared_data = await docker_chat_stream_setup(
            project_id=project_id,
            current_user=current_user,
            user_message=message,
            logs=logs_list,
            instructions=instructions,
        )
    except Exception as e:
        def error_stream():
            yield f"data: {json.dumps({'token': f'Setup error: {str(e)}', 'done': True, 'error': True})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    # Then: use sync generator for streaming
    def event_stream():
        try:
            for chunk in docker_chat_stream_generator(prepared_data):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {str(e)}', 'done': True, 'error': True})}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
