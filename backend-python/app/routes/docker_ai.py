from typing import List, Optional
import re
import json

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from ..LLM.docker_deploy_agent import parse_generated_docker_files, remap_generated_docker_paths, validate_generated_docker_files
from ..controllers.deployment_controller import deploy_project_handler
from ..controllers.deployment_readiness_controller import check_readiness_handler


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


# ─────────────────────────────────────────────────────────────────────────────
# Permissive file-block parser
# Understands all common LLM output formats:
#   **Gemfile** ```ruby ... ```
#   ### rails-api.gemspec ```ruby ... ```
#   Dockerfile ```dockerfile ... ```
#   `nginx.conf`:  ```nginx ... ```
# ─────────────────────────────────────────────────────────────────────────────
_FILENAME_CHARS = r"[\w\.\-/]+"

_FILE_BLOCK_PATTERNS = [
    # **filename** ```lang ... ```
    rf"\*\*(?P<path>{_FILENAME_CHARS})\*\*\s*```(?:[a-zA-Z0-9_\-]*)\n(?P<content>[\s\S]*?)```",
    # ### filename ```lang ... ```
    rf"(?:^|\n)#{1,3}\s*(?P<path>{_FILENAME_CHARS})\s*\n```(?:[a-zA-Z0-9_\-]*)\n(?P<content>[\s\S]*?)```",
    # `filename`: ```lang ... ```
    rf"`(?P<path>{_FILENAME_CHARS})`\s*:?\s*\n?```(?:[a-zA-Z0-9_\-]*)\n(?P<content>[\s\S]*?)```",
    # filename: ```lang ... ```   (no backticks, colon after name)
    rf"(?:^|\n)(?P<path>{_FILENAME_CHARS}):\s*\n```(?:[a-zA-Z0-9_\-]*)\n(?P<content>[\s\S]*?)```",
    # ```Filename\ncontent```  (filename as the lang tag)
    rf"```(?P<path>{_FILENAME_CHARS})\n(?P<content>[\s\S]*?)```",
]

# File extensions that are valid project files (never prose words)
_VALID_EXTENSIONS = {
    "", "rb", "gemspec", "gemfile", "lock", "yml", "yaml", "json", "js", "ts",
    "tsx", "jsx", "py", "go", "java", "kt", "swift", "rs", "sh", "env",
    "conf", "nginx", "toml", "cfg", "ini", "xml", "html", "css", "md",
    "dockerfile", "dockerignore", "gitignore", "txt", "sql",
}

# Known filenames with no extension
_KNOWN_BARE_NAMES = {
    "dockerfile", "gemfile", "makefile", "rakefile", "procfile",
    "vagrantfile", "jenkinsfile", "caddyfile", ".env", ".gitignore",
    ".dockerignore",
}


def _parse_any_file_blocks(text: str) -> dict:
    """
    Extract ALL filename + code-block pairs from LLM output.
    Returns {relative_path: content}.
    """
    found: dict = {}
    for pattern in _FILE_BLOCK_PATTERNS:
        for m in re.finditer(pattern, text or "", re.IGNORECASE | re.MULTILINE):
            raw_path = m.group("path").strip().strip("`*# ")
            content  = (m.group("content") or "").strip()
            if not raw_path or not content:
                continue

            # Normalise path
            path = re.sub(r"^[./\\]+", "", raw_path).replace("\\", "/")
            if not path:
                continue

            # Accept if it's a known bare name or has a recognised extension
            base = path.split("/")[-1].lower()
            ext  = base.rsplit(".", 1)[-1] if "." in base else ""
            if base not in _KNOWN_BARE_NAMES and ext not in _VALID_EXTENSIONS:
                continue  # skip prose words caught by the regex

            if path not in found:          # first match wins
                found[path] = content
                print(f"🔎 _parse_any_file_blocks: found '{path}' ({len(content)} chars)")

    return found




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
    - discovered Dockerfiles / docker-compose / k8s manifests
    - deployment readiness status
    - file tree (truncated)
    """
    return await get_docker_context_handler(project_id, current_user)


@router.get("/{project_id}/check-readiness")
async def check_deployment_readiness(
    project_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """
    Scan the project for all deployment-critical files:
    Dockerfile, docker-compose.yml, k8s manifests, .env.
    Any missing files are auto-generated by Gemini and saved to the project directory.
    Returns a structured readiness report.
    """
    return await check_readiness_handler(project_id, current_user)


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
    model: Optional[str] = Query(None, description="Gemini model to use (overrides default)"),
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
            model_override=model,
        )
    except Exception as e:
        def error_stream():
            yield f"data: {json.dumps({'token': f'Setup error: {str(e)}', 'done': True, 'error': True})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    # Then: use sync generator for streaming
    stream_context = {"full_text": ""}
    
    def event_stream():
        try:
            for chunk in docker_chat_stream_generator(prepared_data):
                if "token" in chunk:
                    stream_context["full_text"] += chunk["token"]
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {str(e)}', 'done': True, 'error': True})}\n\n"

    async def post_chat_action():
        full_text = stream_context.get("full_text", "")
        if not full_text.strip():
            return

        print("🔄 Auto-Healing: Parsing LLM output for files...")

        # ── PASS 1: Docker files (Dockerfile / docker-compose) ─────────────
        # Exact same pipeline as the original working code.
        docker_files = parse_generated_docker_files(full_text)
        docker_files = remap_generated_docker_paths(
            docker_files,
            prepared_data.get("metadata", {}),
            prepared_data.get("services", []),
        )

        if docker_files:
            has_dockerfile = any(
                path.replace("\\", "/").split("/")[-1].lower() == "dockerfile"
                for path in docker_files
            )
            has_compose = any(
                path.replace("\\", "/").split("/")[-1].lower()
                in {"docker-compose.yml", "docker-compose.yaml"}
                for path in docker_files
            )

            skip_docker = False
            if has_dockerfile or has_compose:
                validation_errors = validate_generated_docker_files(
                    files=docker_files,
                    metadata=prepared_data.get("metadata", {}),
                    services=prepared_data.get("services", []),
                    require_dockerfiles=has_dockerfile,
                    require_compose=has_compose,
                )
                if validation_errors:
                    print("⚠️  Docker validation errors — skipping Docker files:")
                    for err in validation_errors:
                        print(f"  - {err}")
                    skip_docker = True

            if not skip_docker:
                for file_path, content in docker_files.items():
                    try:
                        await write_project_file_handler(project_id, current_user, file_path, content)
                        print(f"✅ Auto-Healing: Wrote {file_path}")
                    except Exception as e:
                        print(f"❌ Auto-Healing failed to write {file_path}: {e}")

        # ── PASS 2: Any other project file (Gemfile, gemspec, package.json…) ─
        # Permissive parser, no Docker validation, never double-writes PASS 1 files.
        other_files = _parse_any_file_blocks(full_text)
        docker_basenames = {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
        for file_path, content in other_files.items():
            base = file_path.replace("\\", "/").split("/")[-1].lower()
            if base in docker_basenames:
                continue  # handled (or skipped) by PASS 1
            if file_path in docker_files:
                continue  # already written by PASS 1
            try:
                await write_project_file_handler(project_id, current_user, file_path, content)
                print(f"✅ Auto-Healing: Rewrote {file_path}")
            except Exception as e:
                print(f"❌ Auto-Healing failed to write {file_path}: {e}")

        # Auto-trigger deployment if prompt requested it
        if "deploy" in message.lower():
            print("🚀 Auto-Deploying based on user chat...")
            try:
                await deploy_project_handler(project_id, current_user)
                print("✅ Auto-Deploy successful!")
            except Exception as e:
                print(f"❌ Auto-Deploy failed: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        background=BackgroundTask(post_chat_action)
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
    action: str = Query(..., regex="^(build|run|push|k8s_deploy)$"),
    token: Optional[str] = Query(None, description="Optional bearer token for EventSource"),
):
    """
    Stream docker build/run/push/k8s_deploy logs as SSE.
    """
    auth_header = request.headers.get("authorization") if request else None
    generator = await stream_docker_logs_handler(project_id, action, token, auth_header)

    def event_stream():
        import json

        for event in generator:
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
