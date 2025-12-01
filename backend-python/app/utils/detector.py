import os
import json
import re
import yaml
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
                if folder_lower in ["backend", "server", "api", "app"]:
                    structure["has_backend"] = True
                    structure["backend_path"] = folder_path
                    structure["is_fullstack"] = True
                    print(f"🔍 Fullstack: found backend folder '{folder}'")
                if folder_lower in ["frontend", "client", "web", "ui"]:
                    structure["has_frontend"] = True
                    structure["frontend_path"] = folder_path
                    structure["is_fullstack"] = True
                    print(f"🔍 Fullstack: found frontend folder '{folder}'")
    
    return structure


def _scan_js_for_port_hint(service_path: str, max_files: int = 50) -> Optional[int]:
    """
    Scan JS/TS files under service_path for typical port patterns like:
      - process.env.PORT || 5050
      - app.listen(5050)
    Returns the first reasonable port it finds, or None.
    """
    exts = {".js", ".jsx", ".ts", ".tsx"}
    patterns = [
        # process.env.PORT || 5050
        re.compile(r"process\.env\.PORT\s*\|\|\s*(\d{2,5})"),
        # generic 'PORT ... 5050'
        re.compile(r"\bPORT\b[^;\n]*\b(\d{2,5})\b"),
        # app.listen(5050) / listen(5050)
        re.compile(r"\blist(?:en)?\s*\(\s*(\d{2,5})")
    ]
    
    ports: List[int] = []
    files_scanned = 0
    
    for root, dirs, files in os.walk(service_path):
        dirs[:] = [
            d for d in dirs
            if d not in ["node_modules", "dist", "build", ".next", ".vite", ".git"]
        ]
        
        for file in files:
            if files_scanned >= max_files:
                break
            
            _, ext = os.path.splitext(file)
            if ext.lower() not in exts:
                continue
            
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(10000)
            except Exception:
                files_scanned += 1
                continue
            
            for pat in patterns:
                for m in pat.finditer(content):
                    # last non-None group first
                    for g in reversed(m.groups()):
                        if g and g.isdigit():
                            p = int(g)
                            if 1024 <= p <= 65535:
                                ports.append(p)
                                break
                    if ports:
                        break
                if ports:
                    break
            
            files_scanned += 1
        
        if files_scanned >= max_files:
            break
    
    return ports[0] if ports else None


def _detect_port_from_package_json(project_path: str, prefer_frontend: bool = False) -> Optional[int]:
    """
    Guess port from package.json scripts.
    prefer_frontend:
      - True  => prioritise typical frontend ports
      - False => prioritise typical backend ports
    Also special-cases Vite (frontend) to default to 5173 when no explicit port is set.
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
    # collect dependency names to detect Vite etc.
    deps = {}
    deps.update(data.get("dependencies", {}))
    deps.update(data.get("devDependencies", {}))
    dep_names = set(k.lower() for k in deps.keys())
    
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
    
    # If this looks like a Vite frontend app, default to Vite's dev port 5173
    if prefer_frontend and "vite" in dep_names:
        return 5173
    
    # Default for Node apps when nothing explicit is found
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


def _parse_docker_compose_ports(project_path: str) -> Dict[str, List[Tuple[int, int]]]:
    """
    Parse docker-compose.yml/.yaml using a proper YAML parser (PyYAML).

    Supports:
      services:
        frontend:
          ports:
            - "5173:80"
            - 3000:3000
        backend:
          ports: "5000:5000"
        db:
          ports:
            - "27017:27017"

    Returns:
        {
            "<service_name>": [(host_port, container_port), ...],
            ...
        }
    """
    compose_files = ("docker-compose.yml", "docker-compose.yaml")
    compose_path = None

    for fname in compose_files:
        candidate = os.path.join(project_path, fname)
        if os.path.exists(candidate):
            compose_path = candidate
            break

    # No compose file found
    if not compose_path:
        return {}

    # If PyYAML isn't installed, fall back to "no ports" rather than breaking
    if yaml is None:
        print("Warning: PyYAML not installed; docker-compose ports will not be parsed.")
        return {}

    try:
        with open(compose_path, "r", encoding="utf-8", errors="ignore") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error parsing docker-compose with YAML: {e}")
        return {}

    services = data.get("services", {})
    service_ports: Dict[str, List[Tuple[int, int]]] = {}

    for svc_name, svc_def in services.items():
        if not isinstance(svc_def, dict):
            continue

        ports_field = svc_def.get("ports")
        if not ports_field:
            continue

        # Normalize ports_field to a list
        if isinstance(ports_field, (str, int)):
            ports_list = [ports_field]
        elif isinstance(ports_field, list):
            ports_list = ports_field
        else:
            # Unknown type, skip
            continue

        mappings: List[Tuple[int, int]] = []

        for entry in ports_list:
            # Possible formats:
            # - "3000:3000"
            # - "0.0.0.0:3000:3000"
            # - "3000"
            # - 3000
            host_port: Optional[int] = None
            container_port: Optional[int] = None

            if isinstance(entry, int):
                # `ports: - 3000` means container port 3000, host randomized.
                # We can treat this as (3000, 3000) for our detection purposes,
                # or skip host mapping. Here we treat host == container.
                host_port = entry
                container_port = entry
            else:
                # It's a string
                text = str(entry).strip().strip('"').strip("'")
                # Drop protocol suffix if present, e.g. "3000:3000/tcp"
                if "/" in text:
                    text = text.split("/", 1)[0]

                parts = text.split(":")
                # "3000" => only container port (host random)
                if len(parts) == 1 and parts[0].isdigit():
                    container_port = int(parts[0])
                    # we *could* leave host_port as None; but for your
                    # detector it's more useful to treat host == container
                    host_port = container_port
                elif len(parts) >= 2:
                    # Could be "host:container" or "ip:host:container"
                    # We take last two segments as host/container
                    maybe_host = parts[-2]
                    maybe_container = parts[-1]
                    if maybe_host.isdigit() and maybe_container.isdigit():
                        host_port = int(maybe_host)
                        container_port = int(maybe_container)

            if host_port is not None and container_port is not None:
                mappings.append((host_port, container_port))

        if mappings:
            service_ports[svc_name] = mappings

    return service_ports


def _parse_dockerfile_expose_ports(project_path: str) -> List[int]:
    """
    Collect exposed ports from any Dockerfile found in the project.
    Supports:
      EXPOSE 3000
      EXPOSE 80 443
      EXPOSE 8080/tcp
      EXPOSE 8081/udp
    """
    ports = []
    dockerfiles = ["Dockerfile", "dockerfile"]

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "__pycache__", "dist", "build"]]

        for file in files:
            if file in dockerfiles:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            m = re.search(r"EXPOSE\s+(.*)", line, re.IGNORECASE)
                            if not m:
                                continue

                            tokens = m.group(1).split()
                            for token in tokens:
                                token = token.strip()
                                token = token.split("/")[0]  # drop /tcp
                                if token.isdigit():
                                    ports.append(int(token))
                except:
                    pass

    return sorted(set(ports))


def _classify_docker_service(name: str) -> str:
    """
    Classify a docker-compose service name into one of:
    'frontend', 'backend', 'database', or 'other'.
    """
    n = name.lower()

    if any(k in n for k in ["front", "client", "web", "ui"]):
        return "frontend"
    if any(k in n for k in ["back", "api", "server", "app"]):
        return "backend"
    if any(k in n for k in ["mongo", "mysql", "postgres", "pgsql", "redis", "db"]):
        return "database"
    return "other"


def detect_ports_for_project(
    project_path: str,
    language: str,
    framework: str,
    base_port: Optional[int]
) -> Dict[str, Optional[int]]:
    """
    Detect backend and frontend ports.

    - For JS/TS: look for fullstack structure and read package.json,
      then refine backend with a JS code scan.
      Also consult .env for port hints (root and, for fullstack, backend/frontend subfolders).
    - For others: scan code for host:port; fall back to base_port / defaults,
      with .env overrides.

    Additionally:
    - Parse docker-compose.yml/.yaml and expose:
        docker_backend_ports             (HOST ports on the machine)
        docker_frontend_ports            (HOST ports on the machine)
        docker_database_ports            (HOST ports on the machine)
        docker_other_ports               (service_name -> [HOST ports])
        docker_backend_container_ports   (CONTAINER ports inside backend containers)
        docker_frontend_container_ports  (CONTAINER ports inside frontend containers)
        docker_database_container_ports  (CONTAINER ports inside DB containers)
        docker_other_container_ports     (service_name -> [CONTAINER ports])
    - Parse Dockerfile EXPOSE lines to collect container ports in docker_expose_ports.
    """
    backend_port: Optional[int] = None
    frontend_port: Optional[int] = None

    # ---- read env key/values at the project root ----
    root_env_kv = _read_env_key_values(project_path)

    def _extract_port(val: str) -> Optional[int]:
        val = val.strip()
        if not val:
            return None
        if val.isdigit():
            p = int(val)
            if 1 <= p <= 65535:
                return p
        m = re.search(r"(\d{2,5})", val)
        if m:
            try:
                p = int(m.group(1))
                if 1 <= p <= 65535:
                    return p
            except ValueError:
                return None
        return None

    def _extract_env_ports(env_kv: Dict[str, str]):
        """
        Given a mapping of env key -> value, extract:
          - backend_env_port: from BACKEND_PORT/SERVER_PORT/API_PORT
          - frontend_env_port: from FRONTEND_PORT/CLIENT_PORT/VITE_PORT/REACT_APP_PORT
          - generic_env_port: from PORT
        """
        backend_env_port: Optional[int] = None
        frontend_env_port: Optional[int] = None
        generic_env_port: Optional[int] = None

        for key, value in env_kv.items():
            p = _extract_port(value)
            if p is None:
                continue
            ku = key.upper()

            # explicit backend hints
            if ku in ("BACKEND_PORT", "SERVER_PORT", "API_PORT"):
                if backend_env_port is None:
                    backend_env_port = p
                continue

            # explicit frontend hints
            if ku in ("FRONTEND_PORT", "CLIENT_PORT", "VITE_PORT", "REACT_APP_PORT"):
                if frontend_env_port is None:
                    frontend_env_port = p
                continue

            # generic PORT
            if ku == "PORT" and generic_env_port is None:
                generic_env_port = p

        return backend_env_port, frontend_env_port, generic_env_port

    # root env-derived ports (may be overridden for fullstack)
    backend_env_port, frontend_env_port, generic_env_port = _extract_env_ports(root_env_kv)

    is_js_ts = language in ["JavaScript", "TypeScript"]

    if is_js_ts:
        fullstack = _detect_fullstack_structure(project_path)
        is_fullstack = fullstack.get("is_fullstack", False)

        # ---- FULLSTACK JS/TS (client + server folders) ----
        if is_fullstack:
            backend_path = fullstack.get("backend_path")
            frontend_path = fullstack.get("frontend_path")

            # Backend-specific env: backend/.env overrides root .env
            if backend_path:
                backend_env_kv = _read_env_key_values(backend_path)
                b_backend_env_port, _, b_generic_env_port = _extract_env_ports(backend_env_kv)

                if b_backend_env_port is not None:
                    backend_env_port = b_backend_env_port
                if b_generic_env_port is not None:
                    # generic PORT from backend/.env overrides root generic PORT
                    generic_env_port = b_generic_env_port

            # Frontend-specific env: frontend/.env overrides root .env
            if frontend_path:
                frontend_env_kv = _read_env_key_values(frontend_path)
                _, f_frontend_env_port, _ = _extract_env_ports(frontend_env_kv)

                if f_frontend_env_port is not None:
                    frontend_env_port = f_frontend_env_port
                # We intentionally do NOT use generic PORT for frontend in fullstack,
                # to keep the original semantics.

            # Backend: env override > package.json + code scan > generic PORT
            if backend_env_port is not None:
                backend_port = backend_env_port
            else:
                if fullstack.get("has_backend") and backend_path:
                    backend_port = _detect_port_from_package_json(
                        backend_path, prefer_frontend=False
                    )
                    code_port = _scan_js_for_port_hint(backend_path)
                    if code_port is not None:
                        backend_port = code_port
                else:
                    backend_port = _detect_port_from_package_json(
                        project_path, prefer_frontend=False
                    )
                    code_port = _scan_js_for_port_hint(project_path)
                    if code_port is not None:
                        backend_port = code_port

                if backend_port is None and generic_env_port is not None:
                    backend_port = generic_env_port

            # Frontend: env override > package.json (frontend preference)
            if fullstack.get("has_frontend") and frontend_path:
                if frontend_env_port is not None:
                    frontend_port = frontend_env_port
                else:
                    frontend_port = _detect_port_from_package_json(
                        frontend_path, prefer_frontend=True
                    )
            # we do NOT use generic PORT for frontend in fullstack case

        # ---- SINGLE JS/TS PROJECT (no separate client/server folders) ----
        else:
            # treat React / Next.js as frontend-only by default
            is_frontend_only = framework in ["React", "Next.js"]

            if is_frontend_only:
                # FRONTEND: env > generic PORT > package.json + JS scan
                if frontend_env_port is not None:
                    frontend_port = frontend_env_port
                elif generic_env_port is not None:
                    frontend_port = generic_env_port
                else:
                    frontend_port = _detect_port_from_package_json(
                        project_path, prefer_frontend=True
                    )
                    code_port = _scan_js_for_port_hint(project_path)
                    if code_port is not None:
                        frontend_port = code_port

                # BACKEND: only if explicitly defined in env
                if backend_env_port is not None:
                    backend_port = backend_env_port
                else:
                    backend_port = None

            else:
                # Non-React/Next single JS/TS: treat as backend app
                # Backend: env > package.json + JS scan > generic PORT
                if backend_env_port is not None:
                    backend_port = backend_env_port
                else:
                    backend_port = _detect_port_from_package_json(
                        project_path, prefer_frontend=False
                    )
                    code_port = _scan_js_for_port_hint(project_path)
                    if code_port is not None:
                        backend_port = code_port

                    if backend_port is None and generic_env_port is not None:
                        backend_port = generic_env_port

                # Frontend only if explicitly given in env
                if frontend_env_port is not None:
                    frontend_port = frontend_env_port

    else:
        # ---- NON JS/TS PROJECTS ----
        detected = _scan_code_for_ports(project_path)
        if detected:
            backend_port = detected
        else:
            backend_port = base_port
            if backend_port is None:
                default_ports = {
                    "Python": 8000,
                    "Java": 8080,
                    "Go": 8080,
                    "Ruby": 3000,
                    "PHP": 8000
                }
                backend_port = default_ports.get(language, 8000)

        # Env overrides for backend
        if backend_env_port is not None:
            backend_port = backend_env_port
        elif generic_env_port is not None and backend_port is None:
            backend_port = generic_env_port

        # Allow explicit frontend env even in non-JS projects (edge multi-service)
        if frontend_env_port is not None:
            frontend_port = frontend_env_port

    # ---- Docker-compose ports ----
    docker_service_ports = _parse_docker_compose_ports(project_path)

    # ---- Dockerfile EXPOSE ports ----
    dockerfile_exposed_ports = _parse_dockerfile_expose_ports(project_path)

    docker_backend_ports: List[int] = []
    docker_frontend_ports: List[int] = []
    docker_database_ports: List[int] = []
    docker_other_ports: Dict[str, List[int]] = {}

    # Container (internal) ports for the same services
    docker_backend_container_ports: List[int] = []
    docker_frontend_container_ports: List[int] = []
    docker_database_container_ports: List[int] = []
    docker_other_container_ports: Dict[str, List[int]] = {}

    for svc, mappings in docker_service_ports.items():
        role = _classify_docker_service(svc)
        host_ports = [hp for (hp, cp) in mappings]
        container_ports = [cp for (hp, cp) in mappings]

        if not host_ports and not container_ports:
            continue

        if role == "backend":
            docker_backend_ports.extend(host_ports)
            docker_backend_container_ports.extend(container_ports)
            # OLD behavior was: if backend_port is None and host_ports: backend_port = host_ports[0]
            # We now defer the canonical override until after all services are processed.
        elif role == "frontend":
            docker_frontend_ports.extend(host_ports)
            docker_frontend_container_ports.extend(container_ports)
        elif role == "database":
            docker_database_ports.extend(host_ports)
            docker_database_container_ports.extend(container_ports)
        else:
            if host_ports:
                docker_other_ports[svc] = host_ports
            if container_ports:
                docker_other_container_ports[svc] = container_ports

    # de-duplicate docker port lists
    docker_backend_ports = sorted(set(docker_backend_ports))
    docker_frontend_ports = sorted(set(docker_frontend_ports))
    docker_database_ports = sorted(set(docker_database_ports))

    docker_backend_container_ports = sorted(set(docker_backend_container_ports))
    docker_frontend_container_ports = sorted(set(docker_frontend_container_ports))
    docker_database_container_ports = sorted(set(docker_database_container_ports))

    # --- Compose-driven hints (conservative) ---
    # Only use compose HOST ports if we did not find a better hint earlier.
    if backend_port is None and docker_backend_ports:
        backend_port = docker_backend_ports[0]

    if frontend_port is None and docker_frontend_ports:
        frontend_port = docker_frontend_ports[0]

    return {
        "backend_port": backend_port,
        "frontend_port": frontend_port,

        # HOST ports from docker-compose (what you bind on the machine)
        "docker_backend_ports": docker_backend_ports or None,
        "docker_frontend_ports": docker_frontend_ports or None,
        "docker_database_ports": docker_database_ports or None,
        "docker_other_ports": docker_other_ports or None,

        # CONTAINER ports from docker-compose (internal container-side ports)
        "docker_backend_container_ports": docker_backend_container_ports or None,
        "docker_frontend_container_ports": docker_frontend_container_ports or None,
        "docker_database_container_ports": docker_database_container_ports or None,
        "docker_other_container_ports": docker_other_container_ports or None,

        # Container ports from Dockerfile EXPOSE lines
        "docker_expose_ports": dockerfile_exposed_ports or None,
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
    - env var keys (including nested backend/frontend .env files)
    - docker-compose images
    Also tries to infer a database port.
    """
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
        
        # Runtime defaults (may include default port)
        runtime_info = get_runtime_info(results["language"], results["framework"])
        results.update(runtime_info)
        
        # Dependencies (root + nested subprojects like client/server)
        dep_files = {
            "requirements.txt": "requirements.txt",
            "package.json": "package.json",
            "pom.xml": "pom.xml",
            "go.mod": "go.mod"
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
