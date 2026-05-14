import re
from typing import Optional


def sanitize_project_image_name(project_name: Optional[str]) -> str:
    raw_name = project_name if project_name is not None else "unnamed"
    sanitized = re.sub(r"[^a-z0-9_-]", "-", str(raw_name).lower()).strip("-")
    return sanitized[:50] if len(sanitized) > 50 else sanitized


def build_project_image_repo(
    project_name: Optional[str],
    namespace: Optional[str],
    registry_prefix: Optional[str],
) -> str:
    prefix = registry_prefix or "devops-autopilot"
    project_repo = f"{prefix}-{sanitize_project_image_name(project_name)}"
    clean_namespace = (namespace or "").strip().strip("/")
    if not clean_namespace:
        return project_repo
    if clean_namespace.rsplit("/", 1)[-1] == project_repo:
        return clean_namespace
    return f"{clean_namespace}/{project_repo}"


def build_service_image(image_repo: str, service_name: str) -> str:
    return f"{image_repo}-{str(service_name or 'app').lower()}:latest"
