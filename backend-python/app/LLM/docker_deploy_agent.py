from typing import Dict, List, Optional

from .llm_client import call_llama

# System prompt dedicated to Docker deployment analysis/generation
DOCKER_DEPLOY_SYSTEM_PROMPT = """You are a Docker Configuration Engine. You do not guess; you strictly implement specifications.

INPUT DATA
You will receive:

Metadata (SOURCE OF TRUTH for runtime, ports, commands, database)
Service Definitions (Paths, names, types of services)
Existing Files (Dockerfiles/docker-compose, if any)
File Tree (Project structure)
MODE (VALIDATE_EXISTING or GENERATE_MISSING)
STRICT VARIABLE BINDING PROTOCOL
You MUST map input metadata to output files using this exact logic. DO NOT USE DEFAULTS. DO NOT USE TRAINING DATA SUGGESTIONS.

Variable Bindings:

RUNTIME_IMAGE = metadata.runtime

IF metadata.runtime = "node:20-alpine" → FROM node:20-alpine
STRICT FORBIDDEN: node:14, node:16, python:3.9 (unless in metadata)
BACKEND_PORT = metadata.backend_port

Used for: EXPOSE and ports mapping in compose
STRICT FORBIDDEN: 3000, 3001, 8000, 8080 (unless matches metadata)
FRONTEND_PORT = metadata.frontend_port

Used for: Host mapping in compose (e.g., "5173:80")
DB_PORT = metadata.database_port

Used for: Database ports in compose
BUILD_CMD = metadata.build_command

Used for: RUN instruction (e.g., "npm install", "pip install -r requirements.txt")
START_CMD = metadata.start_command

Used for: CMD instruction
MODE-SPECIFIC RESPONSIBILITIES
MODE = VALIDATE_EXISTING
Diagnose issues in existing files based on Metadata
If Dockerfile uses node:14 but metadata.runtime = "node:20 alpine", FLAG IT
DO NOT generate new files unless explicitly requested
Focus on concrete fixes
MODE = GENERATE_MISSING
MUST generate files for ALL services in Service Definitions
Add verification comment header to EVERY generated file
Generate: backend/Dockerfile, frontend/Dockerfile, docker-compose.yml (as needed)
CRITICAL RULES:

Database Services (mongo, postgres, redis, mysql):

Use official images in compose (e.g., image: mongo:latest)
DO NOT create Dockerfile for databases
Image Field (REQUIRED):

Every service in docker-compose MUST have image: <project>-<service>:latest
Example: image: myproject-backend:latest
Multi-Stage Builds:

Frontend (React/Vue/Angular): Build → nginx:alpine
Go: Build → alpine runtime
LANGUAGE-SPECIFIC PATTERNS

CRITICAL: Verification headers MUST be Dockerfile comments starting with #
INVALID: runtime=node:20-alpine (this causes Docker parse errors!)
VALID: # VERIFICATION: runtime=node:20-alpine, port=8888

Node.js Backend:

# VERIFICATION: runtime=node:20-alpine, port=8888
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
ENV NODE_ENV=production
ENV PORT=8888
EXPOSE 8888
CMD ["node", "server.js"]
React/Vite Frontend (Multi-Stage):

# VERIFICATION: runtime=node:20-alpine, build_output=/app/dist
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
Python Backend:

# VERIFICATION: runtime=python:3.11-slim, port=8000
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
Docker Compose (Multi-Service MERN):

# VERIFICATION: backend_port=8888, frontend_port=5173, db_port=27017
version: '3.9'
services:
  backend:
    image: project-backend:latest  # REQUIRED for push
    build: ./backend
    ports:
      - "8888:8888"  # Use metadata.backend_port
    environment:
      - MONGO_URI=mongodb://mongo:27017/dbname
    depends_on:
      - mongo
  
  frontend:
    image: project-frontend:latest  # REQUIRED for push
    build: ./frontend
    ports:
      - "5173:80"  # Host from metadata.frontend_port, container nginx on 80
  
  mongo:
    image: mongo:latest  # Official image, NO Dockerfile
    ports:
      - "27017:27017"
    volumes:
      - mongo-data:/data/db  # Named volume, NOT bind mount
volumes:
  mongo-data:
OUTPUT FORMAT (MANDATORY)
STATUS: Valid / Invalid / Partially Valid / Not Found / Generated REASON:

Bullet points explaining status
Must cite concrete evidence from files/metadata/logs
FIXES or GENERATED DOCKERFILES:

For VALIDATE: Show specific fixes with line numbers
For GENERATE: Provide COMPLETE file contents with verification headers
LOG ANALYSIS:

Summarize key issues from logs or "No logs provided"
FINAL EXECUTION CHECKLIST (Run before responding)
Before generating, verify you extracted: ☑ Runtime from metadata.runtime (NOT node:14 default) ☑ Backend port from metadata.backend_port (NOT 3000 default) ☑ Frontend port from metadata.frontend_port (NOT 3000 default) ☑ Database port from metadata.database_port ☑ Build command from metadata.build_command ☑ Start command from metadata.start_command ☑ Service paths from Service Definitions ☑ Added image: field to ALL compose services ☑ Used official images for databases (no Dockerfile) ☑ Added verification comments to all files

If ANY checklist item fails, STOP and re-extract from metadata.

Proceed with analysis or generation now."""



def _format_metadata(metadata: Dict) -> str:
    """Format metadata in a structured way that's easy for LLM to parse."""
    if not metadata:
        return "Metadata: unavailable"

    # Use clear key=value format for critical fields
    lines = [
        "=== METADATA (SOURCE OF TRUTH) ===",
        f"metadata.framework = {metadata.get('framework', 'Unknown')}",
        f"metadata.language = {metadata.get('language', 'Unknown')}",
        f"metadata.runtime = {metadata.get('runtime', 'Unknown')}",
        f"metadata.backend_port = {metadata.get('backend_port', 'Unknown')}",
        f"metadata.frontend_port = {metadata.get('frontend_port', 'Unknown')}",
        f"metadata.database = {metadata.get('database', 'Unknown')}",
        f"metadata.database_port = {metadata.get('database_port', 'Unknown')}",
    ]

    build_cmd = metadata.get("build_command")
    start_cmd = metadata.get("start_command")
    if build_cmd:
        lines.append(f"metadata.build_command = {build_cmd}")
    if start_cmd:
        lines.append(f"metadata.start_command = {start_cmd}")

    env_vars = metadata.get("env_variables") or []
    if env_vars:
        lines.append(f"Environment variables: {', '.join(env_vars[:15])}")

    deps = metadata.get("dependencies") or []
    if deps:
        shown = ", ".join(deps[:10])
        if len(deps) > 10:
            shown += " ..."
        lines.append(f"Dependencies: {shown}")
    
    lines.append("=== END METADATA ===")

    return "\n".join(lines)


def _format_dockerfiles(dockerfiles: List[Dict[str, str]]) -> str:
    if not dockerfiles:
        return "No Dockerfiles detected."

    sections: List[str] = []
    for df in dockerfiles:
        path = df.get("path", "Dockerfile")
        content = df.get("content", "")
        sections.append(f"[Dockerfile: {path}]\n{content}")
    return "\n\n".join(sections)


def _format_compose_files(compose_files: List[Dict[str, str]]) -> str:
    if not compose_files:
        return "No docker-compose files detected."

    sections: List[str] = []
    for cf in compose_files:
        path = cf.get("path", "docker-compose.yml")
        content = cf.get("content", "")
        sections.append(f"[Compose: {path}]\n{content}")
    return "\n\n".join(sections)


def _format_file_tree(file_tree: Optional[str]) -> str:
    return file_tree or "File tree: not provided"


def _format_logs(logs: Optional[List[str]]) -> str:
    if not logs:
        return "Build/Run logs: none yet."
    joined = "\n".join(logs[-20:])
    return f"Build/Run logs (latest tail):\n{joined}"


def build_deploy_message(
    project_name: str,
    metadata: Dict,
    dockerfiles: List[Dict[str, str]],
    compose_files: List[Dict[str, str]],
    file_tree: Optional[str],
    user_message: str,
    logs: Optional[List[str]] = None,
    extra_instructions: Optional[str] = None,
    services: Optional[List[Dict[str, str]]] = None,
    mode: str = "VALIDATE_EXISTING",
) -> str:
    if dockerfiles:
        dockerfile_summary = f"Dockerfiles detected: {len(dockerfiles)} ({', '.join(df.get('path', '') for df in dockerfiles[:5])})"
    else:
        dockerfile_summary = "Dockerfiles detected: 0"

    if compose_files:
        compose_summary = f"Compose files detected: {len(compose_files)} ({', '.join(cf.get('path', '') for cf in compose_files[:5])})"
    else:
        compose_summary = "Compose files detected: 0"

    sections = [
        f"MODE: {mode}",
        f"Project: {project_name}",
        dockerfile_summary,
        compose_summary,
        _format_metadata(metadata),
        _format_dockerfiles(dockerfiles),
        _format_compose_files(compose_files),
        _format_file_tree(file_tree),
        _format_logs(logs),
    ]

    if extra_instructions:
        sections.append(f"User deployment instructions: {extra_instructions}")

    # Add service definitions if present
    if services:
        lines = ["Service Definitions:"]
        for svc in services:
            lines.append(f"- name: {svc.get('name', 'unknown')}, path: {svc.get('path', '.')}, type: {svc.get('type', 'unknown')}")
        sections.append("\n".join(lines))

    # Enhance user_message for GENERATE_MISSING mode if it's generic
    if mode == "GENERATE_MISSING" and user_message.strip().lower() in ["generate", "create", ""]:
        user_message = (
            "Generate ALL required Docker files:\n"
            "1. Create Dockerfile for EACH service directory (using metadata.runtime, metadata.backend_port)\n"
            "2. Create docker-compose.yml at project root (with image: fields for ALL services)\n"
            "Use EXACT metadata values. Include VERIFICATION comments. Provide complete file contents."
        )

    sections.append(f"User message: {user_message}")
    sections.append("Respond with STATUS/REASON/FIXES or GENERATED DOCKERFILES/LOG ANALYSIS.")

    return "\n\n".join(sections)


def run_docker_deploy_chat(
    project_name: str,
    metadata: Dict,
    dockerfiles: List[Dict[str, str]],
    compose_files: List[Dict[str, str]],
    file_tree: Optional[str],
    user_message: str,
    logs: Optional[List[str]] = None,
    extra_instructions: Optional[str] = None,
    services: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Invoke LLM to analyze or generate Dockerfiles with the mandated response shape.
    """

    # Decide mode based on presence of Dockerfiles / compose
    if dockerfiles or compose_files:
        mode = "VALIDATE_EXISTING"
    else:
        mode = "GENERATE_MISSING"

    message = build_deploy_message(
        project_name=project_name,
        metadata=metadata,
        dockerfiles=dockerfiles,
        compose_files=compose_files,
        file_tree=file_tree,
        user_message=user_message,
        logs=logs,
        extra_instructions=extra_instructions,
        services=services,
        mode=mode,
    )

    # Debug: Print first 500 chars of message to see if metadata is included
    print(f"DEBUG: Sending message to LLM (first 1000 chars):\n{message[:1000]}\n...")

    return call_llama(
        [
            {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
    )

