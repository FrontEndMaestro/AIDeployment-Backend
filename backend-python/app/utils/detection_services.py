"""
Service inference — scans for Node.js and Python backend/frontend services,
merges stubs, suppresses phantom roots, and populates per-service fields.
Extracted from detector.py to reduce its size.
"""

import os
import json
import re
import shlex
try:
    import yaml
except ImportError:
    yaml = None
from typing import Dict, List, Optional

from .detection_constants import (
    BACKEND_DEPS,
    FRONTEND_DEPS,
    WORKER_DEPS,
    DB_DRIVER_ONLY_DEPS,
    SKIP_DIRS,
    PYTHON_BACKEND_DEPS,
    PYTHON_SKIP_DIRS,
    DB_KEYWORDS,
    norm_path,
)
from .command_extractor import (
    extract_nodejs_commands,
    extract_python_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info,
)
from .detection_ports import _scan_js_for_port_hint


_INFRA_DIRS = {
    "nginx", "docker", "k8s", "kubernetes", "terraform", "tf",
    "ansible", "helm", "ci", "jenkins", "toolbox", "tools",
    "data", "database", "db", "migrations", "seeds", "fixtures",
    "docs", "documentation", "scripts", "bin", "config", "configs",
    "test", "tests", "spec", "e2e", "__tests__", "coverage",
    "public", "static", "assets", "media", "vendor", "lib",
}

_SERVICE_INDICATOR_FILES = {
    "package.json", "requirements.txt", "pyproject.toml",
    "pom.xml", "build.gradle", "go.mod", "Gemfile",
    "Cargo.toml", "manage.py", "composer.json",
}


def _is_service_candidate(folder_path: str, folder_name: str) -> bool:
    """Return True only if the folder looks like a deployable service."""
    if folder_name.lower() in _INFRA_DIRS:
        return False
    try:
        return bool(set(os.listdir(folder_path)) & _SERVICE_INDICATOR_FILES)
    except (PermissionError, OSError):
        return False


def _infer_service_type(service_path: str, service_name: str, project_root: str) -> str:
    """
    Classify a service by reading its package.json deps first (Fix 4).
    Fix 6b: DB keyword names -> 'other' immediately.
    Falls back to name heuristic only if no package.json found.
    """
    pkg_path = os.path.join(project_root, service_path, "package.json")
    deps = {}
    is_be = False
    is_fe = False
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            dep_keys = set(deps.keys())
            ts_express_hint = (
                "@types/express" in dep_keys
                and bool(dep_keys & {"typescript", "ts-node", "tsx"})
                and not bool(dep_keys & FRONTEND_DEPS)
            )
            is_be = bool(dep_keys & BACKEND_DEPS) or ts_express_hint
            is_fe = bool(dep_keys & FRONTEND_DEPS)
            # Worker classification via deps
            worker_match = bool(dep_keys & WORKER_DEPS)
            db_only = bool(dep_keys & DB_DRIVER_ONLY_DEPS) and not is_be and not is_fe
            if worker_match:
                return "worker"
            if db_only:
                return "backend"  # has DB access but no web framework - treat as backend
            if is_be and is_fe:
                return "monolith"
            if is_be:
                return "backend"
            if is_fe:
                return "frontend"
        except Exception:
            pass

    # Fix 6b: DB-named services -> other (before any backend/frontend guess)
    name_lower = service_name.lower()
    if name_lower in DB_KEYWORDS:
        return "other"

    # Fallback to name heuristic only if no package.json found
    _BACKEND_NAMES = {
        "backend", "server", "api", "worker",
        "back-end", "back_end", "admin", "dashboard", "auth",
        "auth-service", "api-gateway", "service",
        "services", "express", "node", "bezkoder-api",
        "user-service", "todo-service", "bend", "nodejs", "graphql",
        "server-app", "node-app", "agentic_ai", "socket",
        "back", "implementation",

    }
    _FRONTEND_NAMES = {
        "frontend", "client", "ui", "web",
        "front-end", "front_end", "front", "react", "vue",
        "angular", "bezkoder-ui", "my-app", "webapp", "web-app",
        "www", "cafe-front", "taskly-frontend",
    }
    _BACKEND_SUBSTR_NAMES = _BACKEND_NAMES - {"worker", "auth", "graphql"}
    _FRONTEND_SUBSTR_NAMES = _FRONTEND_NAMES - {"front", "my-app", "www"}

    if name_lower in _BACKEND_NAMES:
        return "backend"
    if name_lower in _FRONTEND_NAMES:
        return "frontend"
    if any(k in name_lower for k in _BACKEND_SUBSTR_NAMES):
        return "backend"
    if any(k in name_lower for k in _FRONTEND_SUBSTR_NAMES):
        return "frontend"
    return "other"


def _find_all_services_by_deps(project_path: str) -> List[Dict[str, str]]:
    """
    Fix 1: Walk all subdirs (excluding SKIP_DIRS), find every package.json,
    and classify each service by deps against BACKEND_DEPS / FRONTEND_DEPS.
    Folders with no recognized backend/frontend deps are included as type='other' for downstream reclassification.
    Returns list of {name, abs_path, type} stubs.
    """
    services = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        if "package.json" not in files:
            continue

        pkg_path = os.path.join(root, "package.json")
        try:
            with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
                pkg = json.load(f)
        except Exception:
            continue

        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        dep_keys = set(deps.keys())
        ts_express_hint = (
            "@types/express" in dep_keys
            and bool(dep_keys & {"typescript", "ts-node", "tsx"})
            and not bool(dep_keys & FRONTEND_DEPS)
        )
        is_be = bool(dep_keys & BACKEND_DEPS) or ts_express_hint
        is_fe = bool(dep_keys & FRONTEND_DEPS)
        worker_match = bool(dep_keys & WORKER_DEPS)

        if worker_match:
            svc_type = "worker"
        elif is_be and is_fe:
            svc_type = "monolith"
        elif is_be:
            svc_type = "backend"
        elif is_fe:
            svc_type = "frontend"
        else:
            svc_type = "other"

        folder_name = os.path.basename(root) or os.path.basename(project_path)
        services.append({
            "name": folder_name,
            "abs_path": root,
            "type": svc_type,
        })
        print(f"📦 Dep-scan: found {svc_type} service '{folder_name}' at {root}")

    return services


ORCHESTRATOR_SIGNALS = {
    "Makefile", "makefile",
    ".github",       # directory, check with os.path.isdir
    "lerna.json",
    "nx.json",
    "turbo.json",
    "pnpm-workspace.yaml",
}


def _is_orchestrator_root(path: str) -> bool:
    try:
        entries = set(os.listdir(path))
    except OSError:
        return False
    file_signals = {
        e for e in entries
        if e in ORCHESTRATOR_SIGNALS and os.path.isfile(os.path.join(path, e))
    }
    dir_signals = {
        e for e in entries
        if e in {".github", "scripts", ".circleci"}
        and os.path.isdir(os.path.join(path, e))
    }
    return bool(file_signals or dir_signals)


def _suppress_root_if_children_found(
    services: List[Dict[str, str]],
    project_path: str,
) -> List[Dict[str, str]]:
    """
    Fix 5: Post-process service stubs with ordered rules.
    All path comparisons use norm_path().

    Rules applied in order (step 1 = empty-shell dropping runs separately post-population):
    2. Root monolith wins — if root is type=monolith, suppress all non-database children
    3. Root backend coexists — keep everything
    4. Phantom root — root is frontend/other/untyped + >=2 real non-root -> drop root
    """
    root_np = norm_path(project_path)

    def is_root(s):
        return norm_path(s.get("abs_path", "")) == root_np

    root_svcs = [s for s in services if is_root(s)]
    non_root = [s for s in services if not is_root(s)]

    if not root_svcs:
        return services

    root_svc = root_svcs[0]
    root_type = root_svc.get("type", "other")

    # Step 2: Root monolith -> suppress all non-database children
    if root_type == "monolith":
        db_children = [s for s in non_root if s.get("type") == "database"]
        return root_svcs + db_children

    # Step 3: Root backend -> keep everything (root + children are separate services)
    if root_type == "backend":
        return services

    # Step 4: Root is frontend/other/untyped + >=2 real non-root -> drop root
    if root_type in ("frontend", "other") or root_type is None:
        if _is_orchestrator_root(project_path):
            # Root has orchestrator signals — keep everything
            return services
        real_non_root = [
            s for s in non_root
            if s.get("type") not in ("database", "other")
        ]
        root_has_service_deps = False
        root_pkg = os.path.join(project_path, "package.json")
        if os.path.exists(root_pkg):
            try:
                with open(root_pkg, "r", encoding="utf-8", errors="ignore") as f:
                    pkg = json.load(f) or {}
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                root_has_service_deps = bool(
                    set(deps.keys()) & (BACKEND_DEPS | FRONTEND_DEPS | WORKER_DEPS)
                )
            except Exception:
                pass

        threshold = 2 if root_has_service_deps else 1
        if len(real_non_root) >= threshold:
            return non_root

    return services


def _drop_empty_shells(services: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Fix 5 Step 1: Remove services with no port AND no entry_point,
    unless they are database or other type. Called AFTER population.
    """
    survivors = []
    for s in services:
        stype = s.get("type", "other")
        has_signal = bool(s.get("port") and s.get("entry_point"))
        if stype == "database":
            survivors.append(s)
        elif stype == "other":
            if has_signal:
                survivors.append(s)
            else:
                print(f"Dropping empty shell: {s.get('name')} (no port+entry_point)")
        elif s.get("port") or s.get("entry_point"):
            survivors.append(s)
        else:
            print(f"Dropping empty shell: {s.get('name')}")
    return survivors


def _path_depth(path: str) -> int:
    np = norm_path(path)
    if np == ".":
        return 0
    return len([part for part in np.split("/") if part])


def _norm_cmp_path(path: str) -> str:
    """
    Canonical path key for comparisons/dedup across mixed sources.
    Keeps display paths unchanged while making matching robust on case-insensitive filesystems.
    """
    return norm_path(path).lower()


def _is_at_least_as_specific_path(candidate_path: str, existing_path: str) -> bool:
    """
    True when candidate_path is at least as specific as existing_path.
    Prevents replacing concrete paths (e.g. server/) with broad compose root (.).
    """
    cand = norm_path(candidate_path)
    existing = norm_path(existing_path)
    cand_cmp = _norm_cmp_path(candidate_path)
    existing_cmp = _norm_cmp_path(existing_path)

    if cand_cmp == existing_cmp:
        return True
    if existing_cmp == "." and cand_cmp != ".":
        return True
    if cand_cmp == "." and existing_cmp != ".":
        return False

    cand_parts = [p for p in cand_cmp.split("/") if p]
    existing_parts = [p for p in existing_cmp.split("/") if p]
    if (
        existing_parts
        and len(cand_parts) >= len(existing_parts)
        and cand_parts[-len(existing_parts):] == existing_parts
    ):
        return True

    return _path_depth(cand) > _path_depth(existing)



def _normalize_service_path(project_path: str, service_path: str) -> str:
    rel = os.path.relpath(service_path, project_path)
    rel = "." if rel in [".", ""] else rel.replace("\\", "/")
    if rel != "." and not rel.endswith("/"):
        rel += "/"
    return rel


def _compose_cmd_to_text(value: object) -> Optional[str]:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        if parts:
            return " ".join(parts)
    return None


def _extract_entry_from_command_text(command_text: Optional[str]) -> Optional[str]:
    if not command_text:
        return None
    try:
        parts = shlex.split(command_text, posix=True)
    except Exception:
        parts = str(command_text).split()

    for part in parts:
        token = str(part).strip().strip('"').strip("'").strip("`").rstrip(";,")
        if not token:
            continue
        low = token.lower()
        if low in {"node", "nodemon", "npx", "npm", "yarn", "pnpm", "bun", "python", "python3", "uvicorn", "gunicorn"}:
            continue
        if token.startswith("-"):
            continue
        if any(token.endswith(ext) for ext in (".js", ".ts", ".mjs", ".cjs", ".py")):
            return token.replace("\\", "/")
    return None


def _detect_package_manager(service_path: str) -> dict:
    """
    Detect which package manager a Node.js service uses and if lock file exists.
    Returns dict with:
      - manager: 'yarn', 'pnpm', or 'npm'
      - has_lockfile: True if lock file exists (needed for npm ci)
    """
    if os.path.exists(os.path.join(service_path, "yarn.lock")):
        return {"manager": "yarn", "has_lockfile": True}
    elif os.path.exists(os.path.join(service_path, "pnpm-lock.yaml")):
        return {"manager": "pnpm", "has_lockfile": True}
    elif os.path.exists(os.path.join(service_path, "package-lock.json")):
        return {"manager": "npm", "has_lockfile": True}
    else:
        return {"manager": "npm", "has_lockfile": False}


def _extract_workspace_patterns(pkg: Dict) -> List[str]:
    workspaces = pkg.get("workspaces")
    if isinstance(workspaces, list):
        return [str(w).strip() for w in workspaces if isinstance(w, str) and str(w).strip()]
    if isinstance(workspaces, dict):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            return [str(w).strip() for w in packages if isinstance(w, str) and str(w).strip()]
    return []


def _resolve_workspace_paths(project_path: str, patterns: List[str]) -> List[str]:
    resolved: List[str] = []
    seen = set()

    for pattern in patterns:
        if "*" in pattern:
            if pattern.endswith("/*"):
                prefix = pattern[:-2].strip("/\\")
                parent = os.path.join(project_path, prefix) if prefix else project_path
                if not os.path.isdir(parent):
                    continue
                try:
                    for name in os.listdir(parent):
                        candidate = os.path.join(parent, name)
                        if os.path.isdir(candidate):
                            norm = norm_path(candidate)
                            if norm not in seen:
                                seen.add(norm)
                                resolved.append(candidate)
                except (PermissionError, OSError):
                    continue
            continue

        candidate = os.path.join(project_path, pattern.strip("/\\"))
        if os.path.isdir(candidate):
            norm = norm_path(candidate)
            if norm not in seen:
                seen.add(norm)
                resolved.append(candidate)

    return resolved


def _build_node_stub_for_directory(service_path: str, project_path: str) -> Optional[Dict[str, str]]:
    pkg_path = os.path.join(service_path, "package.json")
    if not os.path.exists(pkg_path):
        return None

    try:
        with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
            pkg = json.load(f)
    except Exception:
        return None

    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    dep_keys = set(deps.keys())
    ts_express_hint = (
        "@types/express" in dep_keys
        and bool(dep_keys & {"typescript", "ts-node", "tsx"})
        and not bool(dep_keys & FRONTEND_DEPS)
    )
    is_be = bool(dep_keys & BACKEND_DEPS) or ts_express_hint
    is_fe = bool(dep_keys & FRONTEND_DEPS)
    worker_match = bool(dep_keys & WORKER_DEPS)

    if worker_match:
        svc_type = "worker"
    elif is_be and is_fe:
        svc_type = "monolith"
    elif is_be:
        svc_type = "backend"
    elif is_fe:
        svc_type = "frontend"
    else:
        svc_type = "other"

    folder_name = os.path.basename(service_path) or os.path.basename(project_path)
    return {
        "name": folder_name,
        "abs_path": service_path,
        "type": svc_type,
    }


def _build_python_stub_for_directory(service_path: str, project_path: str) -> Optional[Dict[str, str]]:
    try:
        files = set(os.listdir(service_path))
    except (PermissionError, OSError):
        return None

    framework = None
    pkg_manager = "pip"

    if "manage.py" in files:
        framework = "Django"

    if not framework and "requirements.txt" in files:
        try:
            with open(os.path.join(service_path, "requirements.txt"), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
            for dep in PYTHON_BACKEND_DEPS:
                if dep in content:
                    framework = dep.capitalize()
                    if dep == "fastapi":
                        framework = "FastAPI"
                    break
        except Exception:
            pass

    if not framework and "pyproject.toml" in files:
        pkg_manager = "poetry"
        try:
            with open(os.path.join(service_path, "pyproject.toml"), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
            for dep in PYTHON_BACKEND_DEPS:
                if dep in content:
                    framework = dep.capitalize()
                    if dep == "fastapi":
                        framework = "FastAPI"
                    break
        except Exception:
            pass

    if not framework and "Pipfile" in files:
        pkg_manager = "pipenv"
        try:
            with open(os.path.join(service_path, "Pipfile"), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
            for dep in PYTHON_BACKEND_DEPS:
                if dep in content:
                    framework = dep.capitalize()
                    if dep == "fastapi":
                        framework = "FastAPI"
                    break
        except Exception:
            pass

    if not framework:
        has_python_manifest = any(
            manifest in files for manifest in ("manage.py", "requirements.txt", "pyproject.toml", "Pipfile")
        )
        if not has_python_manifest:
            return None
        framework = "Unknown"

    entry_point = None
    if framework == "Django":
        entry_point = "manage.py"
    else:
        for candidate in ["main.py", "app.py", "run.py", "server.py"]:
            if candidate in files:
                entry_point = candidate
                break

    port = None
    port_source = "default"

    for env_name in [".env", ".env.local", ".env.production"]:
        env_path = os.path.join(service_path, env_name)
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                    PORT_KEYS = ("PORT=", "BACKEND_PORT=", "SERVER_PORT=", "API_PORT=")
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        for key in PORT_KEYS:
                            if line.upper().startswith(key):
                                try:
                                    port = int(line.split("=", 1)[1].strip())
                                    port_source = "env"
                                except ValueError:
                                    pass
            except Exception:
                pass
            break

    if not port and entry_point and os.path.exists(os.path.join(service_path, entry_point)):
        try:
            with open(os.path.join(service_path, entry_point), "r", encoding="utf-8", errors="ignore") as f:
                src = f.read()
            m = re.search(r'(?:uvicorn\.run|app\.run)\s*\(.*?port\s*=\s*(\d+)', src)
            if m:
                port = int(m.group(1))
                port_source = "source"
        except Exception:
            pass

    if not port:
        if framework in ("Django", "FastAPI", "Starlette"):
            port = 8000
        elif framework == "Flask":
            port = 5000
        else:
            port = 8000

    folder_name = os.path.basename(service_path) or os.path.basename(project_path)
    return {
        "name": folder_name,
        "abs_path": service_path,
        "type": "backend",
        "language": "Python",
        "framework": framework,
        "package_manager": pkg_manager,
        "dockerfile_strategy": "python_backend",
        "entry_point": entry_point,
        "port": port,
        "port_source": port_source,
    }


def _build_workspace_stubs(project_path: str) -> Optional[List[Dict[str, str]]]:
    pkg_path = os.path.join(project_path, "package.json")
    if not os.path.exists(pkg_path):
        return None

    try:
        with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
            pkg = json.load(f)
    except Exception:
        return None

    patterns = _extract_workspace_patterns(pkg)
    if not patterns:
        return None

    workspace_paths = _resolve_workspace_paths(project_path, patterns)
    if not workspace_paths:
        return None

    node_stubs: List[Dict[str, str]] = []
    python_stubs: List[Dict[str, str]] = []
    root_norm = norm_path(project_path)

    for workspace_path in workspace_paths:
        if norm_path(workspace_path) == root_norm:
            continue

        node_stub = _build_node_stub_for_directory(workspace_path, project_path)
        if node_stub:
            node_stubs.append(node_stub)

        python_stub = _build_python_stub_for_directory(workspace_path, project_path)
        if python_stub:
            python_stubs.append(python_stub)

    return _merge_node_python_stubs(node_stubs, python_stubs)


def _find_python_services(project_path: str) -> List[Dict[str, str]]:
    """
    Fix 7: Walk subdirs (excluding PYTHON_SKIP_DIRS), detect Python backends via
    manage.py or requirements.txt/pyproject.toml/Pipfile containing PYTHON_BACKEND_DEPS.
    Returns stubs with: name, abs_path, type, language, framework, package_manager,
                        dockerfile_strategy, entry_point, port, port_source.
    """
    services = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in PYTHON_SKIP_DIRS]

        framework = None
        pkg_manager = "pip"

        # Django detection via manage.py
        if "manage.py" in files:
            framework = "Django"

        # Check requirements.txt
        if not framework and "requirements.txt" in files:
            try:
                with open(os.path.join(root, "requirements.txt"), "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                for dep in PYTHON_BACKEND_DEPS:
                    if dep in content:
                        framework = dep.capitalize()
                        if dep == "fastapi":
                            framework = "FastAPI"
                        break
            except Exception:
                pass

        # Check pyproject.toml
        if not framework and "pyproject.toml" in files:
            pkg_manager = "poetry"
            try:
                with open(os.path.join(root, "pyproject.toml"), "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                for dep in PYTHON_BACKEND_DEPS:
                    if dep in content:
                        framework = dep.capitalize()
                        if dep == "fastapi":
                            framework = "FastAPI"
                        break
            except Exception:
                pass

        # Check Pipfile
        if not framework and "Pipfile" in files:
            pkg_manager = "pipenv"
            try:
                with open(os.path.join(root, "Pipfile"), "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                for dep in PYTHON_BACKEND_DEPS:
                    if dep in content:
                        framework = dep.capitalize()
                        if dep == "fastapi":
                            framework = "FastAPI"
                        break
            except Exception:
                pass

        if not framework:
            has_python_manifest = any(
                manifest in files for manifest in ("manage.py", "requirements.txt", "pyproject.toml", "Pipfile")
            )
            if not has_python_manifest:
                continue
            framework = "Unknown"

        # Detect entry_point
        entry_point = None
        if framework == "Django":
            entry_point = "manage.py"
        else:
            for candidate in ["main.py", "app.py", "run.py", "server.py"]:
                if candidate in files:
                    entry_point = candidate
                    break

        # Detect port
        port = None
        port_source = "default"

        # Check .env for PORT
        for env_name in [".env", ".env.local", ".env.production"]:
            env_path = os.path.join(root, env_name)
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                        PORT_KEYS = ("PORT=", "BACKEND_PORT=", "SERVER_PORT=", "API_PORT=")
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            for key in PORT_KEYS:
                                if line.upper().startswith(key):
                                    try:
                                        port = int(line.split("=", 1)[1].strip())
                                        port_source = "env"
                                    except ValueError:
                                        pass
                except Exception:
                    pass
                break

        # Scan source files for port hints
        if not port and entry_point and os.path.exists(os.path.join(root, entry_point)):
            try:
                with open(os.path.join(root, entry_point), "r", encoding="utf-8", errors="ignore") as f:
                    src = f.read()
                # uvicorn.run(..., port=XXXX)
                m = re.search(r'(?:uvicorn\.run|app\.run)\s*\(.*?port\s*=\s*(\d+)', src)
                if m:
                    port = int(m.group(1))
                    port_source = "source"
            except Exception:
                pass

        # Framework defaults
        if not port:
            if framework in ("Django", "FastAPI", "Starlette"):
                port = 8000
            elif framework == "Flask":
                port = 5000
            else:
                port = 8000

        folder_name = os.path.basename(root) or os.path.basename(project_path)
        services.append({
            "name": folder_name,
            "abs_path": root,
            "type": "backend",
            "language": "Python",
            "framework": framework,
            "package_manager": pkg_manager,
            "dockerfile_strategy": "python_backend",
            "entry_point": entry_point,
            "port": port,
            "port_source": port_source,
        })
        print(f"🐍 Python-scan: found {framework} backend '{folder_name}' at {root}")

    return services


def _merge_node_python_stubs(
    node_stubs: List[Dict[str, str]],
    python_stubs: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    Merge Node and Python stubs, deduplicating by abs_path.
    If same path appears in both, prefer Python if it has a framework match,
    otherwise prefer Node.
    """
    by_path = {}
    # Node stubs first
    for s in node_stubs:
        np = norm_path(s.get("abs_path", ""))
        by_path[np] = s
    # Python stubs overlay if they have a framework
    for s in python_stubs:
        np = norm_path(s.get("abs_path", ""))
        if np in by_path:
            # Prefer Python if it detected a real framework
            if s.get("framework"):
                by_path[np] = s
        else:
            by_path[np] = s
    return list(by_path.values())


def infer_services(
    project_path: str,
    language: str,
    framework: str,
    metadata: Dict,
    db_result: Optional[Dict] = None,
) -> List[Dict[str, str]]:
    """
    Return a list of services, each with:
      - name: str
      - path: str (build context relative to project root)
      - type: one of {"backend", "frontend", "monolith", "worker", "other"}
      - port, port_source, entry_point, build_output, env_file, package_manager
    
    Fix 1: Uses dep-based scanning instead of folder-name matching.
    Fix 2: Monolith services get dockerfile_strategy.
    Fix 3/5: Root phantom service suppressed when child services exist.
    Fix 7: Python backends detected alongside Node services.
    """
    static_only = metadata.get("static_only", False)
    workspace_mode = False

    workspace_stubs = _build_workspace_stubs(project_path)
    if workspace_stubs:
        workspace_mode = True
        raw_stubs = workspace_stubs
    else:
        # -- Fix 1: Dep-based service discovery (Node.js) --
        node_stubs = _find_all_services_by_deps(project_path)

        # -- Fix 7: Python backend discovery --
        python_stubs = _find_python_services(project_path)

        # -- Merge + deduplicate (Python preferred if it has framework) --
        raw_stubs = _merge_node_python_stubs(node_stubs, python_stubs)
    
    # Reclassify dep-unknown NON-ROOT stubs before suppress so the threshold
    # count is accurate. Root stubs are intentionally NOT reclassified here:
    # if root is "other" when suppress runs, Step 4 correctly drops it when
    # >=2 real children exist. Reclassifying root to "backend" would trigger
    # Step 3 ("root backend → keep everything") and produce a phantom root.
    root_np = norm_path(project_path)
    for stub in raw_stubs:
        if stub.get("type") != "other":
            continue
        svc_abs_path = stub.get("abs_path", "")
        if not svc_abs_path:
            continue
        if norm_path(svc_abs_path) == root_np:
            continue  # leave root stub unclassified until after suppress
        try:
            rel_stub_path = os.path.relpath(svc_abs_path, project_path).replace("\\", "/")
            rel_stub_path = "." if rel_stub_path in ("", ".") else rel_stub_path
        except Exception:
            rel_stub_path = "."
        inferred_type = _infer_service_type(rel_stub_path, stub.get("name", ""), project_path)
        if inferred_type in ("backend", "frontend", "monolith", "worker"):
            stub["type"] = inferred_type

    # -- Fix 3/5: Suppress root phantom if children found --
    raw_stubs = _suppress_root_if_children_found(raw_stubs, project_path)

    # Reclassify any remaining "other" stubs (including root if it survived suppress)
    for stub in raw_stubs:
        if stub.get("type") != "other":
            continue
        svc_abs_path = stub.get("abs_path", "")
        if not svc_abs_path:
            continue
        try:
            rel_stub_path = os.path.relpath(svc_abs_path, project_path).replace("\\", "/")
            rel_stub_path = "." if rel_stub_path in ("", ".") else rel_stub_path
        except Exception:
            rel_stub_path = "."
        inferred_type = _infer_service_type(rel_stub_path, stub.get("name", ""), project_path)
        if inferred_type in ("backend", "frontend", "monolith", "worker"):
            stub["type"] = inferred_type

    # -- Populate per-service fields --
    services: List[Dict[str, str]] = []
    has_monolith = False

    for stub in raw_stubs:
        svc_abs_path = stub["abs_path"]
        svc_rel_path = _normalize_service_path(project_path, svc_abs_path)
        svc_type = stub["type"]
        svc_name = stub["name"]

        # Check for .env file
        env_file = None
        for env_name in [".env", ".env.local", ".env.production"]:
            env_check = os.path.join(svc_abs_path, env_name)
            if os.path.exists(env_check):
                if svc_rel_path == ".":
                    env_file = f"./{env_name}"
                else:
                    env_file = f"./{svc_rel_path}{env_name}"
                print(f"📄 Found env file for {svc_name}: {env_file}")
                break

        if svc_type in ("backend", "monolith"):
            # -- Python stubs already have fields populated by _find_python_services --
            if stub.get("language") == "Python":
                py_cmds = extract_python_commands(svc_abs_path)
                svc_dict = {
                    "name": svc_name,
                    "path": svc_rel_path,
                    "type": svc_type,
                    "language": "Python",
                    "framework": stub.get("framework"),
                    "port": stub.get("port", 8000),
                    "port_source": stub.get("port_source", "default"),
                    "entry_point": stub.get("entry_point") or py_cmds.get("entry_point"),
                    "start_command": py_cmds.get("start_command"),
                    "env_file": env_file,
                    "package_manager": stub.get("package_manager", "pip"),
                    "dockerfile_strategy": "python_backend",
                }
                services.append(svc_dict)
                print(f"🐍 Python service '{svc_name}': framework={stub.get('framework')}, port={stub.get('port')}")
                continue

            # -- Node.js backend/monolith --
            if os.path.exists(os.path.join(svc_abs_path, "package.json")):
                svc_language = "JavaScript"
                if language in ("JavaScript", "TypeScript", "javascript", "typescript"):
                    svc_framework = framework
                else:
                    svc_framework = "Unknown"
            elif stub.get("language") == "Python":
                svc_language = "Python"
                svc_framework = stub.get("framework", "Unknown")
            else:
                svc_language = language
                svc_framework = framework

            # Extract port from service directory
            port_info = extract_port_from_project(svc_abs_path, svc_framework, svc_language)
            port = port_info.get("port", 3000)
            port_source = port_info.get("source", "default")
            if port_source == "default":
                hint_port = _scan_js_for_port_hint(svc_abs_path)
                if hint_port:
                    port = hint_port
                    port_source = "source"
            # Extract start command from service's package.json
            if svc_language == "Python":
                cmds = extract_python_commands(svc_abs_path)
            else:
                cmds = extract_nodejs_commands(svc_abs_path)
            entry_point = cmds.get("entry_point")  # None if genuinely not found

            # Only apply a last-resort default if the probe also found nothing
            # (extract_nodejs_commands already checked common files — trust its result)
            if not entry_point and svc_language != "Python":
                # Final fallback: check a few key names that extract_nodejs_commands
                # might have missed if pkg_dir differed from svc_abs_path
                for candidate in (
                    "server.js", "index.js", "app.js", "main.js",
                    "src/server.js", "src/index.js", "src/app.js", "src/main.js",
                    "server/app.js", "server/index.js", "server/server.js",
                    "js/index.js", "js/app.js",
                    "bin/www", "bin/www.js",
                    "src/server.ts", "src/index.ts", "src/app.ts",
                    "dist/server.js", "dist/index.js",
                ):
                    if os.path.exists(os.path.join(svc_abs_path, candidate)):
                        entry_point = candidate
                        break
                # Do NOT hardcode "index.js" if no file was found — leave as None
                # so the generator knows entry_point is unknown rather than guessing wrong

            start_command = cmds.get("start_command")
            if not start_command and entry_point and svc_language != "Python":
                start_command = f"node {entry_point}"
            print(f"📦 {svc_type.title()} service '{svc_name}': entry_point={entry_point}, start_command={start_command}")

            svc_dict = {
                "name": svc_name,
                "path": svc_rel_path,
                "type": svc_type,
                "language": svc_language,
                "framework": svc_framework,
                "port": port,
                "port_source": port_source,
                "entry_point": entry_point,
                "start_command": start_command,
                "env_file": env_file,
                "package_manager": _detect_package_manager(svc_abs_path),
            }

            # -- Fix 2: Monolith gets extra fields --
            if svc_type == "monolith":
                has_monolith = True
                svc_dict["dockerfile_strategy"] = "single_stage_with_build"
                # Also get build_output for the React build step
                build_output = cmds.get("build_output", "build")
                svc_dict["build_output"] = build_output

            services.append(svc_dict)

        elif svc_type == "frontend":
            # Extract build_output for this frontend service
            cmds = extract_nodejs_commands(svc_abs_path)
            build_output = cmds.get("build_output", "dist")

            # Extract frontend port
            fe_port_info = extract_frontend_port(svc_abs_path)
            fe_port = fe_port_info.get("port") or 5173
            print(f"📦 Frontend service '{svc_name}': build_output={build_output}, port={fe_port}")

            services.append({
                "name": svc_name,
                "path": svc_rel_path,
                "type": "frontend",
                "build_output": build_output,
                "port": fe_port,
                "dev_port": fe_port,
                "port_source": fe_port_info.get("source", "default"),
                "entry_point": cmds.get("entry_point"),
                "start_command": cmds.get("start_command"),
                "env_file": env_file,
                "package_manager": _detect_package_manager(svc_abs_path),
            })

        elif svc_type == "worker":
            if stub.get("language") == "Python":
                svc_language = "Python"
                svc_framework = stub.get("framework", "Unknown")
            elif os.path.exists(os.path.join(svc_abs_path, "package.json")):
                svc_language = "JavaScript"
                if language in ("JavaScript", "TypeScript", "javascript", "typescript"):
                    svc_framework = framework
                else:
                    svc_framework = "Unknown"
            else:
                svc_language = language
                svc_framework = framework
            if svc_language == "Python":
                cmds = extract_python_commands(svc_abs_path)
            else:
                cmds = extract_nodejs_commands(svc_abs_path)
            port_info = extract_port_from_project(svc_abs_path, svc_framework, svc_language)
            services.append({
                "name": svc_name,
                "path": svc_rel_path,
                "type": "worker",
                "language": svc_language,
                "framework": svc_framework,
                "port": port_info.get("port"),
                "port_source": port_info.get("source", "default"),
                "entry_point": cmds.get("entry_point"),
                "start_command": cmds.get("start_command"),
                "env_file": env_file,
                "package_manager": _detect_package_manager(svc_abs_path),
            })

    # -- Fix 5 Step 1: Drop empty shells post-population --
    services = _drop_empty_shells(services)

    # -- Fallback: if dep-scan found nothing, use legacy single-service logic --
    if not services and not workspace_mode:
        root_env_file = None
        for env_name in [".env", ".env.local", ".env.production"]:
            env_path = os.path.join(project_path, env_name)
            if os.path.exists(env_path):
                root_env_file = f"./{env_name}"
                print(f"📄 Found root env file: {root_env_file}")
                break

        # Phantom fallback guard: only emit a service if we have some positive signal.
        manifest_files = [
            "package.json", "requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock",
            "composer.json", "Cargo.toml", "pom.xml", "go.mod", "Gemfile", "setup.py",
        ]
        has_manifest = any(os.path.exists(os.path.join(project_path, f)) for f in manifest_files)

        node_cmds = extract_nodejs_commands(project_path)
        python_cmds = extract_python_commands(project_path)
        entry_point = node_cmds.get("entry_point") or python_cmds.get("entry_point")

        port_info = extract_port_from_project(project_path, framework, language)
        port = port_info.get("port", 3000)
        port_source = port_info.get("source", "default")
        if port_source == "default":
            hint_port = _scan_js_for_port_hint(project_path)
            if hint_port:
                port = hint_port
                port_source = "source"

        explicit_port = port_source in ("env", "source")

        if not (has_manifest or entry_point or explicit_port):
            return []

        if static_only:
            single_cmds = extract_nodejs_commands(project_path)
            single_build_output = single_cmds.get("build_output", "dist")
            services.append({
                "name": "frontend",
                "path": ".",
                "type": "frontend",
                "port": 80,
                "port_source": "default",
                "build_output": single_build_output,
                "start_command": None,
                "env_file": root_env_file,
            })
        else:
            svc_name = "frontend" if framework in ["React", "Next.js"] else "app"
            svc_type = "frontend" if framework in ["React", "Next.js"] else "backend"
            if svc_type == "frontend":
                single_cmds = extract_nodejs_commands(project_path)
                fe_port_info = extract_frontend_port(project_path)
                services.append({
                    "name": svc_name,
                    "path": ".",
                    "type": svc_type,
                    "port": fe_port_info.get("port") or 5173,
                    "dev_port": fe_port_info.get("port") or 5173,
                    "port_source": fe_port_info.get("source", "default"),
                    "build_output": single_cmds.get("build_output", "dist"),
                    "entry_point": single_cmds.get("entry_point"),
                    "start_command": single_cmds.get("start_command"),
                    "env_file": root_env_file,
                })
            else:
                fallback_cmds = extract_nodejs_commands(project_path)
                fallback_entry = fallback_cmds.get("entry_point")
                fallback_start = fallback_cmds.get("start_command")
                port_info = extract_port_from_project(project_path, framework, language)
                port = port_info.get("port", 3000)
                port_source = port_info.get("source", "default")
                if port_source == "default":
                    hint_port = _scan_js_for_port_hint(project_path)
                    if hint_port:
                        port = hint_port
                        port_source = "source"
                services.append({
                    "name": svc_name,
                    "path": ".",
                    "type": svc_type,
                    "port": port,
                    "port_source": port_source,
                    "entry_point": fallback_entry,
                    "start_command": fallback_start,
                    "env_file": root_env_file,
                })

    # -- Fix 2: Set architecture metadata --
    if has_monolith:
        metadata["architecture"] = "monolith"
    else:
        metadata.setdefault("architecture", "multi-service")

    # -- Compose hints (optional refinement) --
    compose_path = None
    for fname in ("docker-compose.yml", "docker-compose.yaml"):
        candidate = os.path.join(project_path, fname)
        if os.path.exists(candidate):
            compose_path = candidate
            break

    if compose_path and yaml is not None:
        compose_svc_name = "<unknown>"
        try:
            with open(compose_path, "r", encoding="utf-8", errors="ignore") as f:
                compose_data = yaml.safe_load(f) or {}
            compose_services = compose_data.get("services") or {}

            for svc_name, svc_def in compose_services.items():
                compose_svc_name = svc_name
                build_ctx = None
                build_field = svc_def.get("build")
                if isinstance(build_field, str):
                    build_ctx = build_field
                elif isinstance(build_field, dict):
                    build_ctx = build_field.get("context") or "."

                if not build_ctx:
                    continue

                abs_ctx = os.path.abspath(os.path.join(project_path, build_ctx))
                if not os.path.isdir(abs_ctx):
                    continue

                rel_ctx = _normalize_service_path(project_path, abs_ctx)
                svc_type = _infer_service_type(rel_ctx, svc_name, project_path)
                compose_command = _compose_cmd_to_text(svc_def.get("command"))
                compose_entrypoint = _compose_cmd_to_text(svc_def.get("entrypoint"))
                compose_runtime_cmd = " ".join(
                    part for part in [compose_entrypoint, compose_command] if part
                ) or None
                compose_entry = _extract_entry_from_command_text(compose_runtime_cmd)

                # Try to match by path
                matched = False
                for svc in services:
                    if _norm_cmp_path(svc.get("path", "")) == _norm_cmp_path(rel_ctx):
                        svc["name"] = svc_name  # align name to compose
                        svc.setdefault("type", svc_type)
                        if compose_runtime_cmd and not svc.get("start_command"):
                            svc["start_command"] = compose_runtime_cmd
                        if compose_entry and not svc.get("entry_point"):
                            svc["entry_point"] = compose_entry
                        matched = True
                        break

                if matched:
                    continue

                # Match by name
                for svc in services:
                    if svc.get("name") == svc_name:
                        existing_path = svc.get("path", ".")
                        if _is_at_least_as_specific_path(rel_ctx, existing_path):
                            svc["path"] = rel_ctx
                        svc.setdefault("type", svc_type)
                        if compose_runtime_cmd and not svc.get("start_command"):
                            svc["start_command"] = compose_runtime_cmd
                        if compose_entry and not svc.get("entry_point"):
                            svc["entry_point"] = compose_entry
                        matched = True
                        break

                if not matched:
                    # Fix 4: only add compose-discovered service if it looks like a real service
                    abs_ctx_for_check = os.path.abspath(os.path.join(project_path, build_ctx))
                    if not _is_service_candidate(abs_ctx_for_check, svc_name):
                        continue
                    services.append({
                        "name": svc_name,
                        "path": rel_ctx,
                        "type": svc_type,
                        "start_command": compose_runtime_cmd,
                        "entry_point": compose_entry,
                    })
        except Exception as e:
            print(f"Compose hints error for {compose_svc_name}: {e}")

    deduped_by_path_type: Dict[tuple, Dict[str, str]] = {}
    for svc in services:
        key = (_norm_cmp_path(svc.get("path", ".")), str(svc.get("type", "other")))
        if key not in deduped_by_path_type:
            deduped_by_path_type[key] = dict(svc)
            continue
        deduped_by_path_type[key].update({k: v for k, v in svc.items() if v is not None})

    services = list(deduped_by_path_type.values())

    # Root monolith can coexist with compose hints that add child build contexts.
    # If a root monolith exists, suppress non-database subdirectory services to avoid duplication.
    if any(s.get("path") == "." and s.get("type") == "monolith" for s in services):
        services = [
            s for s in services
            if s.get("path") == "." or s.get("type") == "database"
        ]

    # -- Database service detection (smart cloud vs local) --
    backend_path = None
    for svc in services:
        if svc.get("type") in ("backend", "monolith"):
            backend_path = os.path.join(project_path, svc.get("path", "."))
            break

    # If no backend/monolith service survived population, use an "other"-typed
    # raw stub as fallback DB probe target.
    if not backend_path:
        fallback_candidates: List[tuple[int, str]] = []
        for stub in raw_stubs:
            if stub.get("type") != "other":
                continue
            candidate = stub.get("abs_path")
            if not (candidate and os.path.isdir(candidate)):
                continue
            score = 0
            try:
                files = set(os.listdir(candidate))
            except (PermissionError, OSError):
                files = set()
            if "package.json" in files:
                score += 3
            if any(f in files for f in ("requirements.txt", "pyproject.toml", "Pipfile", "manage.py")):
                score += 2
            name_lower = str(stub.get("name", "")).lower()
            if any(tok in name_lower for tok in ("backend", "server", "api", "worker")):
                score += 1
            try:
                rel_candidate = os.path.relpath(candidate, project_path).replace("\\", "/")
            except Exception:
                rel_candidate = candidate
            depth = _path_depth(rel_candidate)
            fallback_candidates.append((score * 10 + depth, candidate))

        if fallback_candidates:
            fallback_candidates.sort(key=lambda item: item[0], reverse=True)
            backend_path = fallback_candidates[0][1]

    db_info: Dict[str, any] = {}
    authoritative_db = None
    if isinstance(db_result, dict):
        authoritative_db = db_result.get("primary")
    if not authoritative_db:
        authoritative_db = metadata.get("database")
    if authoritative_db == "Unknown":
        authoritative_db = None

    if backend_path and authoritative_db:
        db_info = extract_database_info(backend_path, authoritative_db)

        # Keep DB type aligned with detector-level scoring when provided.
        if isinstance(db_result, dict):
            scored_primary = db_result.get("primary")
            if scored_primary and scored_primary != "Unknown":
                normalized = {
                    "MongoDB": "mongodb",
                    "PostgreSQL": "postgresql",
                    "MySQL": "mysql",
                    "Redis": "redis",
                    "SQLite": "sqlite",
                }.get(scored_primary, str(scored_primary).lower())
                db_info["db_type"] = normalized
                db_defaults = {
                    "mongodb": {"port": 27017, "image": "mongo:latest"},
                    "postgresql": {"port": 5432, "image": "postgres:15-alpine"},
                    "mysql": {"port": 3306, "image": "mysql:8"},
                    "redis": {"port": 6379, "image": "redis:alpine"},
                }
                if normalized in db_defaults:
                    db_info["default_port"] = db_defaults[normalized]["port"]
                    db_info["docker_image"] = db_defaults[normalized]["image"]

    if backend_path and db_info.get("db_type"):
        metadata["database_is_cloud"] = db_info["is_cloud"]
        metadata["database_env_var"] = db_info.get("env_var_name")

        if db_info.get("needs_container"):
            db_service_name = {
                "mongodb": "mongo",
                "postgresql": "postgres",
                "mysql": "mysql",
                "redis": "redis",
            }.get(db_info["db_type"], "database")

            if not any(svc.get("type") == "database" for svc in services):
                services.append({
                    "name": db_service_name,
                    "path": ".",
                    "type": "database",
                    "port": db_info.get("default_port"),
                    "docker_image": db_info.get("docker_image"),
                    "is_cloud": False,
                })
                print(f"🏠 Adding LOCAL {db_service_name} container to services")
        else:
            print(f"☁️ Cloud database detected ({db_info['db_type']}), no container needed")
            print(f"   Backend should use env var: {db_info.get('env_var_name')}")

    # Suppress phantom root service when real subdirectory services exist
    # BUT only if the root folder has no dependency file of its own
    _DEP_FILES = {
        "package.json", "requirements.txt", "pyproject.toml",
        "pom.xml", "go.mod", "manage.py", "Gemfile", "Cargo.toml",
    }
    _subdir_services = [
        s for s in services
        if s.get("path", ".").strip("/\\").replace("\\", "/") not in ("", ".")
    ]
    if _subdir_services:
        _root_services = [
            s for s in services
            if s.get("path", ".").strip("/\\").replace("\\", "/") in ("", ".")
        ]
        for rs in _root_services:
            try:
                root_files = set(os.listdir(project_path))
            except (PermissionError, OSError):
                root_files = set()
            if not (root_files & _DEP_FILES):
                services = _subdir_services + [s for s in services if s.get("type") == "database"]
                break

    return services
