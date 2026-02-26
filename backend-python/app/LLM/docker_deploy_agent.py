from typing import Dict, List, Optional

from .llm_client import call_llama

# System prompt dedicated to Docker deployment analysis/generation
DOCKER_DEPLOY_SYSTEM_PROMPT = """You are a Docker configuration generator. Produce CORRECT, WORKING Docker configs with ZERO errors.
Use ONLY values from the input. Never assume or invent values. Service definitions override metadata values.

STEP 1: EXTRACT VALUES FROM INPUT
- PROJECT_NAME, RUNTIME, BACKEND_PORT, FRONTEND_PORT, DATABASE, DATABASE_PORT, DATABASE_IS_CLOUD
- Per-service: name, path, type, port, entry_point, build_output, env_file, package_manager

STEP 2: DETERMINE TYPE PER SERVICE
- STATIC_ONLY=True or RUNTIME contains "nginx" -> Static site
- type=frontend AND build_output set -> Frontend (React/Vue with build step)
- type=backend -> Backend (Node.js server)

STEP 3: GENERATE DOCKERFILES

--- STATIC SITE ---
FROM nginx:alpine
WORKDIR /usr/share/nginx/html
COPY . .
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
No Node.js, no npm, no build steps, no multi-stage.

--- BACKEND (single-stage ONLY) ---
FROM {RUNTIME}
WORKDIR /app
COPY package*.json ./
RUN {INSTALL_CMD}
COPY . .
ENV PORT={service.port}
EXPOSE {service.port}
CMD {CMD_ARRAY}

Rules:
- ONE "FROM" only. No multi-stage, no "AS builder", no nginx.
- EXCEPTION: TypeScript backends — add "RUN npm run build" (or tsc) BEFORE CMD, and set CMD to the compiled output (e.g. ["node", "dist/index.js"]). Still single-stage.
- INSTALL_CMD: npm+lockfile="npm ci", npm+no lockfile="npm install", yarn="yarn install --frozen-lockfile", pnpm="pnpm install --frozen-lockfile"
- CMD priority: service.entry_point -> ["node", "{entry_point}"], else START_COMMAND -> ["npm", "start"], else ["node", "index.js"]
- PORT: use service.port if defined, else BACKEND_PORT
- ALWAYS add ENV PORT={service.port} before EXPOSE to provide a fallback if .env is missing.
- COPY paths are relative to build context (COPY package*.json ./ NOT COPY backend/package*.json ./)

--- FRONTEND (multi-stage REQUIRED) ---
FROM {RUNTIME} AS builder
WORKDIR /app
COPY package*.json ./
RUN {INSTALL_CMD}
COPY . .
RUN {BUILD_CMD}

FROM nginx:alpine
COPY --from=builder /app/{BUILD_OUTPUT} /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

Rules:
- MUST have two FROM statements.
- BUILD_CMD: npm="npm run build", yarn="yarn build", pnpm="pnpm build"
- BUILD_OUTPUT: use service.build_output, or "dist" for Vite, "build" for CRA
- COPY --from=builder MUST use absolute path /app/{build_output} (NEVER relative like "dist .")
- Container always uses port 80 internally.

--- NEXT.JS FRONTEND (special case) ---
Next.js uses SSR and MUST NOT use nginx. Use node in production:
FROM {RUNTIME} AS builder
WORKDIR /app
COPY package*.json ./
RUN {INSTALL_CMD}
COPY . .
RUN {BUILD_CMD}

FROM {RUNTIME}
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
EXPOSE {service.port}
CMD ["npm", "start"]

Detect Next.js when: build_output=".next", or framework contains "next", or next.config.js exists.
Never use nginx for Next.js. Container uses the app port (e.g. 3000), NOT 80.

STEP 4: GENERATE DOCKER-COMPOSE.YML

Every service MUST have both "image:" and "build:" fields.

Backend service:
  {name}:
    image: {PROJECT_NAME}-{name}:latest
    build: ./{path}
    ports:
      - "{service.port}:{service.port}"
    env_file:               # only if service.env_file exists
      - ./{path}/.env
    depends_on:             # only if DATABASE_IS_CLOUD=False
      - {db_service}

Frontend service:
  {name}:
    image: {PROJECT_NAME}-{name}:latest
    build: ./{path}
    ports:
      - "{FRONTEND_PORT}:80"
    depends_on:
      - {backend_name}

Database service (ONLY if DATABASE_IS_CLOUD=False):
  MongoDB:  image: mongo:latest, ports: {DB_PORT}:{DB_PORT}, volumes: mongo-data:/data/db, NO environment vars
  Postgres: image: postgres:latest, POSTGRES_PASSWORD: postgres, volumes: postgres-data:/var/lib/postgresql/data
  MySQL:    image: mysql:latest, MYSQL_ROOT_PASSWORD: root, volumes: mysql-data:/var/lib/mysql
  Redis:    image: redis:alpine, volumes: redis-data:/data

Add "volumes:" section at bottom if database present.

depends_on chain: frontend -> backend -> database (frontend never depends on database directly)

STEP 5: VALIDATE BEFORE RESPONDING
- Backend: single-stage, correct port, correct CMD entry_point, no "npm run build"
- Frontend: multi-stage, port 80, COPY --from uses /app/{build_output}
- Compose: no "version:", all services have image+build, correct port mappings, database only if not cloud
- All COPY paths relative to build context (no service path prefix)

STEP 6: RESPOND

FORMAT:
STATUS: Generated (or Valid/Invalid for validation mode)

REASON:
- Summary of each generated file

GENERATED FILES:

**{path}/Dockerfile**
```dockerfile
{complete content}
```

**docker-compose.yml**
```yaml
{complete content}
```

VALIDATION MODE (when existing Dockerfiles/compose are provided):
Compare against input values. Respond "Valid" if correct, "Invalid" with specific issues if not.

--- EXAMPLE ---
INPUT: PROJECT_NAME=myapp, RUNTIME=node:20-alpine, services=[backend(port:5000, entry_point:server.js, npm ci), frontend(build_output:dist, npm ci)]
DATABASE_IS_CLOUD=True (MongoDB Atlas)

OUTPUT:

STATUS: Generated

REASON:
- Generated backend Dockerfile (single-stage, port 5000, node server.js)
- Generated frontend Dockerfile (multi-stage, nginx, dist)
- Generated docker-compose.yml (2 services, no DB container - cloud DB)

GENERATED FILES:

**backend/Dockerfile**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5000
CMD ["node", "server.js"]
```

**frontend/Dockerfile**
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**docker-compose.yml**
```yaml
services:
  backend:
    image: myapp-backend:latest
    build: ./backend
    ports:
      - "5000:5000"
    env_file:
      - ./backend/.env
  frontend:
    image: myapp-frontend:latest
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```
--- END EXAMPLE ---

Provide COMPLETE file contents. No placeholders, no "...", no template variables like ${X}.
"""



def _format_metadata(metadata: Dict) -> str:
    """Format metadata in a structured way that's easy for LLM to parse."""
    if not metadata:
        return "Metadata: unavailable"

    # Use DIRECT VALUE format - avoid 'metadata.X' pattern that LLM treats as template variable
    # Format: KEY: VALUE ← USE THIS EXACT VALUE
    lines = [
        "=== CONFIGURATION VALUES (USE THESE EXACT VALUES) ===",
    ]
    
    # Add STATIC_ONLY flag FIRST if true (CRITICAL for correct Dockerfile type)
    static_only = metadata.get('static_only', False)
    if static_only:
        lines.append("⚠️ STATIC_ONLY: True ← USE nginx:alpine, NO npm, NO node, NO build step!")
    
    lines.extend([
        f"RUNTIME: {metadata.get('runtime', 'node:20-alpine')} ← USE IN: FROM {metadata.get('runtime', 'node:20-alpine')}",
        f"BACKEND_PORT: {metadata.get('backend_port', 8000)} ← USE IN: EXPOSE {metadata.get('backend_port', 8000)}, ports: \"{metadata.get('backend_port', 8000)}:{metadata.get('backend_port', 8000)}\"",
        f"FRONTEND_PORT: {metadata.get('frontend_port', 3000)} ← USE IN: ports: \"{metadata.get('frontend_port', 3000)}:80\"",
        f"DATABASE: {metadata.get('database', 'Unknown')}",
        f"DATABASE_PORT: {metadata.get('database_port', 27017)}",
        f"FRAMEWORK: {metadata.get('framework', 'Unknown')}",
        f"LANGUAGE: {metadata.get('language', 'Unknown')}",
    ])
    
    # Add database cloud/local info (CRITICAL for compose generation)
    if metadata.get("database_is_cloud") is not None:
        is_cloud = metadata.get("database_is_cloud")
        env_var = metadata.get("database_env_var", "DB_URL")
        if is_cloud:
            lines.append(f"DATABASE_IS_CLOUD: True ← DO NOT add database container! Just pass {env_var} to backend")
        else:
            lines.append(f"DATABASE_IS_CLOUD: False ← Add database container to compose")
        if env_var:
            lines.append(f"DATABASE_ENV_VAR: {env_var}")

    build_cmd = metadata.get("build_command")
    start_cmd = metadata.get("start_command")
    entry_point = metadata.get("entry_point")
    build_output = metadata.get("build_output")
    
    # Check if this is a multi-service project (services with their own entry_point)
    services = metadata.get("services", [])
    has_service_entry_points = any(svc.get("entry_point") for svc in services if svc.get("type") == "backend")
    
    if build_cmd:
        lines.append(f"BUILD_COMMAND: {build_cmd}")
    
    # Only include start_command and entry_point for single-service projects
    # For multi-service, the service definitions have the correct paths
    if start_cmd and not has_service_entry_points:
        lines.append(f"START_COMMAND: {start_cmd}")
    if entry_point and not has_service_entry_points:
        lines.append(f"ENTRY_POINT: {entry_point} ← USE IN: CMD [\"node\", \"{entry_point}\"]")
    elif has_service_entry_points:
        # Show the service entry_points for clarity
        backend_entries = [f"{svc.get('name')}: {svc.get('entry_point')}" 
                          for svc in services if svc.get("type") == "backend" and svc.get("entry_point")]
        lines.append(f"# For multi-service: Use entry_point from Service Definitions ({', '.join(backend_entries)})")
        
    if build_output:
        lines.append(f"BUILD_OUTPUT: {build_output} ← FRONTEND ONLY! NOT for backend!")

    env_vars = metadata.get("env_variables") or []
    if env_vars:
        lines.append(f"Environment variables: {', '.join(env_vars[:15])}")

    deps = metadata.get("dependencies") or []
    if deps:
        shown = ", ".join(deps[:10])
        if len(deps) > 10:
            shown += " ..."
        lines.append(f"Dependencies: {shown}")
    
    lines.append("=== END CONFIGURATION VALUES ===")

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
        f"PROJECT_NAME: {project_name} ← USE IN: image: {project_name}-backend:latest, image: {project_name}-frontend:latest",
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
            
            # Include package_manager for correct install/build commands
            if svc.get('package_manager'):
                pm_info = svc.get('package_manager')
                # Handle both old string format and new dict format
                if isinstance(pm_info, dict):
                    pm = pm_info.get('manager', 'npm')
                    has_lock = pm_info.get('has_lockfile', True)
                else:
                    pm = pm_info
                    has_lock = True
                
                # Backend: install only, Frontend: install + build
                is_backend = svc.get('type') == 'backend'
                
                if pm == 'yarn':
                    if is_backend:
                        svc_line += f", package_manager: yarn (USE: yarn install --frozen-lockfile)"
                    else:
                        svc_line += f", package_manager: yarn (USE: yarn install --frozen-lockfile, yarn build)"
                elif pm == 'pnpm':
                    if is_backend:
                        svc_line += f", package_manager: pnpm (USE: pnpm install --frozen-lockfile)"
                    else:
                        svc_line += f", package_manager: pnpm (USE: pnpm install --frozen-lockfile, pnpm build)"
                elif has_lock:
                    if is_backend:
                        svc_line += f", package_manager: npm (USE: npm ci)"
                    else:
                        svc_line += f", package_manager: npm (USE: npm ci, npm run build)"
                else:
                    if is_backend:
                        svc_line += f", package_manager: npm, NO LOCKFILE (USE: npm install)"
                    else:
                        svc_line += f", package_manager: npm, NO LOCKFILE (USE: npm install, npm run build)"
            
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
            "1. Create a Dockerfile for EACH service directory (use the RUNTIME and PORT values provided above)\n"
            "2. Create docker-compose.yml at project root (with image: and build: fields for ALL services)\n"
            "Use EXACT values from the input. Provide complete file contents."
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


def run_docker_deploy_chat_stream(
    project_name: str,
    metadata: Dict,
    dockerfiles: List[Dict[str, str]],
    compose_files: List[Dict[str, str]],
    file_tree: Optional[str],
    user_message: str,
    logs: Optional[List[str]] = None,
    extra_instructions: Optional[str] = None,
    services: Optional[List[Dict[str, str]]] = None,
):
    """
    Streaming version of run_docker_deploy_chat.
    Yields tokens as they're generated by the LLM.
    """
    from .llm_client import call_llama_stream
    
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

    # Debug: Print metadata values and first 500 chars to see if sent correctly
    print(f"\n=== DEBUG: STREAMING LLM REQUEST ===")
    print(f"metadata.backend_port = {metadata.get('backend_port', 'NOT SET')}")
    print(f"metadata.frontend_port = {metadata.get('frontend_port', 'NOT SET')}")
    print(f"metadata.runtime = {metadata.get('runtime', 'NOT SET')}")
    print(f"Mode: {mode}")
    print(f"Message (first 1000 chars):\n{message[:1000]}\n===")


    # Yield tokens from the streaming LLM call
    for chunk in call_llama_stream(
        [
            {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
    ):
        yield chunk

