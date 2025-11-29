import os
import subprocess
from typing import Dict, Generator, List, Optional
import yaml
import json 

from ..LLM.llm_client import call_llama 

from ..config.settings import settings


# --------- helpers to discover compose + Dockerfiles ---------
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


# --------- BUILD: whole project (compose OR all Dockerfiles) ---------


def build_project_stream(
    project_root: str,
    image_repo: str,  # e.g. "devops-autopilot-<project_id>" or "abdul/devops-autopilot-<project_id>"
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
        msg = "ERROR: No docker-compose.yml and no Dockerfiles found in project."
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
            "docker_backend_container_ports",
            "docker_backend_ports",
            "backend_port",
            "port",
        ]
    elif role == "frontend":
        fields = [
            "docker_frontend_container_ports",
            "docker_frontend_ports",
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
                    "Generating docker-compose.yml via Llama 3.1..."
                ),
                "stage": "run",
            }

            try:
                prompt = _build_compose_generation_prompt(
                    project_root=project_root,
                    dockerfile_rel_paths=dockerfiles,
                    backend_host_port=host_port,
                    metadata=metadata,
                )

                llm_response = call_llama(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are a precise DevOps assistant. "
                                "You ONLY output valid docker-compose.yml YAML as requested."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ]
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

            compose_yaml = _extract_yaml_from_response(llm_response)
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

        cmd = ["docker", "compose", "-f", compose_file, "up"]

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
        image_tag,
    ]
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

                # 2. Get Resolved Image
                source_image = svc.get("image")
                if not source_image:
                    yield {
                        "line": f"Resolved config for '{svc_name}' has no image name. Skipping.",
                        "stage": "push",
                    }
                    continue

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

            # 2. Get Explicit Image (NO GUESSING)
            source_image = svc.get("image")
            if not source_image:
                yield {
                    "line": (
                        f"WARNING: Service '{svc_name}' has no explicit 'image' field. Skipping push to avoid errors."
                    ),
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

    for line in (proc.stdout or "").splitlines():
        name = line.strip()
        if not name:
            continue

        # Match e.g.:
        #   abdul/devops-autopilot-<id>:latest
        #   abdul/devops-autopilot-<id>-api:latest
        #   abdul/devops-autopilot-<id>-web:latest
        if name == f"{image_repo}:latest" or name.startswith(f"{image_repo}-"):
            discovered.append(name)

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
