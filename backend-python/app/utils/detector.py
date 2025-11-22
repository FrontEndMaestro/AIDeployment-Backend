import os
import json
import re
from collections import Counter
from typing import Dict, List, Tuple, Optional
from .ml_analyzer import get_ml_analyzer


# Concrete detection rules (these are highly reliable)
LANGUAGE_INDICATORS = {
    "Python": {
        "extensions": [".py"],
        "files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
        "imports": ["import django", "import flask", "import fastapi", "import requests", "from django", "from flask"],
        "weight": 1.0
    },
    "JavaScript": {
        "extensions": [".js", ".jsx"],
        "files": ["package.json", "package-lock.json", "yarn.lock"],
        "imports": ["require('", "import {", "import '", "from '", "export "],
        "weight": 1.0
    },
    "TypeScript": {
        "extensions": [".ts", ".tsx"],
        "files": ["tsconfig.json"],
        "imports": ["interface ", "type "],
        "weight": 1.0
    },
    "Java": {
        "extensions": [".java"],
        "files": ["pom.xml", "build.gradle", "settings.gradle"],
        "imports": ["import java", "package "],
        "weight": 1.0
    },
    "Go": {
        "extensions": [".go"],
        "files": ["go.mod", "go.sum"],
        "imports": ["package main", "import ("],
        "weight": 1.0
    },
    "Ruby": {
        "extensions": [".rb"],
        "files": ["Gemfile", "Gemfile.lock"],
        "imports": ["require '", "gem "],
        "weight": 1.0
    },
    "PHP": {
        "extensions": [".php"],
        "files": ["composer.json", "composer.lock"],
        "imports": ["<?php", "namespace ", "use "],
        "weight": 1.0
    }
}

FRAMEWORK_INDICATORS = {
    "Flask": {
        "markers": ["from flask import", "Flask(__name__)", "@app.route"],
        "files": [],
        "dependencies": ["flask", "Flask"],
        "confidence_weight": 0.95
    },
    "Django": {
        "markers": ["from django", "django.conf", "settings.INSTALLED_APPS", "manage.py"],
        "files": ["manage.py", "settings.py"],
        "dependencies": ["django", "Django"],
        "confidence_weight": 0.95
    },
    "FastAPI": {
        "markers": ["from fastapi import", "FastAPI()", "app.get(", "app.post("],
        "files": [],
        "dependencies": ["fastapi", "FastAPI"],
        "confidence_weight": 0.95
    },
    "Express.js": {
        "markers": ["require('express')", "const express", "app.listen", "app.get(", "app.post("],
        "files": [],
        "dependencies": ["express"],
        "confidence_weight": 0.95
    },
    "Next.js": {
        "markers": ["next/", "getServerSideProps", "getStaticProps", "pages/"],
        "files": ["next.config.js", "pages/"],
        "dependencies": ["next"],
        "confidence_weight": 0.95
    },
    "React": {
        "markers": ["import React", "from 'react'", "useState(", "useEffect(", "JSX"],
        "files": [],
        "dependencies": ["react"],
        "confidence_weight": 0.9
    },
    "Spring Boot": {
        "markers": ["@SpringBootApplication", "@RestController", "@GetMapping", "@Autowired"],
        "files": ["pom.xml", "application.properties"],
        "dependencies": ["spring-boot", "spring-web"],
        "confidence_weight": 0.95
    },
    "Laravel": {
        "markers": ["use Illuminate", "Route::", "Schema::", "artisan"],
        "files": ["artisan", "config/app.php"],
        "dependencies": ["laravel"],
        "confidence_weight": 0.95
    },
    "Rails": {
        "markers": ["rails", "ActiveRecord", "has_many", "belongs_to", "Gemfile"],
        "files": ["Gemfile", "config/routes.rb"],
        "dependencies": ["rails"],
        "confidence_weight": 0.95
    }
}

# Simple mapping to tie frameworks to primary language for scoring
FRAMEWORK_LANGUAGES: Dict[str, str] = {
    "Flask": "Python",
    "Django": "Python",
    "FastAPI": "Python",
    "Express.js": "JavaScript",
    "Next.js": "JavaScript",
    "React": "JavaScript",
    "Spring Boot": "Java",
    "Laravel": "PHP",
    "Rails": "Ruby",
}

# --- Database indicator config (for DB detection) ---

DB_INDICATORS = {
    "PostgreSQL": {
        "dependencies": [
            "psycopg2", "psycopg2-binary", "asyncpg", "pg", "pg-promise",
            "org.postgresql", "postgresql", "pgx", "pq"
        ],
        "env_keys": ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL"],
        "compose_images": ["postgres"]
    },
    "MySQL": {
        "dependencies": [
            "mysqlclient", "pymysql", "mysql-connector", "mysql-connector-python",
            "mysql2", "mysql", "mariadb-java-client", "mariadb"
        ],
        "env_keys": ["MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"],
        "compose_images": ["mysql", "mariadb"]
    },
    "MongoDB": {
        "dependencies": ["pymongo", "mongoengine", "mongoose", "mongodb", "motor"],
        "env_keys": ["MONGO_URI", "MONGODB_URI"],
        "compose_images": ["mongo"]
    },
    "SQLite": {
        "dependencies": ["sqlite3"],
        "env_keys": [],
        "compose_images": []
    },
    "Redis": {
        "dependencies": ["redis", "aioredis", "ioredis"],
        "env_keys": ["REDIS_URL", "REDIS_HOST"],
        "compose_images": ["redis"]
    }
}


def parse_dependencies_file(file_path: str, file_type: str) -> List[str]:
    """Parse dependencies from various file types"""
    dependencies = []
    
    try:
        if file_type == "requirements.txt":
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                dependencies = [
                    line.split('==')[0].split('>=')[0].split('~=')[0].split('[')[0].strip()
                    for line in content.split('\n')
                    if line.strip() and not line.startswith('#') and not line.startswith('-')
                ]
        
        elif file_type == "package.json":
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                dependencies = list(deps.keys())
        
        elif file_type == "pom.xml":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                artifacts = re.findall(r'<artifactId>(.*?)</artifactId>', content)
                dependencies = artifacts[:20]
        
        elif file_type == "go.mod":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                deps: List[str] = []
                for line in content.split('\n'):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith(('module', 'go', 'require', 'replace', '//')):
                        continue
                    parts = stripped.split()
                    if parts:
                        deps.append(parts[0])
                dependencies = deps
    
    except Exception as e:
        print(f"Error parsing {file_type}: {e}")
    
    return dependencies[:50]


def get_runtime_info(language: str, framework: str) -> Dict:
    """Get runtime, ports, and commands based on detected language/framework"""
    
    runtime_map = {
        "Python": {
            "runtime": "python:3.11-slim",
            "port": 8000,
            "build_command": "pip install -r requirements.txt",
            "start_command": "python main.py"
        },
        "JavaScript": {
            "runtime": "node:20-alpine",
            "port": 3000,
            "build_command": "npm install",
            "start_command": "npm start"
        },
        "TypeScript": {
            "runtime": "node:20-alpine",
            "port": 3000,
            "build_command": "npm install && npm run build",
            "start_command": "npm start"
        },
        "Java": {
            "runtime": "openjdk:17-slim",
            "port": 8080,
            "build_command": "mvn clean install",
            "start_command": "java -jar target/*.jar"
        },
        "Go": {
            "runtime": "golang:1.21-alpine",
            "port": 8080,
            "build_command": "go build -o main .",
            "start_command": "./main"
        },
        "Ruby": {
            "runtime": "ruby:3.2-alpine",
            "port": 3000,
            "build_command": "bundle install",
            "start_command": "ruby app.rb"
        },
        "PHP": {
            # Use CLI image when starting via `php -S`
            "runtime": "php:8.2-cli",
            "port": 80,
            "build_command": "composer install",
            "start_command": "php -S 0.0.0.0:80"
        }
    }
    
    framework_overrides = {
        "Flask": {"port": 5000, "start_command": "flask run --host=0.0.0.0"},
        "Django": {"port": 8000, "start_command": "python manage.py runserver 0.0.0.0:8000"},
        "FastAPI": {"port": 8000, "start_command": "uvicorn main:app --host 0.0.0.0 --port 8000"},
        "Express.js": {"port": 3000, "start_command": "node server.js"},
        "Next.js": {"port": 3000, "build_command": "npm run build", "start_command": "npm run start"},
        "Spring Boot": {"port": 8080, "start_command": "java -jar target/*.jar"},
        "Laravel": {"port": 8000, "start_command": "php artisan serve --host=0.0.0.0"},
        "Rails": {"port": 3000, "start_command": "rails server"},
    }
    
    base_info = runtime_map.get(language, {
        "runtime": "alpine:latest",
        "port": 8000,
        "build_command": None,
        "start_command": None
    })
    
    if framework in framework_overrides:
        base_info.update(framework_overrides[framework])
    
    return base_info


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
            'package.json', 'requirements.txt', 'pom.xml', 'build.gradle',
            'composer.json', 'go.mod', 'Gemfile', 'setup.py'
        ]
        
        def search_recursively(current_path: str, depth: int = 0) -> str:
            if depth > max_depth:
                return current_path
            
            try:
                items = os.listdir(current_path)
                folders = [item for item in items if os.path.isdir(os.path.join(current_path, item))]
                files = [item for item in items if os.path.isfile(os.path.join(current_path, item))]
                
                has_framework_file = any(f in files for f in framework_files)
                
                if has_framework_file:
                    return current_path
                
                if len(folders) == 1 and len(files) == 0:
                    nested_path = os.path.join(current_path, folders[0])
                    print(f"Going deeper: {folders[0]}")
                    return search_recursively(nested_path, depth + 1)
                
                return current_path
            
            except Exception as e:
                print(f"Error scanning {current_path}: {e}")
                return current_path
        
        final_path = search_recursively(extracted_path)
        
        if final_path != extracted_path:
            print(f"Found project root: {final_path}")
        
        return final_path
        
    except Exception as e:
        print(f"Error finding project root: {e}")
        return extracted_path


def heuristic_language_detection(project_path: str) -> Tuple[str, float]:
    """Detect language using file extensions, config files, and imports - highly reliable"""
    
    language_scores = {lang: 0.0 for lang in LANGUAGE_INDICATORS.keys()}
    found_evidence = []
    
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', 'venv', 'dist', 'build', '.next']]
            
            for file in files:
                file_path = os.path.join(root, file)
                _, ext = os.path.splitext(file)
                
                for lang, indicators in LANGUAGE_INDICATORS.items():
                    if ext.lower() in indicators["extensions"]:
                        language_scores[lang] += 0.3
                        if not any(e[0] == lang and e[1] == "extension" for e in found_evidence):
                            found_evidence.append((lang, "extension", file))
                
                for lang, indicators in LANGUAGE_INDICATORS.items():
                    if file in indicators["files"]:
                        language_scores[lang] += 0.7
                        found_evidence.append((lang, "config_file", file))
                
                if ext.lower() in ['.py', '.js', '.ts', '.java', '.go', '.rb', '.php']:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(10000)
                            
                            for lang, indicators in LANGUAGE_INDICATORS.items():
                                for import_pattern in indicators["imports"]:
                                    if import_pattern.lower() in content.lower():
                                        language_scores[lang] += 0.4
                                        found_evidence.append((lang, "import", import_pattern))
                                        break
                    except:
                        pass
    
    except Exception as e:
        print(f"Error during heuristic detection: {e}")
    
    best_language = "Unknown"
    best_score = 0.0
    
    for lang, score in language_scores.items():
        if score > best_score:
            best_score = score
            best_language = lang
    
    confidence = min(best_score / 2.0, 1.0)
    
    if best_score > 0:
        print(f"   Heuristic Language: {best_language} (score: {best_score:.2f})")
    
    return best_language, confidence


def heuristic_framework_detection(project_path: str, language: str) -> Tuple[str, float]:
    """Detect framework using markers, config files, and dependencies - highly reliable"""
    
    framework_scores: Dict[str, float] = {}
    found_evidence = []
    
    try:
        dependencies = set()
        
        req_path = os.path.join(project_path, "requirements.txt")
        if os.path.exists(req_path):
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        pkg = line.split('==')[0].split('>=')[0].split('[')[0].strip().lower()
                        if pkg:
                            dependencies.add(pkg)
            except:
                pass
        
        pkg_json_path = os.path.join(project_path, "package.json")
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for dep in data.get('dependencies', {}).keys():
                        dependencies.add(dep.lower())
                    for dep in data.get('devDependencies', {}).keys():
                        dependencies.add(dep.lower())
            except:
                pass
        
        composer_path = os.path.join(project_path, "composer.json")
        if os.path.exists(composer_path):
            try:
                with open(composer_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for dep in data.get('require', {}).keys():
                        dependencies.add(dep.lower())
            except:
                pass
        
        pom_path = os.path.join(project_path, "pom.xml")
        if os.path.exists(pom_path):
            try:
                with open(pom_path, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                    for dep in re.findall(r'<artifactid>(.*?)</artifactid>', content):
                        dependencies.add(dep.lower())
            except:
                pass
        
        for framework, indicators in FRAMEWORK_INDICATORS.items():
            for dep in indicators["dependencies"]:
                if dep.lower() in dependencies:
                    framework_scores[framework] = framework_scores.get(framework, 0.0) + 0.8
                    found_evidence.append((framework, "dependency", dep))
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', 'venv', 'dist', 'build']]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ['.py', '.js', '.ts', '.java', '.go', '.rb', '.php']:
                    file_path = os.path.join(root, file)
                    
                    for framework, indicators in FRAMEWORK_INDICATORS.items():
                        if file in indicators["files"]:
                            framework_scores[framework] = framework_scores.get(framework, 0.0) + 0.6
                            found_evidence.append((framework, "file", file))
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(10000)
                            
                            for framework, indicators in FRAMEWORK_INDICATORS.items():
                                for marker in indicators["markers"]:
                                    if marker.lower() in content.lower():
                                        framework_scores[framework] = framework_scores.get(framework, 0.0) + 0.5
                                        found_evidence.append((framework, "marker", marker))
                                        break
                    except:
                        pass
        
    except Exception as e:
        print(f"Error during framework heuristic detection: {e}")
    
    best_framework = "Unknown"
    best_score = 0.0
    
    # Apply a soft penalty for frameworks that don't match the detected language
    for framework, score in framework_scores.items():
        fw_lang = FRAMEWORK_LANGUAGES.get(framework)
        adjusted_score = score
        if fw_lang and language != "Unknown" and fw_lang != language:
            adjusted_score *= 0.5  # penalize mismatched language/framework
        if adjusted_score > best_score:
            best_score = adjusted_score
            best_framework = framework
    
    confidence = min(best_score / 2.0, 1.0)
    
    if best_score > 0:
        print(f"   Heuristic Framework: {best_framework} (score: {best_score:.2f})")
    
    return best_framework, confidence


# ----- Port detection helpers -----


def _detect_fullstack_structure(project_path: str) -> Dict[str, Optional[str]]:
    """
    Detect typical fullstack structure with separate frontend/backend folders.
    Looks for 'backend/server/api' and 'frontend/client/web' with package.json.
    """
    structure = {
        "is_fullstack": False,
        "has_backend": False,
        "has_frontend": False,
        "backend_path": None,
        "frontend_path": None,
    }
    
    for root, dirs, files in os.walk(project_path):
        depth = root.replace(project_path, '').count(os.sep)
        if depth > 2:
            continue
        
        for folder in dirs:
            folder_lower = folder.lower()
            folder_path = os.path.join(root, folder)
            pkg_path = os.path.join(folder_path, "package.json")
            
            if os.path.exists(pkg_path):
                if folder_lower in ["backend", "server", "api"]:
                    structure["has_backend"] = True
                    structure["backend_path"] = folder_path
                    structure["is_fullstack"] = True
                    print(f"🔍 Fullstack: found backend folder '{folder}'")
                if folder_lower in ["frontend", "client", "web"]:
                    structure["has_frontend"] = True
                    structure["frontend_path"] = folder_path
                    structure["is_fullstack"] = True
                    print(f"🔍 Fullstack: found frontend folder '{folder}'")
    
    return structure


def _detect_port_from_package_json(project_path: str, prefer_frontend: bool = False) -> Optional[int]:
    """
    Guess port from package.json scripts.
    prefer_frontend:
      - True  => prioritise typical frontend ports
      - False => prioritise typical backend ports
    """
    pkg_json = os.path.join(project_path, "package.json")
    if not os.path.exists(pkg_json):
        return None
    
    try:
        with open(pkg_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading package.json for port detection: {e}")
        return None
    
    scripts = data.get("scripts", {})
    script_strings = " ".join(str(v) for v in scripts.values())
    
    # Look for explicit PORT=XXXX patterns first
    match = re.search(r"\bPORT\s*=?\s*(\d{2,5})\b", script_strings)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    
    # Heuristic port priorities
    if prefer_frontend:
        candidates = [3000, 5173, 4173, 4200, 8080, 8000, 5000, 4000]
    else:
        candidates = [8000, 8080, 5000, 4000, 3000, 5173, 4200]
    
    # More precise matching than simple substring
    for port in candidates:
        port_pattern = re.compile(
            rf"(?:[:=]\s*{port}\b|\bPORT\s*=?\s*{port}\b)"
        )
        if port_pattern.search(script_strings):
            return port
    
    # Default for Node apps
    return 3000


def _scan_code_for_ports(project_path: str, max_files: int = 150) -> Optional[int]:
    """
    Generic port scan: look for host:port patterns in code.
    Used mainly for non-JS/TS projects.
    """
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php"}
    pattern = re.compile(
        r"(?:0\.0\.0\.0|127\.0\.0\.1|localhost)\s*[: ]\s*(\d{2,5})"
    )
    
    counts: Counter = Counter()
    files_scanned = 0
    
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                "node_modules", "__pycache__", ".git", "venv", ".venv",
                "dist", "build", ".next", "target", "bin", "obj", "out"
            ]]
            
            for file in files:
                if files_scanned >= max_files:
                    break
                _, ext = os.path.splitext(file)
                if ext.lower() not in exts:
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(8000)
                    for m in pattern.finditer(content):
                        try:
                            port = int(m.group(1))
                            if 1024 <= port <= 65535:
                                counts[port] += 1
                        except ValueError:
                            continue
                except Exception:
                    continue
                files_scanned += 1
            
            if files_scanned >= max_files:
                break
    except Exception as e:
        print(f"Port scan error: {e}")
    
    if not counts:
        return None
    
    # Most frequent port
    port, _ = counts.most_common(1)[0]
    return port


def detect_ports_for_project(
    project_path: str,
    language: str,
    framework: str,
    base_port: Optional[int]
) -> Dict[str, Optional[int]]:
    """
    Detect backend and frontend ports.
    - For JS/TS: look for fullstack structure and read package.json.
    - For others: scan code for host:port; fall back to base_port / defaults.
    """
    backend_port: Optional[int] = None
    frontend_port: Optional[int] = None
    
    # JS / TS fullstack or single service
    if language in ["JavaScript", "TypeScript"]:
        fullstack = _detect_fullstack_structure(project_path)
        
        # Backend
        if fullstack.get("has_backend") and fullstack.get("backend_path"):
            backend_port = _detect_port_from_package_json(
                fullstack["backend_path"], prefer_frontend=False
            )
        else:
            backend_port = _detect_port_from_package_json(
                project_path, prefer_frontend=False
            )
        
        # Frontend
        if fullstack.get("has_frontend") and fullstack.get("frontend_path"):
            frontend_port = _detect_port_from_package_json(
                fullstack["frontend_path"], prefer_frontend=True
            )
        # If no explicit frontend folder we leave frontend_port = None
        
    else:
        # Non JS/TS: single backend service usually.
        detected = _scan_code_for_ports(project_path)
        if detected:
            backend_port = detected
        else:
            # fallback to base_port or language default
            backend_port = base_port
            if backend_port is None:
                # Just in case base_port is not set, create a small default map
                default_ports = {
                    "Python": 8000,
                    "Java": 8080,
                    "Go": 8080,
                    "Ruby": 3000,
                    "PHP": 8000
                }
                backend_port = default_ports.get(language, 8000)
    
    return {
        "backend_port": backend_port,
        "frontend_port": frontend_port
    }


# ----- Database detection helpers -----


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
        
        # Generic PORT keys
        if "PORT" in key_upper:
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
    - env var keys
    - docker-compose images
    Also tries to infer a database port.
    """
    deps_lower = [d.lower() for d in dependencies]
    env_lower = [e.lower() for e in env_vars]
    
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
    
    # read env key/values for DB port hints
    env_kv = _read_env_key_values(project_path)
    
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
    
    # infer port for primary DB
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
    db_info = detect_databases(project_path, dependencies, env_vars)
    ports_info = detect_ports_for_project(project_path, language, framework, base_port)
    return db_info, ports_info


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
        # New fields for DB & multi-port
        "database": "Unknown",
        "databases": [],
        "database_detection": {},
        "database_port": None,
        "backend_port": None,
        "frontend_port": None,
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
        
        # Runtime defaults (may include default port)
        runtime_info = get_runtime_info(results["language"], results["framework"])
        results.update(runtime_info)
        
        # Dependencies
        dep_files = {
            "requirements.txt": "requirements.txt",
            "package.json": "package.json",
            "pom.xml": "pom.xml",
            "go.mod": "go.mod"
        }
        
        for filename, file_type in dep_files.items():
            file_path = os.path.join(actual_path, filename)
            if os.path.exists(file_path):
                deps = parse_dependencies_file(file_path, file_type)
                results["dependencies"].extend(deps)
                if filename not in results["detected_files"]:
                    results["detected_files"].append(filename)
        
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
        results["database_port"] = db_info.get("port")
        
        if ports_info.get("backend_port") is not None:
            results["backend_port"] = ports_info["backend_port"]
            # Keep existing 'port' field as backend port for backwards compatibility
            results["port"] = ports_info["backend_port"]
        
        if ports_info.get("frontend_port") is not None:
            results["frontend_port"] = ports_info["frontend_port"]
        
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
