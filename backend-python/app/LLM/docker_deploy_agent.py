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
NOTE: In GENERATE mode, use metadata.runtime strictly.
In VALIDATE mode, older runtimes (node:14, node:16) are OK if functional - treat as WARNING not error.
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

=== MODE = VALIDATE_EXISTING ===
Purpose: Check if existing Docker files will WORK, not if they match our conventions.

VALIDATION RULES (more flexible than GENERATE):
1. Runtime mismatch → FLAG as WARNING, not error. Example:
   - Dockerfile: FROM node:16-buster (older but functional)
   - metadata.runtime: node:20-alpine (our default)
   - Result: "Partially Valid" - suggest upgrade but DON'T mark as Invalid

2. Missing verification comments → OK in existing files (only required for GENERATE)

3. Using nginx instead of 'serve' for SPAs → OK if config is correct (WARNING only)

4. Existing database services → KEEP them if they work, even if metadata.database_is_cloud=True
   Reason: User may have intentionally set up local DB for development

5. Port differences → WARNING if different from metadata but functional

Only mark as "Invalid" if configuration will ACTUALLY FAIL:
- Missing required files (CMD target doesn't exist)
- Syntax errors in Dockerfile/compose
- Incompatible settings (wrong architecture, missing dependencies)

DO NOT generate new files unless explicitly requested
Focus on concrete, actionable fixes

=== MODE = GENERATE_MISSING ===
Purpose: Generate production-ready Docker configurations from scratch.

GENERATION RULES (STRICT):
MUST generate files for ALL services in Service Definitions
MUST add verification comment header to EVERY generated file
MUST use metadata.runtime exactly as specified
Generate: backend/Dockerfile, frontend/Dockerfile, docker-compose.yml (as needed)

⚠️⚠️⚠️ CRITICAL: env_file DIRECTIVE ⚠️⚠️⚠️
CHECK Service Definitions for "env_file:" field!
If a service has env_file (e.g., "env_file: ./backend/.env"), you MUST use:
```yaml
backend:
  env_file:
    - ./backend/.env
```
DO NOT use "environment: - DB_URL=${DB_URL}" when env_file is present!
The env_file directive loads ALL variables from the .env file automatically.

CRITICAL RULES:

Database Services (SMART CLOUD VS LOCAL DETECTION):

FOR GENERATE MODE:
- If is_cloud=True → DO NOT add database container, pass env vars to backend
- If is_cloud=False (needs_container=True) → Add database container to compose

FOR VALIDATE MODE:
- If existing compose has a working database service → KEEP IT regardless of is_cloud flag
- Only suggest removal if explicitly requested or causing conflicts

CLOUD DATABASE (e.g., MongoDB Atlas, AWS RDS, Supabase) - GENERATE MODE:
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

Frontend (React/Vue/Angular):
  GENERATE MODE: Use 'serve' package with -s flag for SPA routing (preferred)
  VALIDATE MODE: nginx is acceptable if correctly configured (with try_files for SPA routing)
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
RUN npm install --omit=dev
COPY . .
ENV NODE_ENV=production
ENV PORT=8888
EXPOSE 8888
CMD ["node", "src/index.js"]

⚠️ NEVER LEAVE PLACEHOLDER COMMENTS in your generated Dockerfiles!
BAD: CMD ["node", "app.js"]  # REPLACE with actual entry
GOOD: CMD ["node", "src/index.js"]  (just the actual value from metadata)

⚠️⚠️⚠️ CRITICAL: PATH CONTEXT FOR MULTI-SERVICE PROJECTS ⚠️⚠️⚠️
When docker-compose uses "build: ./api", the Dockerfile is built from INSIDE the api/ directory!
The CMD path must be RELATIVE TO THE SERVICE DIRECTORY, not the project root!

Example:
- Project structure: api/index.js
- docker-compose: build: ./api
- WRONG: CMD ["node", "api/index.js"]  ← This looks for /app/api/index.js (doesn't exist!)
- CORRECT: CMD ["node", "index.js"]    ← This looks for /app/index.js (correct!)

Check Service Definitions for the service "path" field:
- If path = "api/" and entry is "index.js" → CMD ["node", "index.js"]
- If path = "." and entry is "api/index.js" → CMD ["node", "api/index.js"]

React/CRA Frontend (build/ output):

# VERIFICATION: runtime=node:20-alpine, build_output=build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
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
Docker Compose (Multi-Service MERN with env_file):

# VERIFICATION: backend_port=8888, frontend_port=5173, db_port=27017
version: '3.9'
services:
  backend:
    image: project-backend:latest  # REQUIRED for push
    build: ./backend
    ports:
      - "8888:8888"  # Use metadata.backend_port
    env_file:
      - ./backend/.env  # ← USE THIS when service has env_file defined
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
STATUS: Valid / Invalid / Partially Valid / Not Found / Generated

VALIDATION STATUS GUIDELINES:
- "Valid": Configuration will work as-is, fully functional
- "Partially Valid": Configuration works but has improvement opportunities (runtime upgrade, optimization)
- "Invalid": Configuration has actual errors that will cause build/run failures
- "Not Found": No Docker files exist
- "Generated": New files were created (GENERATE mode only)

In VALIDATE mode, prefer "Partially Valid" with WARNINGS over "Invalid" for minor issues like:
- Older but functional runtime versions
- Missing verification comments
- Using nginx instead of serve (if correctly configured)
- Port differences that don't break functionality

Only use "Invalid" for actual breaking issues!

REASON:
Bullet points explaining status
Must cite concrete evidence from files/metadata/logs
For VALIDATE mode: Distinguish between ERRORS (breaking) and WARNINGS (improvement suggestions)

FIXES or GENERATED DOCKERFILES:
For VALIDATE: Show specific fixes with line numbers. Label as REQUIRED FIX or SUGGESTED IMPROVEMENT
For GENERATE: Provide COMPLETE file contents with verification headers

LOG ANALYSIS:
Summarize key issues from logs or "No logs provided"

FINAL EXECUTION CHECKLIST (Run before responding)

=== FOR GENERATE MODE (STRICT) ===
☑ Runtime from metadata.runtime (NOT node:14 default)
☑ Backend port from metadata.backend_port (NOT 3000 default)
☑ Frontend port from metadata.frontend_port (NOT 3000 default)
☑ Database port from metadata.database_port
☑ Build command from metadata.build_command
☑ Start command from metadata.start_command
☑ Service paths from Service Definitions
☑ Added image: field to ALL compose services
☑ Used official images for databases (no Dockerfile)
☑ Added verification comments to all files
☑ ALL verification comments are on SINGLE LINE (no line breaks!)
☑ For React/Vue/Angular frontends, used 'serve -s' (preferred)
☑ For COPY --from=build: Used SERVICE'S build_output

=== FOR VALIDATE MODE (FLEXIBLE) ===
☑ Check if existing runtime is functional (older versions OK with WARNING)
☑ Verify ports will work (differences from metadata are WARNING not error)
☑ Check CMD/ENTRYPOINT points to existing files
☑ Verify syntax is correct
☑ Missing verification comments → OK (not required for existing files)
☑ nginx for SPAs → OK if correctly configured (WARNING to suggest serve)
☑ Existing db service → KEEP if functional

⚠️ CRITICAL: Verification comments with line breaks cause Docker parse errors!
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
    
    # Check if this is a multi-service project (services with their own entry_point)
    services = metadata.get("services", [])
    has_service_entry_points = any(svc.get("entry_point") for svc in services if svc.get("type") == "backend")
    
    if build_cmd:
        lines.append(f"metadata.build_command = {build_cmd}")
    
    # Only include start_command and entry_point for single-service projects
    # For multi-service, the service definitions have the correct paths
    if start_cmd and not has_service_entry_points:
        lines.append(f"metadata.start_command = {start_cmd}")
    if entry_point and not has_service_entry_points:
        lines.append(f"metadata.entry_point = {entry_point}  # CRITICAL: Use this in Dockerfile CMD")
    elif has_service_entry_points:
        # Show the service entry_points for clarity
        backend_entries = [f"{svc.get('name')}: {svc.get('entry_point')}" 
                          for svc in services if svc.get("type") == "backend" and svc.get("entry_point")]
        lines.append(f"# For multi-service: Use entry_point from Service Definitions ({', '.join(backend_entries)})")
        lines.append(f"# NOTE: metadata.entry_point={entry_point} is the ROOT path, NOT the service-relative path!")
        
    if build_output:
        lines.append(f"metadata.build_output = {build_output}  # CRITICAL: Use /app/{build_output} in COPY --from=build")

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
        lines = ["⚠️⚠️⚠️ SERVICE DEFINITIONS (OVERRIDES metadata for multi-service!) ⚠️⚠️⚠️", 
                 "For each service, use ITS entry_point (relative to service dir), NOT metadata.entry_point!"]
        for svc in services:
            svc_line = f"- name: {svc.get('name', 'unknown')}, path: {svc.get('path', '.')}, type: {svc.get('type', 'unknown')}"
            
            # Include port for all services (CRITICAL for correct EXPOSE and ports)
            if svc.get('port'):
                port_src = svc.get('port_source', 'default')
                svc_line += f", PORT: {svc.get('port')} (from {port_src} - USE THIS VALUE!)"
            
            # Include entry_point for backend services (CRITICAL for correct CMD path)
            if svc.get('entry_point'):
                svc_line += f", entry_point: {svc.get('entry_point')} (USE THIS IN CMD: node {svc.get('entry_point')})"
            
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

