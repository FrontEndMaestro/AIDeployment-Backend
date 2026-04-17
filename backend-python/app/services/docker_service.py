import os
import subprocess
from typing import Dict, Generator, List, Optional
import yaml
import json 

from ..LLM.docker_deploy_agent import (
    parse_and_validate_generated_docker_response,
    run_docker_deploy_chat,
    run_k8s_manifest_generation,
)

from ..config.settings import settings


# --------- helpers to discover compose + Dockerfiles ---------

_DB_TOKENS = {"mongo", "postgres", "postgresql", "mysql", "mariadb", "redis", "sqlite", "database", "db"}


def _is_database_service(service_name: str, image_name: str) -> bool:
    """Return True if this compose service is a database (should not be pushed to DockerHub)."""
    combined = f"{service_name} {image_name}".lower()
    return any(token in combined for token in _DB_TOKENS)


def _infer_compose_image_name(compose_dir: str, service_name: str) -> str:
    """
    Derive the docker compose auto-generated image name for a service with build: but no image:.
    Docker names these as: {project_name}-{service_name}
    where project_name = lowercase directory name, spaces/hyphens → underscores not applied
    (Docker actually uses the folder name lowercased with non-alphanums replaced by hyphens).
    """
    folder = os.path.basename(compose_dir) or "project"
    # Docker compose project naming: lowercase, non-alphanumeric → hyphen, then collapse
    import re as _re
    project = _re.sub(r"[^a-z0-9]", "-", folder.lower()).strip("-")
    project = _re.sub(r"-+", "-", project)
    # Compose image name = {project}-{service}
    return f"{project}-{service_name}"

def _docker_login(stage: str) -> Generator[Dict, None, None]:
    """
    If DOCKER_HUB_USERNAME / DOCKER_HUB_PASSWORD are set, perform
    `docker login` and yield log lines as SSE events.

    Caller is responsible for inspecting the final event's exit_code
    and aborting if login failed.
    """
    username = settings.DOCKER_HUB_USERNAME
    password = settings.DOCKER_HUB_PASSWORD

    if not username or not password:
        # No credentials configured => nothing to do
        return

    yield {
        "line": f"Attempting docker login as '{username}'...",
        "stage": stage,
    }

    login_proc = subprocess.Popen(
        ["docker", "login", "-u", username, "--password-stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    if login_proc.stdin:
        login_proc.stdin.write(password + "\n")
        login_proc.stdin.flush()
        login_proc.stdin.close()

    last_line: Optional[Dict] = None
    for line in login_proc.stdout or []:
        last_line = {"line": line.rstrip("\n"), "stage": stage}
        yield last_line

    login_proc.wait()
    final_event = {
        "line": f"{stage} login exited with code {login_proc.returncode}",
        "stage": stage,
        "exit_code": login_proc.returncode,
        "complete": False,  # caller will decide whether to abort
    }
    yield final_event


def _find_compose_file(project_root: str) -> Optional[str]:
    """
    Find a docker-compose file under the project root.
    Prefer a root-level one; fall back to the first found.
    Returns absolute path or None.
    """
    candidates: List[str] = []

    for root, _, files in os.walk(project_root):
        for name in ("docker-compose.yml", "docker-compose.yaml"):
            if name in files:
                full = os.path.join(root, name)
                candidates.append(full)

    if not candidates:
        return None

    # prefer root-level compose if present
    for full in candidates:
        rel = os.path.relpath(full, project_root).replace("\\", "/")
        if "/" not in rel:
            return full

    # else just take the first
    return candidates[0]


def _find_all_dockerfiles(project_root: str) -> List[str]:
    """
    Return a list of Dockerfile *relative paths* under project_root.
    E.g. ["Dockerfile", "client/Dockerfile", "server/Dockerfile"]
    """
    dockerfiles: List[str] = []
    for root, _, files in os.walk(project_root):
        for name in files:
            if name.lower() == "dockerfile":
                full = os.path.join(root, name)
                rel = os.path.relpath(full, project_root)
                dockerfiles.append(rel.replace("\\", "/"))
    return dockerfiles


def _write_generated_files(project_root: str, files: Dict[str, str]) -> List[str]:
    """Write validated generated files under project_root only."""
    root_abs = os.path.abspath(project_root)
    written: List[str] = []
    for rel_path, content in files.items():
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        if clean_rel.startswith("../") or clean_rel == "..":
            raise ValueError(f"Unsafe generated path: {rel_path}")
        dest = os.path.abspath(os.path.join(root_abs, clean_rel))
        if os.path.commonpath([root_abs, dest]) != root_abs:
            raise ValueError(f"Generated path escapes project root: {rel_path}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content.rstrip() + "\n")
        written.append(clean_rel)
    return written


# --------- core command streamer (SSE-compatible) ---------


def _stream_command(cmd: List[str], cwd: str, stage: str) -> Generator[Dict, None, None]:
    """
    Run a command and yield log events as dictionaries for SSE.
    """
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    collected: List[str] = []

    try:
        if process.stdout:
            for line in process.stdout:
                clean = line.rstrip("\n")
                collected.append(clean)
                yield {"line": clean, "stage": stage}
    finally:
        process.wait()
        exit_code = process.returncode
        tail = collected[-50:]
        yield {
            "line": f"{stage} exited with code {exit_code}",
            "stage": stage,
            "exit_code": exit_code,
            "complete": True,
            "tail": tail,
        }


def _tag_and_push(
    source_image: str,
    dest_image: str,
    cwd: str,
) -> Generator[Dict, None, None]:
    """
    Tag source_image as dest_image, then docker push dest_image,
    yielding logs as SSE-style dicts.
    """
    # docker tag
    tag_cmd = ["docker", "tag", source_image, dest_image]
    yield {
        "line": f"Tagging {source_image} -> {dest_image}",
        "stage": "push",
    }
    for event in _stream_command(tag_cmd, cwd=cwd, stage="push"):
        yield event
        if event.get("complete") and event.get("exit_code", 0) != 0:
            return  # tagging failed; abort

    # docker push
    push_cmd = ["docker", "push", dest_image]
    yield {
        "line": f"Pushing {dest_image}",
        "stage": "push",
    }
    for event in _stream_command(push_cmd, cwd=cwd, stage="push"):
        yield event


# --------- external network preflight for compose ---------


def ensure_external_networks(compose_path: str, stage: str) -> List[Dict]:
    """
    Ensure external networks declared in docker-compose exist.
    Returns a list of log dicts to yield before running compose commands.
    """
    events: List[Dict] = []
    if yaml is None or not os.path.exists(compose_path):
        return events

    try:
        with open(compose_path, "r", encoding="utf-8", errors="ignore") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        events.append({"line": f"Skipping external network preflight (parse error: {e})", "stage": stage})
        return events

    networks = data.get("networks", {}) or {}
    external_names: List[str] = []

    for name, cfg in networks.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("external") is True:
            net_name = cfg.get("name") or name
            if net_name:
                external_names.append(str(net_name))

    for net in external_names:
        events.append({"line": f"Checking external network '{net}'", "stage": stage})
        inspect = subprocess.run(
            ["docker", "network", "inspect", net],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if inspect.returncode == 0:
            events.append({"line": f"External network '{net}' exists", "stage": stage})
            continue
        events.append({"line": f"External network '{net}' missing; creating...", "stage": stage})
        create = subprocess.run(
            ["docker", "network", "create", net],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if create.returncode == 0:
            events.append({"line": f"Created external network '{net}'", "stage": stage})
        else:
            events.append({
                "line": f"Failed to create external network '{net}': {create.stderr.strip()}",
                "stage": stage,
                "exit_code": create.returncode,
            })
    return events


# --------- BUILD: whole project (compose OR all Dockerfiles) ---------


def build_project_stream(
    project_root: str,
    image_repo: str,  # e.g. "devops-autopilot-<project_id>" or "abdul/devops-autopilot-<project_id>"
    metadata: Optional[Dict] = None,
) -> Generator[Dict, None, None]:
    """
    High-level build for the whole project.

    - If a docker-compose file exists:
        `docker compose build` in that directory (builds ALL services defined there).
    - Else:
        Build all discovered Dockerfiles one by one, tagging them as:
            {image_repo}-{service_name}:latest

        Canonical tagging rule:
        - If exactly 1 image is built => also tag it as {image_repo}:latest
        - If more than 1 image is built => DO NOT create {image_repo}:latest
    """
    _ensure_compose_env_files(project_root)

    # ---- Login BEFORE any build so private base images can be pulled ----
    last_login_event: Optional[Dict] = None
    for event in _docker_login("build"):
        last_login_event = event
        yield event

    if last_login_event and last_login_event.get("exit_code", 0) != 0:
        # Abort build if login failed
        msg = "Aborting build because docker login failed."
        yield {
            "line": msg,
            "stage": "build",
            "exit_code": last_login_event.get("exit_code", 1),
            "complete": True,
            "tail": [msg],
        }
        return

    # ---- Compose-based build ----
    compose_path = _find_compose_file(project_root)
    if compose_path:
        compose_dir = os.path.dirname(compose_path)
        compose_file = os.path.basename(compose_path)

        for ev in ensure_external_networks(compose_path, "build"):
            yield ev

        cmd = ["docker", "compose", "-f", compose_file, "build"]

        rel_compose = os.path.relpath(compose_path, project_root).replace("\\", "/")
        yield {
            "line": f"Using compose file: {rel_compose}",
            "stage": "build",
        }
        yield {
            "line": f"Running: {' '.join(cmd)} (cwd={compose_dir})",
            "stage": "build",
        }

        for event in _stream_command(cmd, cwd=compose_dir, stage="build"):
            yield event
        return

    # ---- No compose: build all Dockerfiles ----
    dockerfiles = _find_all_dockerfiles(project_root)
    if not dockerfiles:
        # Always attempt auto-generation — even if services list is empty
        services = (metadata or {}).get("services", [])
        yield {
            "line": "No Dockerfiles found. Auto-generating deployment files via Gemini AI...",
            "stage": "build",
        }

        try:
            file_tree = _build_file_tree_text(project_root)
            source_files = _collect_source_files_for_llm(project_root)
            project_name = os.path.basename(project_root) or "project"

            yield {"line": f"Analyzing {len(source_files)} source file(s) for context...", "stage": "build"}

            # Call Agent in GENERATE_MISSING mode
            llm_response = run_docker_deploy_chat(
                project_name=project_name,
                metadata=metadata or {},
                dockerfiles=[],
                compose_files=[],
                source_files=source_files,
                file_tree=file_tree,
                user_message=(
                    "Analyze the source files and generate ALL Docker files needed:\n"
                    "1. A Dockerfile for every service directory\n"
                    "2. A docker-compose.yml at the project root\n"
                    "Use the actual files to detect ports, entry points, and dependencies. "
                    "Do NOT use placeholders — use real values from the code."
                ),
                logs=None,
                extra_instructions=None,
                services=services,
            )

            generated_files, validation_errors = parse_and_validate_generated_docker_response(
                llm_response,
                metadata or {},
                services,
                require_dockerfiles=True,
                require_compose=True,
            )

            if validation_errors:
                yield {
                    "line": f"Generated Docker files have {len(validation_errors)} issue(s). Requesting auto-repair...",
                    "stage": "build",
                }
                repair_response = run_docker_deploy_chat(
                    project_name=project_name,
                    metadata=metadata or {},
                    dockerfiles=[],
                    compose_files=[],
                    source_files=source_files,
                    file_tree=file_tree,
                    user_message=(
                        "Regenerate complete Docker files. Fix these validation errors:\\n"
                        + "\\n".join(f"- {err}" for err in validation_errors)
                    ),
                    logs=validation_errors,
                    extra_instructions=f"Previous invalid response:\n{llm_response[:4000]}",
                    services=services,
                )
                generated_files, validation_errors = parse_and_validate_generated_docker_response(
                    repair_response,
                    metadata or {},
                    services,
                    require_dockerfiles=True,
                    require_compose=True,
                )

            if validation_errors:
                msg = (
                    "ERROR: Agent did not produce valid Docker files:\n"
                    + "\n".join(f"- {err}" for err in validation_errors)
                )
                yield {
                    "line": msg,
                    "stage": "build",
                    "exit_code": 1,
                    "complete": True,
                    "tail": validation_errors,
                }
                return

            written_files = _write_generated_files(project_root, generated_files)
            for rel_path in written_files:
                yield {"line": f"\u2705 Generated {rel_path}", "stage": "build"}

            # If a compose file was generated, use it to build
            compose_generated = any(
                "docker-compose" in k for k in generated_files
            )
            if compose_generated:
                yield {"line": "Using generated docker-compose.yml for build...", "stage": "build"}
                cmd = ["docker", "compose", "-f", "docker-compose.yml", "build"]
                for event in _stream_command(cmd, cwd=project_root, stage="build"):
                    yield event
                return

            dockerfiles = _find_all_dockerfiles(project_root)

        except Exception as e:
            yield {
                "line": f"ERROR: Auto-generation failed: {e}",
                "stage": "build",
                "exit_code": 1,
                "complete": True,
                "tail": [str(e)],
            }
            return

        # If still no dockerfiles after generation
        if not dockerfiles:
            msg = "ERROR: Auto-generation did not produce any buildable files. Please check the project structure."
            yield {
                "line": msg,
                "stage": "build",
                "exit_code": 1,
                "complete": True,
                "tail": [msg],
            }
            return

    yield {
        "line": f"No docker-compose.yml found. Building all Dockerfiles ({len(dockerfiles)}) sequentially.",
        "stage": "build",
    }

    built_images: List[str] = []

    for rel in dockerfiles:
        # derive a simple service name from path
        path_parts = rel.split("/")
        if len(path_parts) == 1:
            service_name = "root"
        else:
            service_name = path_parts[-2] or "root"

        # e.g. abdul/devops-autopilot-<project_id>-server:latest
        service_image = f"{image_repo}-{service_name}:latest"

        full = os.path.join(project_root, rel)
        build_context_dir = os.path.dirname(full) or project_root
        dockerfile_name = os.path.basename(full)

        cmd = ["docker", "build", "-t", service_image]
        if dockerfile_name != "Dockerfile":
            cmd.extend(["-f", dockerfile_name])
        cmd.append(".")

        yield {"line": f"=== Building Dockerfile {rel} as image {service_image} ===", "stage": "build"}
        yield {
            "line": f"Running: {' '.join(cmd)} (cwd={build_context_dir})",
            "stage": "build",
        }

        last_event: Optional[Dict] = None
        for event in _stream_command(cmd, cwd=build_context_dir, stage="build"):
            last_event = event
            yield event

        # stop on first failing Dockerfile
        if last_event and last_event.get("complete") and last_event.get("exit_code", 0) != 0:
            fail_msg = f"ERROR: Build failed for {rel} (image {service_image}). Stopping."
            yield {
                "line": fail_msg,
                "stage": "build",
                "exit_code": last_event.get("exit_code", 1),
                "complete": True,
                "tail": (last_event.get("tail") or []) + [fail_msg],
            }
            return

        built_images.append(service_image)

    # ---- Canonical tag logic (non-compose projects) ----
    if len(built_images) == 1:
        only_image = built_images[0]
        alias_tag = f"{image_repo}:latest"
        tag_cmd = ["docker", "tag", only_image, alias_tag]
        yield {
            "line": f"Tagging single built image {only_image} as canonical {alias_tag}",
            "stage": "build",
        }
        for event in _stream_command(tag_cmd, cwd=project_root, stage="build"):
            yield event
    elif len(built_images) > 1:
        yield {
            "line": f"Multiple images built ({len(built_images)}). Skipping canonical {image_repo}:latest tag.",
            "stage": "build",
        }


def _derive_service_name_from_path(rel_path: str) -> str:
    """
    Infer a service name from a Dockerfile path.
    e.g. 'frontend/Dockerfile' -> 'frontend'
         'backend/api/Dockerfile' -> 'api'
         'Dockerfile' -> 'app'
    """
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) == 1:
        return "app"
    # last dir name before 'Dockerfile'
    return parts[-2] or "app"


def _infer_role_from_name(service_name: str) -> str:
    """
    Very light heuristic: frontend / backend / generic service.
    """
    name = service_name.lower()
    if any(k in name for k in ("front", "client", "web", "ui")):
        return "frontend"
    if any(k in name for k in ("back", "api", "server")):
        return "backend"
    return "service"


def _analyze_dockerfile(dockerfile_path: str) -> Dict:
    """
    Parse a Dockerfile to detect:
    - base images (FROM ...)
    - rough tech hints

    NOTE: We do NOT infer ports here; ports come from detector metadata
    (docker_*_ports, docker_*_container_ports, etc.).
    """
    base_images: List[str] = []
    tech_tags: List[str] = []

    try:
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return {"base_images": [], "tech_tags": []}

    for line in lines:
        stripped = line.strip()

        # FROM node:18-alpine
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                base_images.append(parts[1].lower())

    # very rough tech inference
    for img in base_images:
        if "node" in img:
            tech_tags.append("Node.js")
        if "nginx" in img:
            tech_tags.append("Nginx")
        if "python" in img:
            tech_tags.append("Python")
        if "alpine" in img:
            tech_tags.append("Alpine Linux")
        if "redis" in img:
            tech_tags.append("Redis")
        if "postgres" in img or "postgis" in img:
            tech_tags.append("PostgreSQL")
        if "mongo" in img:
            tech_tags.append("MongoDB")

    tech_tags = sorted(set(tech_tags))
    base_images = sorted(set(base_images))

    return {"base_images": base_images, "tech_tags": tech_tags}


def _normalize_ports(value) -> List[int]:
    """
    Normalize metadata port fields into a list[int].
    Accepts: int, str, list[int/str], None.
    """
    if value is None:
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        # comma- or space-separated, be generous
        parts = [p.strip() for p in value.replace(",", " ").split()]
        return [int(p) for p in parts if p.isdigit()]

    if isinstance(value, (list, tuple)):
        out: List[int] = []
        for v in value:
            if isinstance(v, int):
                out.append(v)
            elif isinstance(v, str) and v.strip().isdigit():
                out.append(int(v.strip()))
        return out

    return []


def _get_role_ports_from_metadata(metadata: Optional[Dict], role: str) -> List[int]:
    """
    Use detector metadata as the authoritative source of container ports
    per role (backend/frontend/other).

    metadata typically contains:
      - docker_backend_ports, docker_backend_container_ports
      - docker_frontend_ports, docker_frontend_container_ports
      - docker_other_ports, docker_other_container_ports
      - docker_expose_ports
      - port, backend_port, frontend_port

    We normalize all of these and return a merged, de-duplicated list.
    """
    if not metadata:
        return []

    role = role.lower()
    fields: List[str] = []

    if role == "backend":
        fields = [
            "backend_container_port",
            "docker_backend_container_ports",
            "docker_backend_ports",
            "backend_runtime_port",
            "backend_port",
            "port",
        ]
    elif role == "frontend":
        fields = [
            "frontend_container_port",
            "docker_frontend_container_ports",
            "docker_frontend_ports",
            "frontend_runtime_port",
            "frontend_port",
        ]
    else:
        fields = [
            "docker_other_container_ports",
            "docker_other_ports",
            "docker_expose_ports",
        ]

    ports: List[int] = []
    for field in fields:
        if field in metadata:
            ports.extend(_normalize_ports(metadata.get(field)))

    # dedupe while preserving order
    seen = set()
    result: List[int] = []
    for p in ports:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _get_tech_tags_from_metadata(metadata: Optional[Dict]) -> List[str]:
    """
    Derive high-level tech stack hints from detector metadata.

    Uses:
      - language
      - framework
      - dependencies
      - database / databases
    """
    if not metadata:
        return []

    tags: List[str] = []

    language = (metadata.get("language") or "").strip()
    framework = (metadata.get("framework") or "").strip()
    database = (metadata.get("database") or "").strip()
    databases = metadata.get("databases") or []

    deps = [str(d).lower() for d in (metadata.get("dependencies") or [])]

    # Language / framework core
    if language:
        tags.append(language)
    if framework and framework.lower() != "unknown":
        tags.append(framework)

        # Role-ish tags based on framework
        fw_lower = framework.lower()
        if fw_lower in ("react", "next.js", "nextjs", "vue", "angular"):
            tags.append("Frontend")
        if fw_lower in ("flask", "django", "fastapi", "express.js", "express", "spring boot", "rails", "laravel"):
            tags.append("Backend")

    # Dependency-based hints
    # (You can extend this list over time)
    dep_map = {
        "react": "React",
        "next": "Next.js",
        "vite": "Vite",
        "express": "Express.js",
        "fastify": "Fastify",
        "nestjs": "NestJS",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "spring-boot": "Spring Boot",
        "spring boot": "Spring Boot",
        "laravel": "Laravel",
        "rails": "Rails",
        "prisma": "Prisma",
        "typeorm": "TypeORM",
        "sequelize": "Sequelize ORM",
    }

    for dep in deps:
        for needle, tag in dep_map.items():
            if needle in dep:
                tags.append(tag)

    # Database hints
    if database and database.lower() != "unknown":
        tags.append(database)
    for db in databases:
        db_str = str(db).strip()
        if db_str and db_str.lower() != "unknown":
            tags.append(db_str)

    # De-duplicate while preserving order
    seen = set()
    result: List[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)

    return result


def _build_compose_generation_prompt(
    project_root: str,
    dockerfile_rel_paths: List[str],
    backend_host_port: int,
    metadata: Optional[Dict] = None,
) -> str:
    """
    Build a detailed prompt for Llama 3.1 to generate docker-compose.yml
    for multi-Dockerfile projects with no existing compose.

    Ports and high-level tech hints are taken from detector metadata.
    Dockerfile analysis only adds per-service base-image hints.
    """
    # --- Metadata summary / hints ---
    meta_bits: List[str] = []
    if metadata:
        if metadata.get("framework"):
            meta_bits.append(f"framework={metadata['framework']}")
        if metadata.get("language"):
            meta_bits.append(f"language={metadata['language']}")
        if metadata.get("runtime"):
            meta_bits.append(f"runtime={metadata['runtime']}")
        if metadata.get("database"):
            meta_bits.append(f"database={metadata['database']}")
    meta_summary = ", ".join(meta_bits) if meta_bits else "unknown"

    # Global role-based port hints from metadata
    backend_ports_meta = _get_role_ports_from_metadata(metadata, "backend")
    frontend_ports_meta = _get_role_ports_from_metadata(metadata, "frontend")
    other_ports_meta = _get_role_ports_from_metadata(metadata, "other")

    # Global tech tags from metadata (language/framework/deps/db)
    meta_tech_tags = _get_tech_tags_from_metadata(metadata)

    service_lines: List[str] = []
    docker_tech_tags: List[str] = []

    for rel in dockerfile_rel_paths:
        abs_path = os.path.join(project_root, rel)
        info = _analyze_dockerfile(abs_path)  # base_images + tech_tags (from base image name)
        service_name = _derive_service_name_from_path(rel)
        role = _infer_role_from_name(service_name)

        base_images = info["base_images"]
        tech_tags = info["tech_tags"]
        docker_tech_tags.extend(tech_tags)

        # Role-based ports from metadata
        if role == "frontend":
            role_ports = frontend_ports_meta
        elif role == "backend":
            role_ports = backend_ports_meta
        else:
            role_ports = other_ports_meta

        service_lines.append(
            f"- service_name: {service_name}\n"
            f"  dockerfile: {rel}\n"
            f"  role: {role}\n"
            f"  metadata_ports_for_role: {role_ports or '[]'}\n"
            f"  base_images: {base_images or '[]'}\n"
            f"  dockerfile_tech_tags: {tech_tags or '[]'}"
        )

    # Merge metadata tech tags + Docker-image-based hints
    combined_tech_tags = []
    seen_tag = set()
    for t in (meta_tech_tags + docker_tech_tags):
        if t not in seen_tag:
            seen_tag.add(t)
            combined_tech_tags.append(t)

    composed_stack = " / ".join(combined_tech_tags) if combined_tech_tags else "unknown"

    prompt = f"""
You are an expert DevOps engineer.

Generate a **production-ready docker-compose.yml** for a multi-service project
that currently has multiple Dockerfiles but no compose file.

Important constraints:

- Use compose version "3.9".
- Use ONLY the provided `service_name` values as keys under `services:`. Do not invent new ones.
- Each service MUST use a `build` section with:
  - `context`: the directory containing its Dockerfile.
  - `dockerfile`: the relative Dockerfile name (usually "Dockerfile").
- Ports (use the metadata-based hints provided for each role):
  - For role=frontend services:
    - Expose them on host port 3000 or 8080, mapped to their main container port.
    - Prefer container ports from `metadata_ports_for_role` if present,
      otherwise pick a reasonable web port (3000, 8080, 80).
  - For role=backend services:
    - Expose them on host port {backend_host_port}, mapped to their main container port.
    - Prefer container ports from `metadata_ports_for_role` if present,
      otherwise pick a reasonable backend port (e.g. 8000).
- Networking:
  - All services must be on the same default network.
  - Ensure they can talk to each other via service names
    (e.g. http://backend:{backend_host_port}).
- Volumes:
  - DO NOT use bind mounts to host paths (no "./data:/db" or similar).
  - If you need persistence, use named volumes only.
- Environment:
  - Avoid external `env_file` references. Prefer inline `environment:` for essential config.
- Images:
  - It's OK if you omit explicit `image:` fields and rely only on `build:`; Docker Compose will generate image names.
- Output:
  - Return ONLY raw YAML for docker-compose.yml.
  - NO markdown fences, NO backticks, NO commentary.

Detected overall tech stack (combined from metadata + Dockerfiles): {composed_stack}
Metadata from analyzer (approximate): {meta_summary}

Global metadata-based ports:
- backend_ports_meta: {backend_ports_meta or '[]'}
- frontend_ports_meta: {frontend_ports_meta or '[]'}
- other_ports_meta: {other_ports_meta or '[]'}

Detected services and their Dockerfiles:

{chr(10).join(service_lines)}

Now output the final docker-compose.yml only.
"""
    return prompt.strip()


def _extract_yaml_from_response(text: str) -> str:
    """
    Extract YAML from an LLM response.
    If fenced with ```...```, return the content inside; otherwise return as-is.
    """
    if "```" not in text:
        return text.strip()

    # Try to grab the first fenced block
    parts = text.split("```")
    if len(parts) < 3:
        return text.strip()

    # parts[1] may be "yaml\n...", so strip a possible leading "yaml" / "yml"
    body = parts[1]
    if body.lstrip().lower().startswith("yaml"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
    if body.lstrip().lower().startswith("yml"):
        body = body.split("\n", 1)[1] if "\n" in body else ""

    return body.strip()


def _extract_compose_yaml_from_agent_response(text: str) -> str:
    """
    Extract docker-compose.yml YAML from the agent's structured response.
    The agent returns: STATUS/REASON/FIXES/GENERATED DOCKERFILES format.
    We need to find the docker-compose.yml section and extract just the YAML.
    """
    import re
    
    # Look for docker-compose.yml section in agent response
    # Pattern: **docker-compose.yml** followed by ```yaml block
    compose_pattern = r'\*\*docker-compose\.yml\*\*\s*```(?:yaml)?\s*([\s\S]*?)```'
    match = re.search(compose_pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Alternative pattern: docker-compose.yml header followed by yaml block
    alt_pattern = r'docker-compose\.yml[^\n]*\n\s*```(?:yaml)?\s*([\s\S]*?)```'
    match = re.search(alt_pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: try to extract any yaml block that looks like compose
    yaml_blocks = re.findall(r'```(?:yaml)?\s*([\s\S]*?)```', text)
    for block in yaml_blocks:
        if 'services:' in block and ('build:' in block or 'image:' in block):
            return block.strip()
    
    # Last resort: use the old extraction method
    return _extract_yaml_from_response(text)


def _collect_docker_files_for_agent(project_root: str) -> tuple:
    """
    Collect Dockerfiles and compose files in the format expected by the agent.
    Returns (dockerfiles, compose_files) where each is a list of {path, content}.
    """
    dockerfiles = []
    compose_files = []
    
    targets = ["Dockerfile", "dockerfile"]
    compose_targets = ["docker-compose.yml", "docker-compose.yaml"]
    
    for root, _, files in os.walk(project_root):
        for name in files:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, project_root).replace("\\", "/")
            
            if name in targets:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    dockerfiles.append({"path": rel_path, "content": content})
                except Exception:
                    dockerfiles.append({"path": rel_path, "content": ""})
            
            if name in compose_targets:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    compose_files.append({"path": rel_path, "content": content})
                except Exception:
                    compose_files.append({"path": rel_path, "content": ""})
    
    return dockerfiles, compose_files


def _build_file_tree_text(project_root: str, max_depth: int = 4, max_entries: int = 200) -> str:
    """
    Build a simple text representation of the file tree for the agent.
    """
    lines = []
    count = 0
    
    def walk(current: str, depth: int):
        nonlocal count
        if depth > max_depth or count >= max_entries:
            return
        
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if count >= max_entries:
                        break
                    if entry.name.startswith(".") and entry.name not in [".env", ".env.example"]:
                        continue
                    if entry.name in ["node_modules", "__pycache__", ".git", "venv", ".venv"]:
                        continue
                    count += 1
                    rel_path = os.path.relpath(entry.path, project_root)
                    prefix = "  " * depth + ("[dir] " if entry.is_dir() else "[file] ")
                    lines.append(f"{prefix}{rel_path}")
                    if entry.is_dir():
                        walk(entry.path, depth + 1)
        except Exception:
            pass
    
    walk(project_root, 0)
    return "\n".join(lines)


def _collect_source_files_for_llm(project_root: str, max_files: int = 6, max_bytes: int = 40_000) -> List[Dict]:
    """
    Collect key source files to give the LLM concrete context when generating
    Docker files. Prefers entry points, manifests, and small config files.
    Returns: [{path: str, content: str}]
    """
    priority_names = {
        "package.json", "requirements.txt", "setup.py", "pyproject.toml",
        "go.mod", "pom.xml", "build.gradle", "Gemfile", "composer.json",
        "main.py", "app.py", "server.py", "index.js", "server.js", "app.js",
        "main.go", "App.tsx", "index.ts",
    }
    priority_exts = {".py", ".js", ".ts", ".go", ".java", ".rb"}
    skip_dirs = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build", ".next"}

    found_priority: List[Dict] = []
    found_other: List[Dict] = []
    total_bytes = 0

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for name in files:
            if total_bytes >= max_bytes or (len(found_priority) + len(found_other)) >= max_files * 3:
                break
            full = os.path.join(root, name)
            rel = os.path.relpath(full, project_root).replace("\\", "/")
            try:
                size = os.path.getsize(full)
                if size == 0 or size > 60_000:
                    continue
                content = open(full, "r", encoding="utf-8", errors="ignore").read()
                entry = {"path": rel, "content": content[:8000]}
                if name in priority_names:
                    found_priority.append(entry)
                    total_bytes += min(len(content), 8000)
                elif any(name.endswith(ext) for ext in priority_exts):
                    found_other.append(entry)
                    total_bytes += min(len(content), 8000)
            except Exception:
                pass

    combined = found_priority + found_other
    return combined[:max_files]


# --------- RUN: compose-aware runner ---------


def run_project_stream(
    project_root: str,
    image_repo: str,
    host_port: int,
    metadata: Optional[Dict] = None,
) -> Generator[Dict, None, None]:
    """
    Run the project in a compose-aware way:

    - If docker-compose.yml exists:
        `docker compose up` (all services) in that directory.
    - Else, if >1 Dockerfiles exist:
        1) Ask Llama 3.1 to generate a docker-compose.yml (permanent).
        2) Save it to project_root/docker-compose.yml.
        3) Validate with `docker compose config`.
        4) If valid, run `docker compose up`.
    - Else (single Dockerfile or no compose + single image):
        `docker run --rm -p <host_port>:<container_port> {image_repo}:latest`
        where container_port is inferred from detector metadata.
    """
    # Step 0: do we already have a compose file?
    compose_path = _find_compose_file(project_root)

    # If not, and we have multiple Dockerfiles, auto-generate one via LLM
    if not compose_path:
        dockerfiles = _find_all_dockerfiles(project_root)
        if len(dockerfiles) > 1:
            yield {
                "line": (
                    f"Detected {len(dockerfiles)} Dockerfiles and no docker-compose.yml. "
                    "Generating docker-compose.yml via Docker Deploy Agent..."
                ),
                "stage": "run",
            }

            try:
                # Collect docker files in the format expected by the agent
                dockerfile_data, _ = _collect_docker_files_for_agent(project_root)
                file_tree = _build_file_tree_text(project_root)
                
                # Get project name from path
                project_name = os.path.basename(project_root) or "project"
                
                # Get services from metadata (contains env_file, is_cloud, build_output)
                services = (metadata or {}).get("services", [])
                
                # Use the sophisticated agent to generate docker-compose
                llm_response = run_docker_deploy_chat(
                    project_name=project_name,
                    metadata=metadata or {},
                    dockerfiles=dockerfile_data,
                    compose_files=[],  # We're generating because none exists
                    file_tree=file_tree,
                    user_message="Generate a docker-compose.yml for all detected services. Use env_file if detected in service definitions.",
                    logs=None,
                    extra_instructions=None,
                    services=services,
                )
            except Exception as e:
                msg = f"ERROR: LLM call for compose generation failed: {e}"
                yield {
                    "line": msg,
                    "stage": "run",
                    "exit_code": 1,
                    "complete": True,
                    "tail": [msg],
                }
                return

            generated_files, validation_errors = parse_and_validate_generated_docker_response(
                llm_response,
                metadata or {},
                services,
                require_dockerfiles=False,
                require_compose=True,
            )
            if validation_errors:
                yield {
                    "line": "Generated compose failed validation. Asking agent for one corrected response...",
                    "stage": "run",
                }
                try:
                    repair_response = run_docker_deploy_chat(
                        project_name=project_name,
                        metadata=metadata or {},
                        dockerfiles=dockerfile_data,
                        compose_files=[],
                        file_tree=file_tree,
                        user_message=(
                            "Regenerate docker-compose.yml only. Fix these validation errors exactly:\n"
                            + "\n".join(f"- {err}" for err in validation_errors)
                        ),
                        logs=validation_errors,
                        extra_instructions=f"Previous invalid response:\n{llm_response[:4000]}",
                        services=services,
                    )
                except Exception as e:
                    msg = f"ERROR: LLM repair call for compose generation failed: {e}"
                    yield {
                        "line": msg,
                        "stage": "run",
                        "exit_code": 1,
                        "complete": True,
                        "tail": [msg],
                    }
                    return
                generated_files, validation_errors = parse_and_validate_generated_docker_response(
                    repair_response,
                    metadata or {},
                    services,
                    require_dockerfiles=False,
                    require_compose=True,
                )

            if validation_errors:
                msg = "ERROR: Agent did not produce a valid docker-compose.yml:\n" + "\n".join(
                    f"- {err}" for err in validation_errors
                )
                yield {
                    "line": msg,
                    "stage": "run",
                    "exit_code": 1,
                    "complete": True,
                    "tail": validation_errors,
                }
                return

            compose_yaml = generated_files.get("docker-compose.yml")
            if not compose_yaml:
                compose_yaml = next(
                    content for path, content in generated_files.items()
                    if os.path.basename(path).lower() in {"docker-compose.yml", "docker-compose.yaml"}
                )
            compose_path = os.path.join(project_root, "docker-compose.yml")

            try:
                with open(compose_path, "w", encoding="utf-8") as f:
                    f.write(compose_yaml + "\n")
                yield {
                    "line": f"Wrote generated docker-compose.yml to {compose_path}.",
                    "stage": "run",
                }
            except Exception as e:
                msg = f"ERROR: Unable to write docker-compose.yml: {e}"
                yield {
                    "line": msg,
                    "stage": "run",
                    "exit_code": 1,
                    "complete": True,
                    "tail": [msg],
                }
                return

            # Validate with `docker compose config`
            compose_dir = os.path.dirname(compose_path)
            compose_file = os.path.basename(compose_path)
            rel_compose = os.path.relpath(compose_path, project_root).replace("\\", "/")

            config_cmd = ["docker", "compose", "-f", compose_file, "config"]
            yield {
                "line": f"Validating generated compose via: {' '.join(config_cmd)} (cwd={compose_dir})",
                "stage": "run",
            }

            try:
                proc = subprocess.run(
                    config_cmd,
                    cwd=compose_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception as e:
                msg = f"ERROR: Failed to run docker compose config: {e}"
                yield {
                    "line": msg,
                    "stage": "run",
                    "exit_code": 1,
                    "complete": True,
                    "tail": [msg],
                }
                return

            if proc.returncode != 0:
                msg = (
                    "ERROR: Generated docker-compose.yml is invalid.\n"
                    f"docker compose config exited with {proc.returncode}.\n"
                    f"stderr:\n{proc.stderr}"
                )
                yield {
                    "line": msg,
                    "stage": "run",
                    "exit_code": proc.returncode,
                    "complete": True,
                    "tail": [msg],
                }
                return

            yield {
                "line": (
                    "Generated docker-compose.yml is valid. "
                    f"Proceeding to docker compose up ({rel_compose})."
                ),
                "stage": "run",
            }

    # If we now have a compose file (either pre-existing or generated), use it
    compose_path = _find_compose_file(project_root)
    if compose_path:
        compose_dir = os.path.dirname(compose_path)
        compose_file = os.path.basename(compose_path)
        rel_compose = os.path.relpath(compose_path, project_root).replace("\\", "/")

        for ev in ensure_external_networks(compose_path, "run"):
            yield ev

        # Always recreate containers for compose runs
        down_cmd = ["docker", "compose", "-f", compose_file, "down", "--remove-orphans"]
        yield {
            "line": f"Running: {' '.join(down_cmd)} (cwd={compose_dir}) to clean previous containers",
            "stage": "run",
        }
        for event in _stream_command(down_cmd, cwd=compose_dir, stage="run"):
            yield event

        cmd = ["docker", "compose", "-f", compose_file, "up", "--force-recreate"]

        yield {
            "line": f"Using compose file for run: {rel_compose}",
            "stage": "run",
        }
        yield {
            "line": f"Running: {' '.join(cmd)} (cwd={compose_dir})",
            "stage": "run",
        }

        # This will start all services defined in the compose file and stream logs
        for event in _stream_command(cmd, cwd=compose_dir, stage="run"):
            yield event
        return

    # --------- fallback for non-compose projects: single Docker image ---------
    image_tag = f"{image_repo}:latest"

    # Intelligent port mapping
    meta = metadata or {}
    container_port = host_port  # default: assume same as host

    def _first_int_port(value) -> Optional[int]:
        """
        Safely extract the first int from a list-like metadata field.
        Handles None / scalar / list-of-mixed-types gracefully.
        """
        if isinstance(value, int):
            return value
        if not isinstance(value, list):
            return None
        for v in value:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
        return None

    # Priority:
    # 1) docker_expose_ports
    # 2) docker_backend_container_ports
    # 3) docker_frontend_container_ports
    container_port = (
        _first_int_port(meta.get("docker_expose_ports"))
        or _first_int_port(meta.get("docker_backend_container_ports"))
        or _first_int_port(meta.get("docker_frontend_container_ports"))
        or host_port
    )

    cmd = [
        "docker",
        "run",
        "--rm",
        "-p",
        f"{host_port}:{container_port}",
        "--add-host", "host.docker.internal:host-gateway",  # Allow access to host services
    ]

    # Inject .env file if it exists (CRITICAL for single-service backends)
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        cmd.extend(["--env-file", ".env"])
        yield {
            "line": "Injecting environment variables from .env file",
            "stage": "run"
        }

    cmd.append(image_tag)
    yield {
        "line": (
            f"Running single container {image_tag} with port mapping "
            f"Host:{host_port} -> Container:{container_port}"
        ),
        "stage": "run",
    }
    yield from _stream_command(cmd, cwd=".", stage="run")



# --------- PUSH: either compose-based services or single image ---------


def push_image_stream(project_root: str, image_repo: str,metadata) -> Generator[Dict, None, None]:
    """
    Stream docker push logs.
    Includes:
    1. Docker Login (Critical for private repos)
    2. Volume Warnings (Safety check)
    3. Magic Fix (JSON resolution for correct image names)
    4. Safety Skip (Don't guess names if resolution fails)
    """
    # ---------- 1. Optional Docker Login ----------
    last_login_event: Optional[Dict] = None
    for event in _docker_login("push"):
        last_login_event = event
        yield event

    if last_login_event and last_login_event.get("exit_code", 0) != 0:
        msg = "Aborting push because docker login failed."
        yield {
            "line": msg,
            "stage": "push",
            "exit_code": last_login_event.get("exit_code", 1),
            "complete": True,
            "tail": [msg],
        }
        return

    # ---------- 2. Compose-Aware Push ----------
    compose_path = _find_compose_file(project_root)
    if compose_path:
        compose_dir = os.path.dirname(compose_path)
        compose_file = os.path.basename(compose_path)
        rel_compose = os.path.relpath(compose_path, project_root).replace("\\", "/")

        yield {
            "line": f"Using compose file for push (read-only): {rel_compose}",
            "stage": "push",
        }

        for ev in ensure_external_networks(compose_path, "push"):
            yield ev

        # --- Helper to check for volume warnings ---
        warned_paths = set()

        def _check_volumes(service_name, volumes_list):
            if not volumes_list:
                return
            for vol in volumes_list:
                host_path = None
                # String format: "./data:/app/data"
                if isinstance(vol, str):
                    host_path = vol.split(":", 1)[0].strip()
                # Object format: { type: bind, source: ./data }
                elif isinstance(vol, dict):
                    host_path = vol.get("source") or vol.get("src")

                if host_path and (
                    host_path.startswith("./")
                    or host_path.startswith("/")
                    or host_path.startswith("~")
                ):
                    if host_path not in warned_paths:
                        warned_paths.add(host_path)
                        yield {
                            "line": (
                                f"WARNING: Host volume detected ('{host_path}') in service "
                                f"'{service_name}'. Local data will NOT be uploaded. "
                                "Use 'COPY' in Dockerfile for code or Named Volumes for data."
                            ),
                            "stage": "push",
                        }

        # --- PATH A: Level 2 "Magic" Resolution (JSON) ---
        services_from_config: Optional[Dict[str, Dict]] = None
        config_cmd = ["docker", "compose", "-f", compose_file, "config", "--format", "json"]

        yield {
            "line": f"Resolving final service images via: {' '.join(config_cmd)}",
            "stage": "push",
        }

        try:
            proc = subprocess.run(
                config_cmd,
                cwd=compose_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if proc.returncode == 0:
                try:
                    config_data = json.loads(proc.stdout or "{}")
                    services_from_config = config_data.get("services") or {}
                    yield {"line": "Successfully resolved compose config.", "stage": "push"}
                except json.JSONDecodeError:
                    yield {
                        "line": "Failed to parse compose config JSON. Falling back to YAML.",
                        "stage": "push",
                    }
            else:
                yield {
                    "line": f"Compose config failed (exit {proc.returncode}). Falling back to YAML.",
                    "stage": "push",
                }
        except Exception as e:
            yield {
                "line": f"Error running compose config: {e}. Falling back to YAML.",
                "stage": "push",
            }

        # If JSON resolution worked, use it
        if services_from_config:
            for svc_name, svc in services_from_config.items():
                # 1. Check Warnings
                yield from _check_volumes(svc_name, svc.get("volumes", []))

                # 2. Skip pure database images (mongo, postgres, redis, mysql)
                svc_image_raw = svc.get("image") or ""
                if _is_database_service(svc_name, svc_image_raw):
                    yield {
                        "line": f"Skipping database service '{svc_name}' (not pushed to DockerHub).",
                        "stage": "push",
                    }
                    continue

                # 3. Resolve source image — explicit or compose auto-name
                source_image = svc_image_raw or None
                if not source_image:
                    # Docker Compose auto-names build images as {project_dir}-{service_name}
                    inferred = _infer_compose_image_name(compose_dir, svc_name)
                    yield {
                        "line": f"Service '{svc_name}' has no explicit image. Inferring built image: {inferred}",
                        "stage": "push",
                    }
                    source_image = inferred

                dest_image = f"{image_repo}-{svc_name}:latest"
                yield from _tag_and_push(source_image, dest_image, cwd=compose_dir)
            return

        # --- PATH B: Fallback YAML Parsing (Safety Mode) ---
        yield {"line": "Falling back to safe YAML parsing mode.", "stage": "push"}

        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        services = data.get("services") or {}

        for svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue

            # 1. Check Warnings
            yield from _check_volumes(svc_name, svc.get("volumes", []))

            # 2. Skip pure database images
            svc_image_raw = svc.get("image") or ""
            if _is_database_service(svc_name, svc_image_raw):
                yield {
                    "line": f"Skipping database service '{svc_name}' (not pushed to DockerHub).",
                    "stage": "push",
                }
                continue

            # 3. Resolve source image — explicit or compose auto-name
            source_image = svc_image_raw or None
            if not source_image:
                if "build" in svc:
                    inferred = _infer_compose_image_name(compose_dir, svc_name)
                    yield {
                        "line": f"Service '{svc_name}' has no explicit image. Inferring built image: {inferred}",
                        "stage": "push",
                    }
                    source_image = inferred
                else:
                    yield {
                        "line": f"WARNING: Service '{svc_name}' has no image and no build config. Skipping.",
                        "stage": "push",
                    }
                    continue

            dest_image = f"{image_repo}-{svc_name}:latest"
            yield from _tag_and_push(source_image, dest_image, cwd=compose_dir)
        return

    # ---------- 3. Non-Compose Projects ----------
    # We may have:
    # - A single canonical image:   {image_repo}:latest
    # - Multiple service images:    {image_repo}-api:latest, {image_repo}-web:latest, ...
    #
    # Goal: push ALL matching images for this project.

    discovered: List[str] = []

    list_cmd = ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]
    yield {
        "line": f"Discovering local images for prefix '{image_repo}' via: {' '.join(list_cmd)}",
        "stage": "push",
    }

    try:
        proc = subprocess.run(
            list_cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as e:
        yield {
            "line": f"ERROR: Unable to list docker images: {e}",
            "stage": "push",
            "exit_code": 1,
            "complete": True,
            "tail": [str(e)],
        }
        return

    if proc.returncode != 0:
        msg = f"ERROR: 'docker images' failed (exit {proc.returncode}): {proc.stderr.strip()}"
        yield {
            "line": msg,
            "stage": "push",
            "exit_code": proc.returncode,
            "complete": True,
            "tail": [msg],
        }
        return

    canonical_tag = f"{image_repo}:latest"
    has_canonical, service_tags = False, []
    for line in (proc.stdout or "").splitlines():
        name = line.strip()
        if not name: continue
        if name == canonical_tag:
            has_canonical = True
            discovered.append(name)
        elif name.startswith(f"{image_repo}-"):
            service_tags.append(name)
    if not has_canonical:
        discovered.extend(service_tags)

    if not discovered:
        msg = (
            f"No local images found for project prefix '{image_repo}'. "
            "Did you run the build step first?"
        )
        yield {
            "line": msg,
            "stage": "push",
            "exit_code": 1,
            "complete": True,
            "tail": [msg],
        }
        return

    # Push all matching images
    yield {
        "line": f"Found {len(discovered)} image(s) for this project: {', '.join(discovered)}",
        "stage": "push",
    }

    for img in discovered:
        yield {"line": f"Pushing {img}", "stage": "push"}
        for event in _stream_command(["docker", "push", img], cwd=project_root, stage="push"):
            yield event


def _ensure_compose_env_files(project_root: str) -> None:
    """
    Look at docker-compose.yml and ensure that all referenced env_file paths exist.
    If a referenced file is missing, create an empty file so docker compose doesn't fail early.
    """
    compose_path = _find_compose_file(project_root)
    if not compose_path:
        return

    try:
        with open(compose_path, "r", encoding="utf-8") as f:
            compose_data = yaml.safe_load(f) or {}
    except Exception:
        # If we can't parse, don't break the build/push -- just ignore
        return

    services = compose_data.get("services", {}) or {}
    compose_dir = os.path.dirname(compose_path)

    def _normalize_env_files(env_file_value):
        if not env_file_value:
            return []
        if isinstance(env_file_value, str):
            return [env_file_value]
        if isinstance(env_file_value, list):
            return [str(v) for v in env_file_value]
        return []

    for service_name, svc in services.items():
        env_files = _normalize_env_files(svc.get("env_file"))
        for rel in env_files:
            env_path = os.path.join(compose_dir, rel)
            if not os.path.exists(env_path):
                try:
                    os.makedirs(os.path.dirname(env_path), exist_ok=True)
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(
                            "# Auto-created by DevOps Autopilot because docker-compose "
                            "referenced this env_file\n"
                        )
                except Exception:
                    # Best-effort -- if this fails, docker compose will still show the real error
                    pass


# --------- Kubernetes Deployment Streaming ---------


def _read_compose_services_for_k8s(compose_path: str) -> List[Dict]:
    """
    Read docker-compose.yml and return a list of app services with their
    locally-built image names (skip database services).
    Returns: [{name, image, port}]
    """
    try:
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    compose_dir = os.path.dirname(compose_path)
    services = data.get("services") or {}
    result: List[Dict] = []

    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        image_raw = svc.get("image") or ""
        # Skip database services
        if _is_database_service(svc_name, image_raw):
            continue
        # Resolve image name
        if image_raw:
            image = image_raw
        elif "build" in svc:
            image = _infer_compose_image_name(compose_dir, svc_name)
        else:
            continue
        # Get first exposed port
        port = 80
        ports = svc.get("ports") or []
        for p in ports:
            if isinstance(p, str):
                parts = p.split(":")
                try:
                    port = int(parts[-1].split("/")[0])
                    break
                except ValueError:
                    pass
            elif isinstance(p, dict):
                try:
                    port = int(p.get("target") or p.get("container_port") or 80)
                    break
                except (TypeError, ValueError):
                    pass
        result.append({"name": svc_name, "image": image, "port": port})
    return result


def _build_k8s_manifests_from_compose(
    services: List[Dict],
    project_label: str,
    base_node_port: int,
) -> str:
    """
    Generate a combined Kubernetes YAML (multi-document) for all app services.
    Uses imagePullPolicy: IfNotPresent so local Docker images are used directly
    without needing them on DockerHub — perfect for Docker Desktop Kubernetes.
    """
    import re as _re
    docs: List[str] = []
    current_port = base_node_port

    for svc in services:
        svc_name = _re.sub(r"[^a-z0-9-]", "-", svc["name"].lower()).strip("-")
        image = svc["image"]
        container_port = svc["port"]

        deployment = (
            f"apiVersion: apps/v1\n"
            f"kind: Deployment\n"
            f"metadata:\n"
            f"  name: {svc_name}\n"
            f"  labels:\n"
            f"    app: {svc_name}\n"
            f"    project: {project_label}\n"
            f"spec:\n"
            f"  replicas: 1\n"
            f"  selector:\n"
            f"    matchLabels:\n"
            f"      app: {svc_name}\n"
            f"  template:\n"
            f"    metadata:\n"
            f"      labels:\n"
            f"        app: {svc_name}\n"
            f"        project: {project_label}\n"
            f"    spec:\n"
            f"      containers:\n"
            f"      - name: {svc_name}\n"
            f"        image: {image}\n"
            f"        imagePullPolicy: IfNotPresent\n"
            f"        ports:\n"
            f"        - containerPort: {container_port}\n"
            f"        resources:\n"
            f"          requests:\n"
            f"            memory: \"128Mi\"\n"
            f"            cpu: \"100m\"\n"
            f"          limits:\n"
            f"            memory: \"512Mi\"\n"
            f"            cpu: \"500m\"\n"
        )

        # Clamp node port to valid range
        node_port = max(30000, min(32767, current_port))
        current_port += 1

        service = (
            f"apiVersion: v1\n"
            f"kind: Service\n"
            f"metadata:\n"
            f"  name: {svc_name}-svc\n"
            f"  labels:\n"
            f"    app: {svc_name}\n"
            f"    project: {project_label}\n"
            f"spec:\n"
            f"  type: NodePort\n"
            f"  selector:\n"
            f"    app: {svc_name}\n"
            f"  ports:\n"
            f"  - port: {container_port}\n"
            f"    targetPort: {container_port}\n"
            f"    nodePort: {node_port}\n"
        )

        docs.append(deployment)
        docs.append(service)

    return "\n---\n".join(docs) + "\n"


def _find_k8s_manifests(project_root: str) -> List[str]:
    """
    Find Kubernetes manifest YAML files under project_root/k8s/.
    Returns list of absolute file paths.
    """
    k8s_dir = os.path.join(project_root, "k8s")
    found: List[str] = []
    if not os.path.isdir(k8s_dir):
        return found
    for name in os.listdir(k8s_dir):
        if name.endswith(".yaml") or name.endswith(".yml"):
            found.append(os.path.join(k8s_dir, name))
    return sorted(found)


def _write_k8s_files(project_root: str, files: Dict[str, str]) -> List[str]:
    """Write k8s manifest files to disk under project_root. Returns list of written paths."""
    root_abs = os.path.abspath(project_root)
    written: List[str] = []
    for rel_path, content in files.items():
        clean = rel_path.replace("\\", "/").lstrip("/")
        dest = os.path.abspath(os.path.join(root_abs, clean))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content.rstrip() + "\n")
        written.append(clean)
    return written


def k8s_deploy_stream(
    project_root: str,
    image_repo: str,
    metadata: Optional[Dict] = None,
) -> Generator[Dict, None, None]:
    """
    High-level Kubernetes deployment streamer.

    Flow:
    1. Check kubectl is available
    2. Check k8s cluster is reachable
    3. Find k8s manifests in project_root/k8s/
    4. If none found → generate via Gemini and save them
    5. Run `kubectl apply -f k8s/` and stream output
    6. Wait a few seconds then stream pod status
    """
    import re as _re
    import time as _time

    meta = metadata or {}
    project_name = os.path.basename(project_root) or "project"
    import re as _re2
    sanitized = _re2.sub(r"[^a-z0-9_-]", "-", project_name.lower()).strip("-")[:50]
    hub_user = settings.DOCKER_HUB_USERNAME
    repo_prefix = settings.APP_REGISTRY_PREFIX or "devops-autopilot"
    if hub_user:
        _image_repo = image_repo  # Already fully qualified from caller
    else:
        _image_repo = image_repo

    deployment_name = _re.sub(r"[^a-z0-9-]", "-", sanitized).strip("-")
    node_port = 30000 + (hash(project_root) % 2767)
    node_port = max(30000, min(32767, node_port))

    # 1. Check kubectl available
    yield {"line": "Checking kubectl availability...", "stage": "k8s_deploy"}
    try:
        check = subprocess.run(
            ["kubectl", "version", "--client", "--output=yaml"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10
        )
        if check.returncode != 0:
            msg = "ERROR: kubectl not found or not working. Install kubectl and ensure it is in PATH."
            yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
            return
        yield {"line": "✅ kubectl found", "stage": "k8s_deploy"}
    except FileNotFoundError:
        msg = "ERROR: kubectl binary not found. Please install kubectl."
        yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
        return
    except Exception as e:
        msg = f"ERROR: kubectl check failed: {e}"
        yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
        return

    # 2. Check cluster reachable
    yield {"line": "Checking Kubernetes cluster connectivity...", "stage": "k8s_deploy"}
    try:
        cluster_check = subprocess.run(
            ["kubectl", "cluster-info"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        if cluster_check.returncode != 0:
            stderr_msg = cluster_check.stderr.decode("utf-8", errors="replace").strip()
            msg = (
                f"ERROR: Kubernetes cluster not reachable. {stderr_msg}\n"
                "Ensure Docker Desktop Kubernetes is enabled and running."
            )
            yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
            return
        yield {"line": "✅ Kubernetes cluster is reachable", "stage": "k8s_deploy"}
    except Exception as e:
        msg = f"ERROR: Cluster check failed: {e}"
        yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
        return

    # 3. Find or generate k8s manifests
    k8s_manifests = _find_k8s_manifests(project_root)

    if not k8s_manifests:
        services = meta.get("services", [])

        # ── Compose-aware: build per-service manifests using local image names ──
        compose_path_found = _find_compose_file(project_root)
        if compose_path_found:
            yield {"line": "Reading compose services to generate per-service k8s manifests...", "stage": "k8s_deploy"}
            try:
                compose_services = _read_compose_services_for_k8s(compose_path_found)
                if compose_services:
                    manifest_content = _build_k8s_manifests_from_compose(compose_services, deployment_name, node_port)
                    manifest_path = os.path.join(project_root, "k8s")
                    os.makedirs(manifest_path, exist_ok=True)
                    with open(os.path.join(manifest_path, "deployment.yaml"), "w", encoding="utf-8") as f:
                        f.write(manifest_content)
                    yield {"line": "✅ Generated k8s/deployment.yaml from compose services", "stage": "k8s_deploy"}
                    k8s_manifests = _find_k8s_manifests(project_root)
            except Exception as e:
                yield {"line": f"Warning: compose-aware k8s generation failed: {e}. Falling back to Gemini.", "stage": "k8s_deploy"}

    if not k8s_manifests:
        services = meta.get("services", [])
        yield {
            "line": "No k8s/ manifests found. Generating via Gemini AI...",
            "stage": "k8s_deploy",
        }
        try:
            generated = run_k8s_manifest_generation(
                project_name=project_name,
                deployment_name=deployment_name,
                image_repo=_image_repo,
                node_port=node_port,
                services=services,
                metadata=meta,
            )
            if not generated:
                msg = "ERROR: Gemini could not generate k8s manifests. Check GEMINI_API_KEY."
                yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
                return

            written = _write_k8s_files(project_root, generated)
            for rel in written:
                yield {"line": f"✅ Generated and saved: {rel}", "stage": "k8s_deploy"}

            k8s_manifests = _find_k8s_manifests(project_root)
        except Exception as e:
            msg = f"ERROR: k8s manifest generation failed: {e}"
            yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
            return

    if not k8s_manifests:
        msg = "ERROR: No k8s manifests available after generation attempt."
        yield {"line": msg, "stage": "k8s_deploy", "exit_code": 1, "complete": True, "tail": [msg]}
        return

    # 4. Apply manifests
    k8s_dir = os.path.join(project_root, "k8s")
    yield {"line": f"Applying {len(k8s_manifests)} manifest(s) from k8s/ ...", "stage": "k8s_deploy"}

    apply_cmd = ["kubectl", "apply", "-f", k8s_dir, "--validate=false"]
    yield {"line": f"Running: {' '.join(apply_cmd)}", "stage": "k8s_deploy"}

    last_apply_event: Optional[Dict] = None
    for event in _stream_command(apply_cmd, cwd=project_root, stage="k8s_deploy"):
        last_apply_event = event
        yield event

    if last_apply_event and last_apply_event.get("exit_code", 0) != 0:
        tail = last_apply_event.get("tail") or []
        msg = "ERROR: kubectl apply failed. See logs above."
        yield {"line": msg, "stage": "k8s_deploy", "exit_code": last_apply_event.get("exit_code", 1), "complete": True, "tail": tail + [msg]}
        return

    yield {"line": "✅ kubectl apply succeeded", "stage": "k8s_deploy"}

    # 5. Wait briefly then check pod status
    yield {"line": "⏳ Waiting for pods to start (10 seconds)...", "stage": "k8s_deploy"}
    _time.sleep(10)

    pod_cmd = ["kubectl", "get", "pods", "-l", f"app={deployment_name}", "-o", "wide"]
    yield {"line": f"Checking pod status: {' '.join(pod_cmd)}", "stage": "k8s_deploy"}

    try:
        pod_proc = subprocess.run(
            pod_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        stdout = pod_proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = pod_proc.stderr.decode("utf-8", errors="replace").strip()
        if stdout:
            for line in stdout.splitlines():
                yield {"line": line, "stage": "k8s_deploy"}
        if stderr:
            yield {"line": f"[stderr] {stderr}", "stage": "k8s_deploy"}
    except Exception as e:
        yield {"line": f"Warning: Could not get pod status: {e}", "stage": "k8s_deploy"}

    # 6. Stream recent events for the deployment
    events_cmd = ["kubectl", "get", "events", "--sort-by=lastTimestamp", "--field-selector=reason!=SuccessfulCreate"]
    try:
        ev_proc = subprocess.run(
            events_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        ev_out = ev_proc.stdout.decode("utf-8", errors="replace").strip()
        if ev_out:
            yield {"line": "--- Recent Kubernetes Events ---", "stage": "k8s_deploy"}
            for line in ev_out.splitlines()[-20:]:
                yield {"line": line, "stage": "k8s_deploy"}
    except Exception:
        pass  # Events are nice-to-have

    yield {
        "line": f"🚀 Deployment complete! Service exposed on NodePort {node_port}. Access at http://localhost:{node_port}",
        "stage": "k8s_deploy",
        "complete": True,
        "exit_code": 0,
        "service_url": f"http://localhost:{node_port}",
        "deployment_name": deployment_name,
    }
