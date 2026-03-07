"""
Database detection helpers — identifies databases from dependencies, env vars,
and docker-compose images.
Extracted from detector.py to reduce its size.
"""

import os
import re
from typing import Dict, List, Tuple, Optional

from .detection_constants import DB_INDICATORS, DB_ENV_KEYWORDS


def _infer_database_port(
    primary_db: str,
    env_kv: Dict[str, str],
    compose_content: str
) -> Optional[int]:
    """
    Infer database port from env key/values and docker-compose content.
    Falls back to well-known defaults if nothing explicit is found.
    """
    primary = primary_db or "Unknown"
    DEFAULT_DB_PORTS: Dict[str, Optional[int]] = {
        "PostgreSQL": 5432,
        "MySQL": 3306,
        "MongoDB": 27017,
        "SQLite": None,  # file-based
        "Redis": 6379,
    }

    # DB-specific env keys to prefer over generic PORT vars
    DB_SPECIFIC_PORT_KEYS: Dict[str, List[str]] = {
        "PostgreSQL": ["PGPORT", "POSTGRES_PORT", "DB_PORT", "DATABASE_PORT"],
        "MySQL": ["MYSQL_PORT", "MARIADB_PORT", "DB_PORT", "DATABASE_PORT"],
        "MongoDB": ["MONGO_PORT", "MONGODB_PORT", "DB_PORT", "DATABASE_PORT"],
        "Redis": ["REDIS_PORT", "DB_PORT", "DATABASE_PORT"],
    }
    
    default_port = DEFAULT_DB_PORTS.get(primary, None)
    specific_ports: List[int] = []
    generic_ports: List[int] = []
    
    # 1) From env key/values (DB-specific first, then generic PORT keys)
    specific_keys_for_db = set(DB_SPECIFIC_PORT_KEYS.get(primary, []))
    
    for key, value in env_kv.items():
        key_upper = key.upper()
        val = value.strip()
        
        # DB-specific keys
        if key_upper in specific_keys_for_db:
            if val.isdigit():
                specific_ports.append(int(val))
            else:
                for m in re.findall(r":(\d{2,5})", val):
                    try:
                        specific_ports.append(int(m))
                    except ValueError:
                        continue
            continue
        
        # Generic DB PORT keys (NOT plain "PORT" which is for backend!)
        # Only use DB_PORT or DATABASE_PORT for database port inference
        if key_upper in ("DB_PORT", "DATABASE_PORT"):
            if val.isdigit():
                generic_ports.append(int(val))
            else:
                for m in re.findall(r":(\d{2,5})", val):
                    try:
                        generic_ports.append(int(m))
                    except ValueError:
                        continue
    
    # Prefer env-based port matching default if available (specific first)
    if default_port is not None:
        if default_port in specific_ports:
            return default_port
        if specific_ports:
            return specific_ports[0]
        if default_port in generic_ports:
            return default_port
    
    if specific_ports:
        return specific_ports[0]
    
    if generic_ports:
        return generic_ports[0]
    
    # 2) From docker-compose port mappings
    # Look for patterns like "5432:5432" or "15432:5432"
    if compose_content and default_port is not None:
        try:
            # host:container
            pattern = re.compile(r"(\d{2,5})\s*:\s*(\d{2,5})")
            for host_p, container_p in pattern.findall(compose_content):
                try:
                    host_port = int(host_p)
                    container_port = int(container_p)
                except ValueError:
                    continue
                
                if container_port == default_port:
                    return host_port  # host port that maps to default DB port
        except Exception as e:
            print(f"Error inferring DB port from compose: {e}")
    
    # 3) Fall back to default if known (non-SQLite)
    return default_port


def detect_databases(
    project_path: str,
    dependencies: List[str],
    env_vars: List[str]
) -> Dict:
    """
    Detect likely databases based on:
    - dependency names
    - env var keys (including nested backend/frontend .env files)
    - docker-compose images
    Also tries to infer a database port.
    """
    # Import here to avoid circular imports
    from .detector import _read_env_key_values
    from .detection_ports import _detect_fullstack_structure

    deps_lower = [d.lower() for d in dependencies]
    
    # docker-compose content
    compose_content = ""
    for fname in ("docker-compose.yml", "docker-compose.yaml"):
        cpath = os.path.join(project_path, fname)
        if os.path.exists(cpath):
            try:
                with open(cpath, "r", encoding="utf-8", errors="ignore") as f:
                    compose_content += f.read().lower()
            except Exception:
                pass
    
    # read env key/values for DB hints (root + nested backend/frontend .env files)
    env_kv_root = _read_env_key_values(project_path)
    env_kv: Dict[str, str] = dict(env_kv_root)

    try:
        fullstack = _detect_fullstack_structure(project_path)
        backend_path = fullstack.get("backend_path")
        frontend_path = fullstack.get("frontend_path")

        if backend_path:
            env_kv.update(_read_env_key_values(backend_path) or {})
        if frontend_path:
            env_kv.update(_read_env_key_values(frontend_path) or {})
    except Exception as e:
        print(f"Error reading nested .env files for DB detection: {e}")

    # env var keys for DB indicator scoring:
    # - from the original env_vars list (root)
    # - plus any keys we saw in nested .env files
    env_lower_from_list = [e.lower() for e in env_vars]
    env_lower_from_kv = [k.lower() for k in env_kv.keys()]
    env_lower = list(set(env_lower_from_list) | set(env_lower_from_kv))
    
    scores: Dict[str, float] = {}
    evidence: Dict[str, List[str]] = {}
    
    for db_name, info in DB_INDICATORS.items():
        score = 0.0
        ev: List[str] = []
        
        # Dependencies
        for dep_pattern in info["dependencies"]:
            for d in deps_lower:
                if dep_pattern in d:
                    score += 1.0
                    ev.append(f"dependency:{dep_pattern}")
                    break
        
        # Env var keys
        for key in info["env_keys"]:
            if key.lower() in env_lower:
                score += 0.8
                ev.append(f"env:{key}")

        # Opportunistic substring match (captures POSTGRES_URL, MONGODB_URL, etc.)
        substrings = DB_ENV_KEYWORDS.get(db_name, [])
        if substrings:
            for env_key in env_lower:
                if any(sub in env_key for sub in substrings):
                    score += 0.4
                    ev.append(f"env_like:{env_key}")
                    break
        
        # docker-compose images
        for img in info["compose_images"]:
            if img in compose_content:
                score += 0.7
                ev.append(f"compose:{img}")
        
        if score > 0:
            scores[db_name] = score
            evidence[db_name] = ev
    
    if not scores:
        return {
            "primary": "Unknown",
            "all": [],
            "details": {},
            "port": None
        }
    
    # Sort databases by score desc
    sorted_dbs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_dbs[0][0]
    all_names = [name for name, _ in sorted_dbs]
    
    details = {
        name: {"score": scores[name], "evidence": evidence.get(name, [])}
        for name in all_names
    }
    
    print(f"   Detected databases (best first): {all_names}")
    
    # infer port for primary DB (using merged env values)
    db_port = _infer_database_port(primary, env_kv, compose_content)
    
    return {
        "primary": primary,
        "all": all_names,
        "details": details,
        "port": db_port
    }


def detect_db_and_ports(
    project_path: str,
    language: str,
    framework: str,
    dependencies: List[str],
    env_vars: List[str],
    base_port: Optional[int]
) -> Tuple[Dict, Dict]:
    """
    High-level helper:
    - database detection
    - port detection (backend & frontend)
    """
    from .detection_ports import detect_ports_for_project

    db_info = detect_databases(project_path, dependencies, env_vars)
    ports_info = detect_ports_for_project(project_path, language, framework, base_port)
    return db_info, ports_info
