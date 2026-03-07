"""
detector.py — Orchestrator + backwards-compatible re-export hub.

All domain logic has been extracted into focused modules:
  - detection_constants   : shared constants & tiny helpers
  - detection_language    : language/framework detection, dependency parsing
  - detection_ports       : port detection (package.json, source scan, Docker)
  - detection_database    : database detection
  - detection_services    : service inference

This file keeps:
  1. Re-exports so that `from app.utils.detector import X` keeps working
  2. detect_framework()   — the main orchestrator
  3. Docker / env helpers tightly coupled to the orchestrator
  4. find_project_root()
"""

import os
import json
from typing import Dict, List, Optional

# ── Re-exports from detection_constants ────────────────────────────────
from .detection_constants import (                          # noqa: F401
    LANGUAGE_INDICATORS,
    FRAMEWORK_INDICATORS,
    FRAMEWORK_LANGUAGES,
    DB_INDICATORS,
    DB_ENV_KEYWORDS,
    BACKEND_DEPS,
    FRONTEND_DEPS,
    SKIP_DIRS,
    PYTHON_BACKEND_DEPS,
    DB_KEYWORDS,
    PYTHON_SKIP_DIRS,
    _languages_compatible,
    norm_path,
    _normalize_dep_name,
)

# ── Re-exports from detection_language ─────────────────────────────────
from .detection_language import (                           # noqa: F401
    parse_dependencies_file,
    get_runtime_info,
    heuristic_language_detection,
    heuristic_framework_detection,
)

# ── Re-exports from detection_ports ────────────────────────────────────
from .detection_ports import (                              # noqa: F401
    _detect_fullstack_structure,
    _scan_js_for_port_hint,
    _detect_port_from_package_json,
    _scan_code_for_ports,
    _parse_docker_compose_ports,
    _parse_dockerfile_expose_ports,
    _classify_docker_service,
    detect_ports_for_project,
)

# ── Re-exports from detection_database ─────────────────────────────────
from .detection_database import (                           # noqa: F401
    _infer_database_port,
    detect_databases,
    detect_db_and_ports,
)

# ── Re-exports from detection_services ─────────────────────────────────
from .detection_services import (                           # noqa: F401
    _INFRA_DIRS,
    _SERVICE_INDICATOR_FILES,
    _is_service_candidate,
    _infer_service_type,
    _find_all_services_by_deps,
    _suppress_root_if_children_found,
    _drop_empty_shells,
    _normalize_service_path,
    _detect_package_manager,
    _find_python_services,
    _merge_node_python_stubs,
    infer_services,
)

# ── Direct imports used by functions that remain in this file ──────────
from .ml_analyzer import get_ml_analyzer
from .command_extractor import (
    extract_nodejs_commands,
    extract_python_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info,
)


# =====================================================================
# Functions that remain in detector.py
# =====================================================================

def detect_docker_files(project_path: str) -> Dict:
    """Detect Docker files"""
    result = {
        "dockerfile": False,
        "docker_compose": False,
        "detected_files": []
    }
    
    docker_files = ['Dockerfile', 'dockerfile']
    compose_files = ['docker-compose.yml', 'docker-compose.yaml']
    
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', 'venv']]
            
            for file in files:
                if file in docker_files:
                    result["dockerfile"] = True
                    result["detected_files"].append(file)
                
                if file in compose_files:
                    result["docker_compose"] = True
                    result["detected_files"].append(file)
    
    except Exception as e:
        print(f"Docker detection error: {e}")
    
    return result


def detect_env_variables(project_path: str) -> List[str]:
    """Detect environment variables from .env files (keys only)"""
    env_vars = []
    env_files = ['.env', '.env.example', '.env.sample', '.env.local']
    
    for env_file in env_files:
        env_path = os.path.join(project_path, env_file)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key = line.split('=')[0].strip()
                            if key and key not in env_vars:
                                env_vars.append(key)
            except Exception as e:
                print(f"Error reading {env_file}: {e}")
    
    return env_vars


def _read_env_key_values(project_path: str) -> Dict[str, str]:
    """Internal helper: read key=value pairs from typical .env files (for DB/port hints)."""
    env_values: Dict[str, str] = {}
    env_files = [
        '.env', '.env.local', '.env.development', '.env.production',
        '.env.test', '.env.example'
    ]
    for env_file in env_files:
        env_path = os.path.join(project_path, env_file)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_values[key.strip()] = value.strip()
            except Exception as e:
                print(f"Error reading {env_file} for values: {e}")
    return env_values


def find_project_root(extracted_path: str, max_depth: int = 3) -> str:
    """Find actual project root recursively"""
    try:
        framework_files = [
            'package.json', 'requirements.txt', 'pyproject.toml', 'Pipfile', 'poetry.lock',
            'pom.xml', 'build.gradle', 'composer.json', 'go.mod', 'Gemfile', 'Cargo.toml',
            'setup.py'
        ]

        excluded_dirs = {
            'infra', 'node_modules', '.git', '__pycache__', '.terraform',
            'venv', '.venv', 'dist', 'build', '.next'
        }

        def has_manifest(path: str) -> bool:
            try:
                return any(os.path.exists(os.path.join(path, f)) for f in framework_files)
            except Exception:
                return False

        def search_unique(current_path: str, depth: int = 0) -> Optional[str]:
            """
            Search down to max_depth for manifest files. If exactly one unique
            manifest-containing directory exists in this subtree, return it.
            If multiple candidates exist, return None (ambiguous).
            """
            if depth > max_depth:
                return None

            if has_manifest(current_path):
                return current_path

            try:
                entries = os.listdir(current_path)
            except Exception as e:
                print(f"Error scanning {current_path}: {e}")
                return None

            found: List[str] = []
            for name in entries:
                abs_path = os.path.join(current_path, name)
                if not os.path.isdir(abs_path):
                    continue
                if name in excluded_dirs:
                    continue
                child = search_unique(abs_path, depth + 1)
                if child:
                    found.append(child)

            # Deduplicate candidates
            uniq: List[str] = []
            seen = set()
            for p in found:
                if p in seen:
                    continue
                seen.add(p)
                uniq.append(p)

            if len(uniq) == 1:
                return uniq[0]
            return None

        final_path = search_unique(extracted_path) or extracted_path

        # Guard: if search_unique descended into a service-named folder,
        # check whether its parent contains sibling service folders.
        # If so, the parent is the real root, not the child.
        _SERVICE_FOLDER_NAMES = {
            "backend", "frontend", "client", "server", "api", "web", "ui",
            "app", "src", "admin", "dashboard", "worker", "services",
            "front", "back", "bend", "nodejs", "node", "express",
            "react", "vue", "angular", "spa",
        }
        _NOISE_DIRS = {
            ".git", ".github", ".circleci", ".vscode", ".idea", "docs",
            "scripts", "nginx", "node_modules", "__pycache__", "dist",
            "build", "coverage", ".cache", ".next", "db", "data",
            "database", "config", "configs", "routes", "models",
            "middleware", "middlewares", "controllers", "utils", "helpers",
            "lib", "public", "static", "assets", "images", "tf", "toolbox",
        }

        if final_path != extracted_path:
            leaf_name = os.path.basename(final_path).lower()
            if leaf_name in _SERVICE_FOLDER_NAMES:
                parent = os.path.dirname(final_path)
                try:
                    parent_contents = set(os.listdir(parent))
                    _DEP_FILES = {
                        "package.json", "requirements.txt", "pyproject.toml",
                        "pom.xml", "go.mod", "manage.py",
                    }
                    parent_has_dep = bool(parent_contents & _DEP_FILES)
                    siblings = [
                        d for d in parent_contents
                        if os.path.isdir(os.path.join(parent, d))
                        and d not in _NOISE_DIRS
                        and d.lower() in _SERVICE_FOLDER_NAMES
                    ]
                    # Use parent if:
                    # - parent has no dep file of its own (it's a container, not a project), OR
                    # - parent has 2+ service-named children (monorepo root)
                    if not parent_has_dep or len(siblings) >= 2:
                        final_path = parent
                except (PermissionError, OSError):
                    pass

        root = final_path

        if final_path != extracted_path:
            print(f"Found project root: {final_path}")

        return root
        
    except Exception as e:
        print(f"Error finding project root: {e}")
        return extracted_path


def detect_framework(project_path: str, use_ml: bool = True) -> Dict:
    """Hybrid detection: Heuristics first, ML as supplement"""
    
    print(f"\nStarting Hybrid Framework Detection")
    print(f"Project Path: {project_path}")
    print(f"ML Mode: {'Enabled' if use_ml else 'Disabled'}\n")
    
    actual_path = find_project_root(project_path, max_depth=3)
    
    results: Dict = {
        "framework": "Unknown",
        "language": "Unknown",
        "runtime": "alpine:latest",
        "dependencies": [],
        "port": None,
        "build_command": None,
        "start_command": None,
        "env_variables": [],
        "dockerfile": False,
        "docker_compose": False,
        "detected_files": [],
        "detection_confidence": {
            "language": 0.0,
            "framework": 0.0,
            "method": "unknown"
        },
        "has_package_json": False,
        "has_requirements_txt": False,
        "has_manage_py": False,
        "static_only": False,
        # New fields for DB & multi-port
        "database": "Unknown",
        "databases": [],
        "database_detection": {},
        "database_port": None,
        "backend_port": None,
        "frontend_port": None,
        # docker-aware ports (HOST ports)
        "docker_backend_ports": None,
        "docker_frontend_ports": None,
        "docker_database_ports": None,
        "docker_other_ports": None,
        # NEW: docker container ports
        "docker_backend_container_ports": None,
        "docker_frontend_container_ports": None,
        "docker_database_container_ports": None,
        "docker_other_container_ports": None,
        # Dockerfile EXPOSE ports (container ports)
        "docker_expose_ports": None,
    }
    
    try:
        print("Running heuristic detection (fast & reliable)...")
        heur_lang, heur_lang_conf = heuristic_language_detection(actual_path)
        heur_fw, heur_fw_conf = heuristic_framework_detection(actual_path, heur_lang)
        
        results["language"] = heur_lang
        results["framework"] = heur_fw
        results["detection_confidence"]["language"] = heur_lang_conf
        results["detection_confidence"]["framework"] = heur_fw_conf
        results["detection_confidence"]["method"] = "heuristic"
        
        # Optional ML supplement
        if use_ml and (heur_lang_conf < 0.5 or heur_fw_conf < 0.5):
            print("\nHeuristic confidence low, trying ML as supplement...")
            try:
                ml_analyzer = get_ml_analyzer()
                ml_results = ml_analyzer.analyze_project(actual_path)
                
                if ml_results.get("language_confidence", 0) > 0.6 and heur_lang == "Unknown":
                    results["language"] = ml_results["language"]
                    results["detection_confidence"]["language"] = ml_results["language_confidence"]
                    results["detection_confidence"]["method"] = "hybrid (ML language)"
                
                if ml_results.get("framework_confidence", 0) > 0.6 and heur_fw == "Unknown":
                    results["framework"] = ml_results["framework"]
                    results["detection_confidence"]["framework"] = ml_results["framework_confidence"]
                    # if we changed framework via ML, mark method accordingly
                    if results["detection_confidence"]["method"] == "heuristic":
                        results["detection_confidence"]["method"] = "hybrid (ML framework)"
            except Exception as e:
                print(f"ML analysis failed, continuing with heuristic: {e}")
        
                # Sanity check: prevent impossible framework/language combos
        fw_lang = FRAMEWORK_LANGUAGES.get(results["framework"])
        if fw_lang and results["language"] == "Unknown":
            results["language"] = fw_lang
            results["detection_confidence"]["language"] = max(results["detection_confidence"]["language"], 0.5)

        if fw_lang and results["language"] != "Unknown" and not _languages_compatible(results["language"], fw_lang):
            print(
                f"⚠️ Inconsistent detection: framework {results['framework']} "
                f"normally uses {fw_lang}, but language detected as {results['language']}. "
                f"Keeping framework and adjusting language."
            )
            results["language"] = fw_lang
            results["detection_confidence"]["language"] = max(results["detection_confidence"]["language"], 0.5)
            if results["detection_confidence"]["method"] == "heuristic":
                results["detection_confidence"]["method"] = "hybrid (framework->language)"


        # Runtime defaults (may include default port)
        runtime_info = get_runtime_info(results["language"], results["framework"])
        results.update(runtime_info)

        # --- Smart command extraction from actual project files ---
        # Override generic defaults with actual commands from package.json or Python entry points
        if results["language"] in ("JavaScript", "TypeScript") or results["framework"] in ("Express.js", "Next.js", "React"):
            nodejs_cmds = extract_nodejs_commands(actual_path)
            if nodejs_cmds.get("start_command"):
                results["start_command"] = nodejs_cmds["start_command"]
                print(f"📦 Overriding start_command with: {results['start_command']}")
            if nodejs_cmds.get("entry_point"):
                results["entry_point"] = nodejs_cmds["entry_point"]
            if nodejs_cmds.get("build_command"):
                results["build_command"] = nodejs_cmds["build_command"]
            if nodejs_cmds.get("build_output"):
                results["build_output"] = nodejs_cmds["build_output"]
                print(f"📦 Detected build_output: {results['build_output']}")
        
        elif results["language"] == "Python":
            python_cmds = extract_python_commands(actual_path)
            if python_cmds.get("start_command"):
                results["start_command"] = python_cmds["start_command"]
                print(f"🐍 Overriding start_command with: {results['start_command']}")
        # --- Lightweight presence flags for key files ---
        has_package_json = False
        has_requirements_txt = False
        has_manage_py = False

        for root, dirs, files in os.walk(actual_path):
            dirs[:] = [
                d for d in dirs
                if d not in ['node_modules', '__pycache__', '.git', 'venv', '.venv', 'dist', 'build', '.next']
            ]

            if 'package.json' in files:
                has_package_json = True
            if 'requirements.txt' in files:
                has_requirements_txt = True
            if 'manage.py' in files:
                has_manage_py = True

            if has_package_json and has_requirements_txt and has_manage_py:
                break

        results["has_package_json"] = has_package_json
        results["has_requirements_txt"] = has_requirements_txt
        results["has_manage_py"] = has_manage_py

        # Static-only JS/TS project: no package.json or Python server files
        results["static_only"] = (
            results["language"] in ("JavaScript", "TypeScript")
            and not has_package_json
            and not has_requirements_txt
            and not has_manage_py
        )

        if results["static_only"]:
            # Prefer a static server image; do NOT invent Node/Django commands
            print("🔍 Detected static-only JS/TS project (no package.json/manage.py/requirements.txt).")
            results["runtime"] = "nginx:alpine"
            results["port"] = 80
            results["build_command"] = None
            results["start_command"] = None

        
        # Dependencies (root + nested subprojects like client/server)
        dep_files = {
            "requirements.txt": "requirements.txt",
            "pyproject.toml": "pyproject.toml",
            "Pipfile": "Pipfile",
            "poetry.lock": "poetry.lock",
            "package.json": "package.json",
            "pom.xml": "pom.xml",
            "go.mod": "go.mod",
            "composer.json": "composer.json",
            "Cargo.toml": "Cargo.toml",
        }
        
        visited_dep_files = set()
        
        # 1) Root-level dep files
        for filename, file_type in dep_files.items():
            file_path = os.path.join(actual_path, filename)
            if os.path.exists(file_path):
                deps = parse_dependencies_file(file_path, file_type)
                results["dependencies"].extend(deps)
                if filename not in results["detected_files"]:
                    results["detected_files"].append(filename)
                visited_dep_files.add(os.path.abspath(file_path))
        
        # 2) Nested dep files (e.g. mern/client/package.json, mern/server/package.json)
        for root, dirs, files in os.walk(actual_path):
            dirs[:] = [
                d for d in dirs
                if d not in ['node_modules', '__pycache__', '.git', 'venv', '.venv', 'dist', 'build', '.next']
            ]
            
            for file in files:
                if file in dep_files:
                    full_path = os.path.abspath(os.path.join(root, file))
                    if full_path in visited_dep_files:
                        continue
                    
                    file_type = dep_files[file]
                    deps = parse_dependencies_file(full_path, file_type)
                    results["dependencies"].extend(deps)
                    if file not in results["detected_files"]:
                        results["detected_files"].append(file)
                    
                    visited_dep_files.add(full_path)
        
        # Docker files
        docker_info = detect_docker_files(actual_path)
        results["dockerfile"] = docker_info["dockerfile"]
        results["docker_compose"] = docker_info["docker_compose"]
        results["detected_files"].extend(docker_info["detected_files"])
        
        # Env vars
        env_vars = detect_env_variables(actual_path)
        if env_vars:
            results["env_variables"] = env_vars
        
        # DB + port detection (using final language/framework + deps/env + base port)
        db_info, ports_info = detect_db_and_ports(
            actual_path,
            results["language"],
            results["framework"],
            results["dependencies"],
            results.get("env_variables", []),
            base_port=results.get("port")
        )
        
        results["database"] = db_info.get("primary", "Unknown")
        results["databases"] = db_info.get("all", [])
        results["database_detection"] = db_info.get("details", {})
        
        # IMPORTANT: Only set database_port if database is LOCAL (needs container)
        # Cloud databases (is_cloud=True) should have NO port to avoid confusing LLM
        if results.get("database_is_cloud"):
            results["database_port"] = None  # Cloud DB - no container needed
            print(f"☁️ Database is cloud - clearing database_port")
        else:
            results["database_port"] = db_info.get("port")
        
        if ports_info.get("backend_port") is not None:
            results["backend_port"] = ports_info["backend_port"]
            # Keep existing 'port' field as backend port for backwards compatibility
            results["port"] = ports_info["backend_port"]
        
        if ports_info.get("frontend_port") is not None:
            results["frontend_port"] = ports_info["frontend_port"]
        
        if "docker_backend_ports" in ports_info:
            results["docker_backend_ports"] = ports_info.get("docker_backend_ports")
        if "docker_frontend_ports" in ports_info:
            results["docker_frontend_ports"] = ports_info.get("docker_frontend_ports")
        if "docker_database_ports" in ports_info:
            results["docker_database_ports"] = ports_info.get("docker_database_ports")
        if "docker_other_ports" in ports_info:
            results["docker_other_ports"] = ports_info.get("docker_other_ports")
        if "docker_backend_container_ports" in ports_info:
            results["docker_backend_container_ports"] = ports_info.get("docker_backend_container_ports")
        if "docker_frontend_container_ports" in ports_info:
            results["docker_frontend_container_ports"] = ports_info.get("docker_frontend_container_ports")
        if "docker_database_container_ports" in ports_info:
            results["docker_database_container_ports"] = ports_info.get("docker_database_container_ports")
        if "docker_other_container_ports" in ports_info:
            results["docker_other_container_ports"] = ports_info.get("docker_other_container_ports")
        if "docker_expose_ports" in ports_info:
            results["docker_expose_ports"] = ports_info.get("docker_expose_ports")

        # Service inference (uses file tree + metadata; compose only as hints)
        try:
            results["services"] = infer_services(
                actual_path,
                results.get("language", "Unknown"),
                results.get("framework", "Unknown"),
                results
            )
        except Exception:
            results["services"] = []
        
        # =======================================================================
        # PORT CONSOLIDATION: Copy service ports to metadata for consistency
        # The per-service ports (from extract_port_from_project) are authoritative
        # because they check the actual service directory's .env and source files.
        # =======================================================================
        for svc in results.get("services", []):
            svc_type = svc.get("type")
            svc_port = svc.get("port")
            svc_port_source = svc.get("port_source", "unknown")
            
            if svc_type in ("backend", "monolith") and svc_port:
                # Only override if service port came from a reliable source
                if svc_port_source in ("env", "source"):
                    print(f"🔧 Consolidating: backend_port = {svc_port} (from {svc_port_source})")
                    results["backend_port"] = svc_port
                    results["port"] = svc_port  # backwards compat
                elif results.get("backend_port") is None:
                    # Use service port as fallback if no port detected yet
                    results["backend_port"] = svc_port
                    results["port"] = svc_port
            
            elif svc_type == "frontend" and svc_port:
                if svc_port_source in ("env", "source", "vite_default", "cra_default"):
                    print(f"🔧 Consolidating: frontend_port = {svc_port} (from {svc_port_source})")
                    results["frontend_port"] = svc_port
                elif results.get("frontend_port") is None:
                    results["frontend_port"] = svc_port
        
        # =======================================================================
        # CLOUD DATABASE: Clear database_port if database is cloud
        # database_is_cloud is set by infer_services -> extract_database_info()
        # This ensures LLM doesn't add a database container for cloud DBs
        # =======================================================================
        if results.get("database_is_cloud"):
            results["database_port"] = None
            print(f"☁️ Cloud database detected - clearing database_port (no container needed)")
        
        # =======================================================================
        # DEPLOY BLOCKED CHECK: Backend service requires .env file
        # If backend exists but has no .env, block deployment and notify user
        # =======================================================================
        backend_services = [s for s in results.get("services", []) if s.get("type") in ("backend", "monolith")]
        backend_missing_env = any(
            svc.get("type") in ("backend", "monolith") and not svc.get("env_file")
            for svc in results.get("services", [])
        )
        
        if backend_services and backend_missing_env:
            if results.get("database") != "Unknown":
                # Database detected + no .env → BLOCK deployment
                results["deploy_blocked"] = True
                results["deploy_blocked_reason"] = (
                    "Backend .env file is required because a database was detected. "
                    "Please add a .env file with DATABASE_URL, PORT, and other secrets."
                )
                results["backend_env_missing"] = True
                results["deploy_warning"] = None
                print(f"⚠️ Deploy blocked: Backend .env file missing (database detected)")
            else:
                # No database + no .env → WARNING only (not blocked)
                results["deploy_blocked"] = False
                results["deploy_blocked_reason"] = None
                results["backend_env_missing"] = True
                results["deploy_warning"] = (
                    "No .env detected. Proceed only if your app doesn't require secrets."
                )
                print(f"⚠️ Deploy warning: Backend .env file missing (no database)")
        else:
            results["deploy_blocked"] = False
            results["deploy_blocked_reason"] = None
            results["backend_env_missing"] = False
            results["deploy_warning"] = None
        
        # Deduplicate detected_files
        results["detected_files"] = list(set(results["detected_files"]))

        # Safe debug print
        try:
            print("Here are all the results:\n" + json.dumps(results, indent=2, default=str))
        except Exception:
            print("Here are all the results (non-serializable parts skipped)")
        
        print(f"\nDetection Complete!")
        print(f"   Language: {results['language']} (confidence: {results['detection_confidence']['language']:.2f})")
        print(f"   Framework: {results['framework']} (confidence: {results['detection_confidence']['framework']:.2f})")
        print(f"   Method: {results['detection_confidence']['method']}\n")
        
        return results
        
    except Exception as e:
        print(f"Detection error: {e}")
        import traceback
        traceback.print_exc()
        return results
