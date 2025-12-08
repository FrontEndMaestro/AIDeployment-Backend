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

Database Services (SMART CLOUD VS LOCAL DETECTION):

CHECK SERVICE DEFINITIONS for database info:
- If is_cloud=True → DO NOT add database container, pass env vars to backend
- If is_cloud=False (needs_container=True) → Add database container to compose

CLOUD DATABASE (e.g., MongoDB Atlas, AWS RDS, Supabase):
  - NO database service in docker-compose
  - DO NOT add mongo/postgres/redis service
  - ENV VAR INJECTION (choose based on service definition):
  
    1. If service has "env_file: ./backend/.env" → USE THIS:
       ```yaml
       backend:
         env_file:
           - ./backend/.env  # PREFERRED - loads all vars!
       ```
    
    2. If NO env_file detected → USE THIS (user provides at runtime):
       ```yaml
       backend:
         environment:
           - DB_URL=${DB_URL}  # User must export DB_URL before docker compose
       ```

LOCAL DATABASE (e.g., mongodb://localhost):
  - CHECK service definitions for database service with is_cloud: False
  - Add database service with docker_image from service definition
  - Backend MUST have depends_on: [db_service_name]
  - Backend gets: environment: - MONGO_URI=mongodb://mongo:27017/dbname
  
  EXAMPLE LOCAL DB docker-compose.yml:
  ```yaml
  services:
    backend:
      depends_on:
        - mongo
      environment:
        - MONGO_URI=mongodb://mongo:27017/dbname
    
    mongo:
      image: mongo:latest  # Use docker_image from service definition
      ports:
        - "27017:27017"
  ```

Use official images in compose (e.g., image: mongo:latest)
DO NOT create Dockerfile for databases

Image Field (REQUIRED):

Every service in docker-compose MUST have image: <project>-<service>:latest
Example: image: myproject-backend:latest
Multi-Stage Builds:

Frontend (React/Vue/Angular): Build → use 'serve' package (NOT nginx!)
⚠️ NEVER USE nginx for React/Vue/Angular SPAs - use 'serve' with -s flag for SPA routing
Go: Build → alpine runtime

⚠️⚠️⚠️ CRITICAL: BUILD OUTPUT DIRECTORY DETECTION ⚠️⚠️⚠️
This is the #1 cause of frontend Docker build failures!

MUST READ SERVICE DEFINITIONS for build_output field:
- If Service has "build_output: build" → use /app/build in COPY --from=build
- If Service has "build_output: dist" → use /app/dist in COPY --from=build

ERROR PATTERN RECOGNITION (READ LOGS CAREFULLY):
1. If logs contain "cra.link/deployment" or "react-scripts build" → It's CRA → use /app/build (NOT /app/dist!)
2. If logs contain "vite" → It's Vite → use /app/dist
3. If error is "/app/dist: not found" and logs show CRA → The fix is to use /app/build instead!

EXAMPLE ERROR AND FIX:
Error: COPY --from=build /app/dist → "not found"
Logs show: "https://cra.link/deployment"
FIX: Change to COPY --from=build /app/build

LANGUAGE-SPECIFIC PATTERNS

CRITICAL DOCKERFILE SYNTAX RULES:
1. Verification headers MUST be on ONE LINE - NO LINE BREAKS!
2. MUST start with # symbol
3. MUST be followed immediately by FROM instruction on next line

INVALID (causes Docker parse error):
# VERIFICATION: runtime=node:20-alpine,
port=8888                               <-- LINE BREAK CAUSES ERROR!

VALID (single line):
# VERIFICATION: runtime=node:20-alpine, port=8888
FROM node:20-alpine

Node.js Backend:

# VERIFICATION: runtime=node:20-alpine, port=8888, start_cmd=node src/index.js
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
ENV NODE_ENV=production
ENV PORT=8888
EXPOSE 8888
CMD ["node", "src/index.js"]

⚠️ NEVER LEAVE PLACEHOLDER COMMENTS in your generated Dockerfiles!
BAD: CMD ["node", "app.js"]  # REPLACE with actual entry
GOOD: CMD ["node", "src/index.js"]  (just the actual value from metadata)

You MUST read metadata.start_command and use it directly. Example:
- If metadata.start_command = "node server/index.js" → CMD ["node", "server/index.js"]

React/CRA Frontend (build/ output):

# VERIFICATION: runtime=node:20-alpine, build_output=build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/build ./static
EXPOSE 80
CMD ["serve", "-s", "static", "-l", "80"]

Vite Frontend (dist/ output):

# VERIFICATION: runtime=node:20-alpine, build_output=dist
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./static
EXPOSE 80
CMD ["serve", "-s", "static", "-l", "80"]
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
Before generating, verify you extracted: ☑ Runtime from metadata.runtime (NOT node:14 default) ☑ Backend port from metadata.backend_port (NOT 3000 default) ☑ Frontend port from metadata.frontend_port (NOT 3000 default) ☑ Database port from metadata.database_port ☑ Build command from metadata.build_command ☑ Start command from metadata.start_command ☑ Service paths from Service Definitions ☑ Added image: field to ALL compose services ☑ Used official images for databases (no Dockerfile) ☑ Added verification comments to all files ☑ ALL verification comments are on SINGLE LINE (no line breaks!) ☑ For React/Vue/Angular frontends, used 'serve -s' NOT nginx! ☑ For frontend COPY --from=build: Used SERVICE'S build_output (CRA→/app/build, Vite→/app/dist)

⚠️ CRITICAL: Verification comments with line breaks cause Docker parse errors!
⚠️ CRITICAL: For SPAs (React/Vue/Angular), you MUST use 'serve -s' package, NOT nginx!
⚠️ CRITICAL: If logs show 'cra.link/deployment' or 'react-scripts', use /app/build NOT /app/dist!

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
    
    # Add database cloud/local info (CRITICAL for compose generation)
    if metadata.get("database_is_cloud") is not None:
        is_cloud = metadata.get("database_is_cloud")
        env_var = metadata.get("database_env_var", "DB_URL")
        if is_cloud:
            lines.append(f"metadata.database_is_cloud = True  # ⚠️ DO NOT add database container! Just pass {env_var} to backend")
        else:
            lines.append(f"metadata.database_is_cloud = False  # Add database container to compose")
        if env_var:
            lines.append(f"metadata.database_env_var = {env_var}")

    build_cmd = metadata.get("build_command")
    start_cmd = metadata.get("start_command")
    entry_point = metadata.get("entry_point")
    build_output = metadata.get("build_output")
    
    if build_cmd:
        lines.append(f"metadata.build_command = {build_cmd}")
    if start_cmd:
        lines.append(f"metadata.start_command = {start_cmd}")
    if entry_point:
        lines.append(f"metadata.entry_point = {entry_point}  # CRITICAL: Use this in Dockerfile CMD, NOT server.js")
    if build_output:
        lines.append(f"metadata.build_output = {build_output}  # CRITICAL: Use /app/{build_output} in COPY --from=build, NOT /app/dist!")

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
        lines = ["Service Definitions (USE THESE VALUES, NOT DEFAULTS!):"]
        for svc in services:
            svc_line = f"- name: {svc.get('name', 'unknown')}, path: {svc.get('path', '.')}, type: {svc.get('type', 'unknown')}"
            
            # Include port for all services (CRITICAL for correct EXPOSE and ports)
            if svc.get('port'):
                port_src = svc.get('port_source', 'default')
                svc_line += f", PORT: {svc.get('port')} (from {port_src} - USE THIS VALUE!)"
            
            # Include build_output for frontend services (CRITICAL for correct COPY path)
            if svc.get('build_output'):
                svc_line += f", build_output: {svc.get('build_output')} (USE /app/{svc.get('build_output')})"
            
            # Include env_file for services with .env (CRITICAL for docker-compose env injection)
            if svc.get('env_file'):
                svc_line += f", env_file: {svc.get('env_file')} (ADD TO COMPOSE: env_file: ['{svc.get('env_file')}'])"
            
            # Include database cloud/local info (CRITICAL for compose generation)
            if svc.get('type') == 'database':
                is_cloud = svc.get('is_cloud', False)
                if is_cloud:
                    svc_line += f", is_cloud: True (DO NOT ADD THIS TO COMPOSE - use backend env var instead!)"
                else:
                    docker_image = svc.get('docker_image', 'mongo:latest')
                    svc_line += f", is_cloud: False, docker_image: {docker_image} (ADD TO COMPOSE!)"
            
            lines.append(svc_line)
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

