from typing import Dict, List, Optional

from .llm_client import call_llama

# System prompt dedicated to Docker deployment analysis/generation
DOCKER_DEPLOY_SYSTEM_PROMPT = """You generate Docker configurations based on project metadata.

⚠️⚠️⚠️ CRITICAL RULES - READ FIRST ⚠️⚠️⚠️
1. BACKEND = SINGLE-STAGE! Only ONE "FROM". NO "as builder". NO "COPY --from". NO nginx.
2. FRONTEND = MULTI-STAGE! Use "FROM ... as builder", then "FROM nginx:alpine", then "COPY --from=builder".
3. Backend does NOT need npm run build - just install and run directly.
4. Only use values from metadata - never assume.
⚠️⚠️⚠️ END CRITICAL RULES ⚠️⚠️⚠️

## HOW TO READ INPUT

You will receive:
1. PROJECT_NAME(lowercase only) → Use for image names: {PROJECT_NAME}-backend:latest
2. RUNTIME → Use in FROM instruction
3. BACKEND_PORT → Use in ENV PORT, EXPOSE, and compose ports
4. FRONTEND_PORT → Use in compose ports (maps to container port 80)
5. DATABASE → Type of database (MongoDB, PostgreSQL, MySQL, Redis)
6. DATABASE_PORT → Port for database container
7. DATABASE_IS_CLOUD → If True, skip database container; If False, add it

Service Definitions contain per-service info:
- path → build context in compose: build: ./{path}
- port → EXPOSE and compose ports for this service
- entry_point → CMD path (e.g., CMD ["node", "{entry_point}"])
- build_output → COPY path in multi-stage (dist or build)
- env_file → env_file directive in compose
- docker_image → database container image (for database services)
- is_cloud → skip container if True

## GENERATE MODE

⚠️ FIRST: CHECK STATIC_ONLY FLAG ⚠️
- If STATIC_ONLY=True → This is a STATIC SITE (use nginx, NO Node.js, NO npm, NO build!)
- If RUNTIME contains "nginx" → Also a STATIC SITE
- Otherwise → Node.js project

### STATIC SITE (STATIC_ONLY=True or RUNTIME=nginx)
- FROM nginx:alpine
- COPY . /usr/share/nginx/html
- EXPOSE 80
- CMD ["nginx", "-g", "daemon off;"]
- NO npm, NO node, NO package.json, NO build step, NO multi-stage

### NODE.JS BACKEND (type=backend)
- FROM {RUNTIME} (e.g., node:20-alpine)
- ⚠️ NO MULTI-STAGE! Single FROM only. No nginx. No COPY --from.
- CMD ["node", "{entry_point}"] or ["npm", "start"]
- EXPOSE {BACKEND_PORT}
- NO build step needed for backend (runs directly with node)

### NODE.JS FRONTEND (type=frontend with build_output)
- Multi-stage build required
- Stage 1: COPY package*.json, npm install, COPY . . (REQUIRED!), npm run build
- Stage 2: RUN npm install -g serve, COPY {build_output}, CMD ["serve", "-s", "static", "-l", "80"]
- build_output: dist (Vite) or build (CRA)
- Container EXPOSE 80 (NOT dev port like 3000/5173)

### Next.js (framework=Next.js)
- Multi-stage, copy .next folder
- EXPOSE 3000, CMD ["npm", "start"]

### Docker Compose
DO NOT include 'version:' attribute (obsolete in Docker Compose v2).

For each service in Service Definitions:
```yaml
services:
  {service.name}:
    image: {PROJECT_NAME}-{service.name}:latest
    build: ./{service.path}
    ports:
      - "{service.port}:{container_port}"
    env_file:
      - {service.env_file}  # ⚠️ REQUIRED if env_file is defined! Check Service Definitions.
```

⚠️ ENV_FILE RULE: If a service has env_file defined in Service Definitions, you MUST add it to compose!

Service dependency rules:
- BACKEND depends_on database (if is_cloud=False)
- FRONTEND does NOT depend on database! Frontend talks to backend, not DB directly
- Add depends_on only to services that need to wait for another service

Database service (only if is_cloud=False):
```yaml
  {database_name}:
    image: {docker_image}
    ports:
      - "{DATABASE_PORT}:{DATABASE_PORT}"
    volumes:
      - {database_name}-data:{volume_path}

volumes:  # REQUIRED - declare named volumes at bottom
  {database_name}-data:
```

Database-specific rules:
- MongoDB: NO environment needed - just image, ports, volume (volume path: /data/db)
- PostgreSQL: ADD environment: POSTGRES_PASSWORD (volume path: /var/lib/postgresql/data)
- MySQL: ADD environment: MYSQL_ROOT_PASSWORD (volume path: /var/lib/mysql)

NEVER add hardcoded credentials to MongoDB containers!

### Backend CMD Logic
- If entry_point exists (e.g., src/server.js) → CMD ["node", "{entry_point}"]
- If only start_command exists (e.g., npm start) → CMD ["npm", "start"]
- Use entry_point if available, fall back to start_command

## KEY RULES

1. NEVER hardcode values - always read from metadata
2. NEVER use ${VARIABLE} syntax - use actual values from input
3. Use env_file to inject entire .env file, not individual vars
4. CMD path is RELATIVE to service directory (from entry_point)
5. Frontend container always uses port 80 internally
6. Skip database container if is_cloud=True
7. CRITICAL: ALL PATHS IN DOCKERFILE ARE RELATIVE TO BUILD CONTEXT
   - If compose has build: ./backend, then Dockerfile is built from INSIDE backend/
   - COPY paths must NOT include the service folder name!
   - WRONG: COPY backend/package.json ./ (looks for /backend/backend/package.json)
   - CORRECT: COPY package.json ./ (looks for /backend/package.json)
   - WRONG: COPY backend/src ./src
   - CORRECT: COPY src ./src
   - WRONG: COPY backend/. .
   - CORRECT: COPY . .

## PACKAGE MANAGER
Read package_manager from Service Definitions:
- npm (with lockfile) → RUN npm ci, RUN npm run build
- npm (NO LOCKFILE) → RUN npm install, RUN npm run build (NEVER use npm ci without lockfile!)
- yarn → RUN yarn install --frozen-lockfile, RUN yarn build
- pnpm → RUN pnpm install --frozen-lockfile, RUN pnpm build

## TYPESCRIPT
- If entry_point ends in .ts → use compiled output or ts-node

## RESPONSE FORMAT

STATUS: Generated

REASON:
- Generated {service.name} Dockerfile using {values from metadata}
- Generated docker-compose.yml with {list services}

GENERATED FILES:

**{service.path}/Dockerfile**
```dockerfile
<content using actual values from metadata>
```

**docker-compose.yml**
```yaml
<content using actual values from metadata>
```

## VALIDATE MODE

Compare existing Dockerfiles against metadata:
- Does EXPOSE match {BACKEND_PORT}?
- Does FROM match {RUNTIME}?
- Does CMD match {entry_point}?
- Does build_output match {build_output}?
- Do compose ports match service ports?
- Do compose volumes match service volumes?
- Refer to Logs for Debugging (if any)
Say "Valid" if files work.
Say "Invalid" only for blocking errors (syntax, missing files).

## FINAL CHECKLIST (verify before responding)
☐ Every compose service has image: {PROJECT_NAME}-{service.name}:latest
☐ Every Dockerfile has COPY . . before npm run build
☐ env_file included if service has env_file defined
☐ No database container if DATABASE_IS_CLOUD=True
☐ Backend Dockerfile is SINGLE-STAGE (only one FROM, no nginx, no COPY --from)
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

