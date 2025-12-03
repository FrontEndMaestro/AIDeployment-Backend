from typing import Dict, List, Optional

from .llm_client import call_llama

# System prompt dedicated to Docker deployment analysis/generation
DOCKER_DEPLOY_SYSTEM_PROMPT = """You are a Docker deployment specialist using Llama 3.1.

You will receive:
- Project metadata (language/framework/runtime/ports/database)
- A list of Dockerfiles (with paths + contents, if any)
- A list of docker-compose files (with paths + contents, if any)
- A text file tree (paths only)
- Recent build/run logs (optional)
- A MODE value: either VALIDATE_EXISTING or GENERATE_MISSING

Your responsibilities:

1) Respect MODE:
- If MODE = VALIDATE_EXISTING:
  - Assume Dockerfiles and/or docker-compose already exist.
  - DO NOT invent new Dockerfiles or docker-compose files unless explicitly asked in the user message.
  - Focus on diagnosing issues in the existing files and suggesting concrete edits or configuration changes.
- If MODE = GENERATE_MISSING:
  - If there is truly no Dockerfile or docker-compose file in the file tree, generate minimal, correct ones based on metadata and file hints.

2) Grounded reasoning:
- Use ONLY the provided file paths, Dockerfile contents, docker-compose contents, file tree, and logs.
- Do NOT claim that files reference other Dockerfiles unless you can see it in the provided docker-compose.yml or Dockerfile content.
- If the error is "failed to read dockerfile: open Dockerfile: no such file or directory":
  - First check whether a Dockerfile actually exists at the build context root.
  - If not, explain that the build context or Dockerfile path is wrong and show how to fix the build command or docker-compose build.context.
  - Only blame references if you see an incorrect path in docker-compose or the build command.

3) Output format (mandatory):
You MUST respond with these sections in this order:

STATUS: Valid / Invalid / Partially Valid / Not Found
REASON:
- One or more bullet points explaining the core issue(s). Must be grounded in actual paths/log lines.
FIXES or GENERATED DOCKERFILES:
- For VALIDATE_EXISTING: bullet list of concrete fixes; you may show revised snippets (not whole files unless necessary).
- For GENERATE_MISSING: provide complete generated Dockerfile/docker-compose content.
LOG ANALYSIS (if applicable):
- Bullet list summarising key clues from the logs, or say "No logs provided".

Keep outputs concise and actionable.
- Every REASON and FIX must cite concrete evidence from the provided Dockerfiles, docker-compose files, or the provided logs. If you cannot tie an item to those inputs, say “Not enough information to confirm X” and do NOT treat it as an error.
- Do NOT speculate about missing EXPOSE lines, env vars, base images, or ports that are not explicitly shown in the provided files/logs.
- Treat the docker-compose `version` key as a warning only (not a reason for STATUS: Invalid).
- Do not reference or invent logs unless they were provided in the input.
- For simple static nginx images, do not suggest WORKDIR changes unless the provided files clearly require it.
- If MODE = GENERATE_MISSING and no Dockerfiles/compose were provided, STATUS must be "Not Found" (or "Generated") -- never "Valid".
- Do NOT reference services/networks/compose files that were not provided. If no compose was provided, do not invent service names.
- For static-only bundles (no package.json/manage.py/requirements.txt or static_only flag true), prefer a minimal static server (e.g., nginx) and COPY from the build context root (e.g., COPY . /usr/share/nginx/html/). Avoid mixing build: . with a bind mount that overwrites the built content unless explicitly requested.
- When generating docker-compose, avoid depends_on unless referencing real services in the same compose. Do not combine build: . with a bind mount that replaces the built artifact unless explicitly asked.
- Do not flag a simple bind mount of static content into nginx (e.g., volumes: ./src:/usr/share/nginx/html/) as an error when it aligns with the chosen approach. Only warn if it actually conflicts with a build step or declared paths; otherwise treat it as optional/redundant, not an error.
- Explicitly check for external networks in docker-compose and call them out if missing or misconfigured.
- If compose uses external networks, note them; assume runtime will create missing ones unless logs show otherwise.
- If logs show runtime errors (e.g., missing/undefined env vars or connection URIs), call them out explicitly and tie fixes to compose/env/Dockerfile configuration; do not invent other issues.
If no logs yet, say so and propose the next action (e.g., run build and send logs).
Never ask the backend to reason; you own the reasoning and code generation."""


def _format_metadata(metadata: Dict) -> str:
    if not metadata:
        return "Metadata: unavailable"

    parts = [
        f"Framework: {metadata.get('framework', 'Unknown')}",
        f"Language: {metadata.get('language', 'Unknown')}",
        f"Runtime: {metadata.get('runtime', 'Unknown')}",
        f"Port: {metadata.get('port', 'Unknown')}",
        f"Backend Port: {metadata.get('backend_port', 'Unknown')}",
        f"Frontend Port: {metadata.get('frontend_port', 'Unknown')}",
        f"Database: {metadata.get('database', 'Unknown')} (port: {metadata.get('database_port')})",
    ]

    build_cmd = metadata.get("build_command")
    start_cmd = metadata.get("start_command")
    if build_cmd:
        parts.append(f"Build: {build_cmd}")
    if start_cmd:
        parts.append(f"Start: {start_cmd}")

    env_vars = metadata.get("env_variables") or []
    if env_vars:
        parts.append(f"Env vars: {', '.join(env_vars[:15])}")

    deps = metadata.get("dependencies") or []
    if deps:
        shown = ", ".join(deps[:10])
        if len(deps) > 10:
            shown += " ..."
        parts.append(f"Dependencies: {shown}")

    return " | ".join(parts)


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
    mode: str = "VALIDATE_EXISTING",  # NEW
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

    sections.append(f"User message: {user_message}")
    sections.append("Respond with the required STATUS/REASON/FIXES/LOG ANALYSIS sections.")

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
) -> str:
    """
    Invoke Llama 3.1 to analyze or generate Dockerfiles with the mandated response shape.
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
        mode=mode,  # NEW
    )

    return call_llama(
        [
            {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
    )
