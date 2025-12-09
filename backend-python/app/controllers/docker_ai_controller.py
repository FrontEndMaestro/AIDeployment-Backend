import os
import shutil
from typing import Dict, List, Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException

from ..LLM.docker_deploy_agent import run_docker_deploy_chat
from ..config.database import get_projects_collection
from ..config.settings import settings
from ..utils.auth import decode_access_token
from ..utils.file_system import read_file
from ..utils.detector import find_project_root

from ..services.docker_service import (
    build_project_stream,
    run_project_stream,
    push_image_stream,
)


async def _validate_project(project_id: str, current_user: dict) -> Dict:
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied: Not project owner")

    return project


def _safe_project_path(project: Dict) -> str:
    extracted_path = project.get("extracted_path") or settings.EXTRACTED_DIR
    real_path = os.path.abspath(extracted_path)
    if not os.path.exists(real_path):
        raise HTTPException(status_code=400, detail="Extracted project files not found")
    return real_path


async def _get_user_from_token(token: Optional[str]) -> Optional[Dict]:
    """
    Decode a JWT token and fetch the user document. Returns None if token is not provided.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=401, detail="Invalid token")
    collection = get_projects_collection().database.get_collection("users")
    user = await collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _collect_docker_files(project_root: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    dockerfiles: List[Dict[str, str]] = []
    compose_files: List[Dict[str, str]] = []

    targets = ["Dockerfile", "dockerfile"]
    compose_targets = ["docker-compose.yml", "docker-compose.yaml"]

    for root, _, files in os.walk(project_root):
        for name in files:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, project_root)

            if name in targets:
                content = read_file(full_path) or ""
                dockerfiles.append({"path": rel_path, "content": content})
            if name in compose_targets:
                content = read_file(full_path) or ""
                compose_files.append({"path": rel_path, "content": content})

    return dockerfiles, compose_files


def _build_file_tree(project_root: str, max_depth: int = 4, max_entries: int = 200) -> Tuple[str, List[Dict]]:
    """
    Returns a simple indented text tree for Llama context and a structured tree for the UI.
    """
    lines: List[str] = []
    structured: List[Dict] = []
    count = 0

    def walk(current: str, depth: int) -> Optional[List[Dict]]:
        nonlocal count
        if depth > max_depth or count >= max_entries:
            return []

        entries = []
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if count >= max_entries:
                        break
                    if entry.name.startswith(".") and entry.name not in [".env", ".env.example"]:
                        continue
                    count += 1
                    rel_path = os.path.relpath(entry.path, project_root)
                    prefix = "  " * depth + ("[dir] " if entry.is_dir() else "[file] ")
                    lines.append(f"{prefix}{rel_path}")

                    node = {
                        "name": entry.name,
                        "path": rel_path.replace("\\", "/"),
                        "is_dir": entry.is_dir(),
                    }
                    if entry.is_dir():
                        node["children"] = walk(entry.path, depth + 1)
                    entries.append(node)
        except Exception:
            return entries
        return entries

    structured = walk(project_root, 0) or []
    tree_text = "\n".join(lines)
    if count >= max_entries:
        tree_text += "\n...truncated"
    return tree_text, structured


def _ensure_analyzed(project: Dict):
    if project.get("status") not in ["analyzed", "completed"]:
        raise HTTPException(status_code=400, detail="Project must be analyzed before Docker deploy")


async def get_docker_context_handler(project_id: str, current_user: dict) -> Dict:
    project = await _validate_project(project_id, current_user)
    _ensure_analyzed(project)
    extracted_path = _safe_project_path(project)
    
    # Find the actual project root (handles subfolder structure like project-xxx/mern-blog-main)
    project_root = find_project_root(extracted_path)

    dockerfiles, compose_files = _collect_docker_files(extracted_path)
    file_tree_text, file_tree_struct = _build_file_tree(extracted_path)
    
    # Get stored metadata
    metadata = dict(project.get("metadata", {}))
    services = metadata.get("services", [])
    
    # =======================================================================
    # DYNAMIC ENV FILE DETECTION
    # Re-check for .env files on every page load to handle newly added files
    # =======================================================================
    print(f"🔍 Dynamic env_file check - project_root: {project_root}")
    print(f"🔍 Services to check: {services}")
    
    for svc in services:
        svc_path = svc.get("path", ".").rstrip("/\\")
        if svc_path == "." or not svc_path:
            svc_dir = project_root
        else:
            svc_dir = os.path.join(project_root, svc_path)
        
        print(f"🔍 Checking service '{svc.get('name')}' (type: {svc.get('type')}) at path: {svc_dir}")
        print(f"🔍   Current env_file value: {svc.get('env_file')}")
        
        # Check for .env file - always re-check even if previously None
        for env_name in [".env", ".env.local", ".env.production"]:
            env_path = os.path.join(svc_dir, env_name)
            exists = os.path.exists(env_path)
            print(f"🔍   Checking {env_path}: exists={exists}")
            if exists:
                svc["env_file"] = f"./{svc_path}/{env_name}" if svc_path and svc_path != "." else f"./{env_name}"
                print(f"✅ Dynamic env_file detected for {svc.get('name')}: {svc['env_file']}")
                break
    
    # Recalculate deploy_blocked based on current env_file status
    backend_services = [s for s in services if s.get("type") == "backend"]
    backend_missing_env = any(
        svc.get("type") == "backend" and not svc.get("env_file")
        for svc in services
    )
    
    if backend_services and backend_missing_env:
        metadata["deploy_blocked"] = True
        metadata["deploy_blocked_reason"] = (
            "Backend .env file is required for Docker deployment. "
            "Please add a .env file to your backend directory with your environment variables "
            "(e.g., DATABASE_URL, PORT, JWT_SECRET)."
        )
        metadata["backend_env_missing"] = True
    else:
        metadata["deploy_blocked"] = False
        metadata["deploy_blocked_reason"] = None
        metadata["backend_env_missing"] = False
    
    # Update services in metadata
    metadata["services"] = services

    return {
        "success": True,
        "project": {
            "id": str(project["_id"]),
            "project_name": project.get("project_name"),
            "status": project.get("status"),
        },
        "metadata": metadata,
        "dockerfiles": dockerfiles,
        "compose_files": compose_files,
        "file_tree": {
            "text": file_tree_text,
            "tree": file_tree_struct,
        },
        "docker_compose_present": bool(compose_files),
    }


async def docker_chat_handler(
    project_id: str,
    current_user: dict,
    user_message: str,
    logs: Optional[List[str]] = None,
    instructions: Optional[str] = None,
) -> Dict:
    project = await _validate_project(project_id, current_user)
    _ensure_analyzed(project)
    project_root = _safe_project_path(project)

    dockerfiles, compose_files = _collect_docker_files(project_root)
    file_tree_text, _ = _build_file_tree(project_root)
    metadata = project.get("metadata", {}) or {}
    services = metadata.get("services") or []

    # Dynamic env_file detection to ensure it's always up-to-date
    # (handles projects analyzed before env_file detection was implemented)
    for svc in services:
        svc_path = svc.get("path", ".").rstrip("/\\")  # Remove trailing slashes
        if svc_path == "." or not svc_path:
            svc_dir = project_root
        else:
            svc_dir = os.path.join(project_root, svc_path)
        
        # Dynamic env_file detection
        if not svc.get("env_file"):
            for env_name in [".env", ".env.local", ".env.production"]:
                env_path = os.path.join(svc_dir, env_name)
                if os.path.exists(env_path):
                    svc["env_file"] = f"./{svc_path}/{env_name}" if svc_path and svc_path != "." else f"./{env_name}"
                    print(f"🔧 Dynamic env_file detected for {svc.get('name')}: {svc['env_file']}")
                    break
        
        # Dynamic entry_point detection for backend services
        if svc.get("type") == "backend" and not svc.get("entry_point"):
            from ..utils.command_extractor import extract_nodejs_commands
            backend_cmds = extract_nodejs_commands(svc_dir)
            entry_point = backend_cmds.get("entry_point", "index.js")
            svc["entry_point"] = entry_point
            print(f"🔧 Dynamic entry_point detected for {svc.get('name')}: {entry_point}")
    
    # Debug: Print services to verify env_file and entry_point are present
    print(f"📦 Services being sent to LLM: {services}")

    reply = run_docker_deploy_chat(
        project_name=project.get("project_name", "project"),
        metadata=metadata,
        dockerfiles=dockerfiles,
        compose_files=compose_files,
        file_tree=file_tree_text,
        user_message=user_message,
        logs=logs,
        extra_instructions=instructions,
        services=services,
    )

    return {
        "success": True,
        "reply": reply,
        "model": "qwen2.5-coder",
        "dockerfiles_found": bool(dockerfiles),
        # Frontend should append ?action=build|run|push as needed
        "log_stream_base_url": f"/api/docker/{project_id}/logs",
    }


async def read_project_file_handler(
    project_id: str, current_user: dict, relative_path: str
) -> Dict:
    project = await _validate_project(project_id, current_user)
    project_root = _safe_project_path(project)

    normalized = os.path.abspath(os.path.join(project_root, relative_path))
    if not normalized.startswith(os.path.abspath(project_root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not os.path.exists(normalized):
        raise HTTPException(status_code=404, detail="File not found")

    # Read as binary then decode with replacement to avoid binary decode errors (e.g., favicon.ico)
    try:
        with open(normalized, "rb") as f:
            raw = f.read()
        content = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read file: {exc}")

    return {
        "success": True,
        "path": relative_path.replace("\\", "/"),
        "content": content,
    }


async def write_project_file_handler(
    project_id: str, current_user: dict, relative_path: str, content: str
) -> Dict:
    project = await _validate_project(project_id, current_user)
    project_root = _safe_project_path(project)

    normalized = os.path.abspath(os.path.join(project_root, relative_path))
    if not normalized.startswith(os.path.abspath(project_root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not relative_path.strip():
        raise HTTPException(status_code=400, detail="Path is required")

    try:
        os.makedirs(os.path.dirname(normalized), exist_ok=True)
        with open(normalized, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to write file: {exc}")

    return {"success": True, "path": relative_path.replace("\\", "/")}


async def create_project_folder_handler(
    project_id: str, current_user: dict, relative_path: str
) -> Dict:
    """
    Create a folder (and parents) under the project root.
    """
    project = await _validate_project(project_id, current_user)
    project_root = _safe_project_path(project)

    if not relative_path or not relative_path.strip():
        raise HTTPException(status_code=400, detail="Folder path is required")

    normalized = os.path.abspath(os.path.join(project_root, relative_path))
    if not normalized.startswith(os.path.abspath(project_root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    try:
        os.makedirs(normalized, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to create folder: {exc}")

    return {"success": True, "path": relative_path.replace("\\", "/")}


async def delete_project_path_handler(
    project_id: str, current_user: dict, relative_path: str
) -> Dict:
    """
    Delete a file or directory (recursively for directories) under the project root.
    """
    project = await _validate_project(project_id, current_user)
    project_root = _safe_project_path(project)

    if not relative_path or not relative_path.strip():
        raise HTTPException(status_code=400, detail="Path is required")

    normalized_root = os.path.abspath(project_root)
    normalized = os.path.abspath(os.path.join(project_root, relative_path))
    if not normalized.startswith(normalized_root):
        raise HTTPException(status_code=400, detail="Invalid path")

    if normalized == normalized_root:
        raise HTTPException(status_code=400, detail="Cannot delete project root")

    if not os.path.exists(normalized):
        raise HTTPException(status_code=404, detail="File or folder not found")

    try:
        if os.path.isdir(normalized):
            shutil.rmtree(normalized)
        else:
            os.remove(normalized)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete path: {exc}")

    return {"success": True, "path": relative_path.replace("\\", "/")}


async def stream_docker_logs_handler(
    project_id: str,
    action: str,
    token: Optional[str],
    authorization_header: Optional[str],
):
    bearer_token = token
    if not bearer_token and authorization_header:
        if authorization_header.lower().startswith("bearer "):
            bearer_token = authorization_header.split(" ", 1)[1].strip()

    user = await _get_user_from_token(bearer_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    project = await _validate_project(project_id, user)
    _ensure_analyzed(project)
    project_root = _safe_project_path(project)

    metadata = project.get("metadata", {}) or {}
    backend_host_port = metadata.get("backend_port") or metadata.get("port") or 8000

    # Build a canonical image repo for this project, namespaced by Docker Hub username if available
    hub_user = settings.DOCKER_HUB_USERNAME
    repo_prefix = settings.APP_REGISTRY_PREFIX or "devops-autopilot"
    
    # Use project_name instead of project_id for better readability
    # Sanitize project_name for Docker tag compatibility (lowercase, alphanumeric, dashes, underscores)
    project_name = project.get("project_name", "unnamed")
    import re
    sanitized_name = re.sub(r'[^a-z0-9_-]', '-', project_name.lower()).strip('-')
    # Limit length to avoid overly long image names
    sanitized_name = sanitized_name[:50] if len(sanitized_name) > 50 else sanitized_name

    if hub_user:
        # e.g. abdul/devops-autopilot-simplecart-js-master
        image_repo = f"{hub_user}/{repo_prefix}-{sanitized_name}"
    else:
        # fallback (local only)
        image_repo = f"{repo_prefix}-{sanitized_name}"

    if action == "build":
        generator = build_project_stream(project_root, image_repo, metadata)
    elif action == "run":
        generator = run_project_stream(project_root, image_repo, backend_host_port, metadata)
    elif action == "push":
        generator = push_image_stream(project_root, image_repo,metadata)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    return generator
