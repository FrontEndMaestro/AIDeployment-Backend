import os
import json
import re
import yaml
from collections import Counter
from typing import Dict, List, Tuple, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None
from .ml_analyzer import get_ml_analyzer
from .command_extractor import (
    extract_nodejs_commands, 
    extract_python_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info
)


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


def _languages_compatible(detected: str, expected: str) -> bool:
    """
    Treat JavaScript and TypeScript as compatible for JS ecosystem frameworks
    (e.g., React/Next/Express) so valid framework detections aren't erased.
    """
    if detected == expected:
        return True
    js_like = {"JavaScript", "TypeScript"}
    return detected in js_like and expected in js_like


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

DB_ENV_KEYWORDS = {
    "PostgreSQL": ["postgres", "postgresql", "pg"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongo", "mongodb"],
    "Redis": ["redis"],
    "SQLite": ["sqlite"],
}


# --- Service classification dep sets (Fix 1 / Fix 4) ---
BACKEND_DEPS = {
    "express", "fastify", "koa", "hapi", "@nestjs/core",
    "apollo-server", "graphql-yoga", "@hapi/hapi",
}

FRONTEND_DEPS = {
    "react", "vue", "svelte", "next", "nuxt", "vite",
    "react-scripts", "react-dom", "@vitejs/plugin-react",
    "@vue/cli-service", "gatsby", "@sveltejs/kit",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".next", "coverage", "test", "tests", ".cache",
}

PYTHON_BACKEND_DEPS = {
    "fastapi", "flask", "django", "starlette", "tornado", "aiohttp", "sanic",
}

DB_KEYWORDS = {
    "postgres", "postgresql", "mysql", "mongo", "mongodb", "redis",
    "elasticsearch", "cassandra", "sqlite", "db", "database",
}

PYTHON_SKIP_DIRS = SKIP_DIRS | {"venv", ".venv", "env"}


def norm_path(p: str) -> str:
    """Normalise a path: backslashes → forward, strip trailing slashes, empty → '.'."""
    if not p:
        return "."
    p = p.replace("\\", "/").rstrip("/")
    return p if p else "."


def _normalize_dep_name(dep: str) -> str:
    """Best-effort normalize a dependency spec into a package name."""
    dep = (dep or "").strip()
    if not dep:
        return ""

    # Drop environment markers and direct references
    dep = dep.split(";", 1)[0].strip()
    dep = dep.split("@", 1)[0].strip()

    # Strip extras (e.g., fastapi[standard])
    dep = dep.split("[", 1)[0].strip()

    # Strip version / comparator noise
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "="):
        if sep in dep:
            dep = dep.split(sep, 1)[0].strip()
            break

    # Some formats include whitespace (e.g., "pkg >= 1.0")
    dep = dep.split(None, 1)[0].strip()
    return dep


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

        elif file_type == "pyproject.toml":
            deps: List[str] = []
            if tomllib is not None:
                with open(file_path, "rb") as f:
                    data = tomllib.load(f) or {}

                # PEP 621 dependencies (list of strings)
                project = data.get("project") or {}
                for dep in project.get("dependencies") or []:
                    name = _normalize_dep_name(dep)
                    if name:
                        deps.append(name)

                opt = project.get("optional-dependencies") or {}
                if isinstance(opt, dict):
                    for group_deps in opt.values():
                        if isinstance(group_deps, list):
                            for dep in group_deps:
                                name = _normalize_dep_name(dep)
                                if name:
                                    deps.append(name)

                # Poetry dependencies (tables)
                poetry = (data.get("tool") or {}).get("poetry") or {}
                poetry_deps = poetry.get("dependencies") or {}
                if isinstance(poetry_deps, dict):
                    deps.extend([k for k in poetry_deps.keys() if k.lower() != "python"])

                group = poetry.get("group") or {}
                if isinstance(group, dict):
                    for grp in group.values():
                        if isinstance(grp, dict):
                            grp_deps = grp.get("dependencies") or {}
                            if isinstance(grp_deps, dict):
                                deps.extend([k for k in grp_deps.keys() if k.lower() != "python"])
            dependencies = deps

        elif file_type == "Pipfile":
            deps: List[str] = []
            if tomllib is not None:
                with open(file_path, "rb") as f:
                    data = tomllib.load(f) or {}
                for section_name in ("packages", "dev-packages"):
                    section = data.get(section_name) or {}
                    if isinstance(section, dict):
                        deps.extend(list(section.keys()))
            dependencies = deps

        elif file_type == "poetry.lock":
            deps: List[str] = []
            if tomllib is not None:
                with open(file_path, "rb") as f:
                    data = tomllib.load(f) or {}
                pkgs = data.get("package") or []
                if isinstance(pkgs, list):
                    for pkg in pkgs:
                        if isinstance(pkg, dict):
                            name = pkg.get("name")
                            if name:
                                deps.append(str(name))
            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                deps.extend(re.findall(r'(?m)^name\\s*=\\s*\"([^\"]+)\"\\s*$', content))
            dependencies = deps

        elif file_type == "composer.json":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f) or {}
            deps = {**data.get("require", {}), **data.get("require-dev", {})}
            dependencies = list(deps.keys())

        elif file_type == "Cargo.toml":
            deps: List[str] = []
            if tomllib is not None:
                with open(file_path, "rb") as f:
                    data = tomllib.load(f) or {}
                for section_name in ("dependencies", "dev-dependencies", "build-dependencies"):
                    section = data.get(section_name) or {}
                    if isinstance(section, dict):
                        deps.extend(list(section.keys()))
            dependencies = deps
    
    except Exception as e:
        print(f"Error parsing {file_type}: {e}")
    
    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for d in dependencies:
        if not d:
            continue
        if d in seen:
            continue
        seen.add(d)
        deduped.append(d)

    return deduped[:50]


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
        if fw_lang and language != "Unknown" and not _languages_compatible(language, fw_lang):
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


def _infer_service_type(service_path: str, service_name: str, project_root: str) -> str:
    """
    Classify a service by reading its package.json deps first (Fix 4).
    Fix 6b: DB keyword names → 'other' immediately.
    Falls back to name heuristic only if no package.json found.
    """
    pkg_path = os.path.join(project_root, service_path, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            is_be = bool(deps.keys() & BACKEND_DEPS)
            is_fe = bool(deps.keys() & FRONTEND_DEPS)
            if is_be and is_fe:
                return "monolith"
            if is_be:
                return "backend"
            if is_fe:
                return "frontend"
        except Exception:
            pass

    # Fix 6b: DB-named services → other (before any backend/frontend guess)
    name_lower = service_name.lower()
    if name_lower in DB_KEYWORDS:
        return "other"

    # Fallback to name heuristic only if no package.json found
    if any(k in name_lower for k in ["backend", "server", "api", "worker"]):
        return "backend"
    if any(k in name_lower for k in ["frontend", "client", "ui", "web", "app"]):
        return "frontend"
    return "other"


def _find_all_services_by_deps(project_path: str) -> List[Dict[str, str]]:
    """
    Fix 1: Walk all subdirs (excluding SKIP_DIRS), find every package.json,
    and classify each service by deps against BACKEND_DEPS / FRONTEND_DEPS.
    Fix 6a: Skips type=other stubs entirely.
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
        is_be = bool(deps.keys() & BACKEND_DEPS)
        is_fe = bool(deps.keys() & FRONTEND_DEPS)

        if is_be and is_fe:
            svc_type = "monolith"
        elif is_be:
            svc_type = "backend"
        elif is_fe:
            svc_type = "frontend"
        else:
            continue  # Fix 6a: neither backend nor frontend deps — skip (type=other)

        folder_name = os.path.basename(root) or os.path.basename(project_path)
        services.append({
            "name": folder_name,
            "abs_path": root,
            "type": svc_type,
        })
        print(f"📦 Dep-scan: found {svc_type} service '{folder_name}' at {root}")

    return services


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
    4. Phantom root — root is frontend/other/untyped + ≥2 real non-root → drop root
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

    # Step 2: Root monolith → suppress all non-database children
    if root_type == "monolith":
        db_children = [s for s in non_root if s.get("type") == "database"]
        return root_svcs + db_children

    # Step 3: Root backend → keep everything (root + children are separate services)
    if root_type == "backend":
        return services

    # Step 4: Root is frontend/other/untyped + ≥2 real non-root → drop root
    if root_type in ("frontend", "other") or root_type is None:
        real_non_root = [
            s for s in non_root
            if s.get("type") not in ("database", "other")
        ]
        if len(real_non_root) >= 2:
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
        if stype in ("database", "other"):
            survivors.append(s)
            continue
        if s.get("port") or s.get("entry_point"):
            survivors.append(s)
            continue
        print(f"Dropping empty shell: {s.get('name')} (no port, no entry_point)")
    return survivors



def _normalize_service_path(project_path: str, service_path: str) -> str:
    rel = os.path.relpath(service_path, project_path)
    rel = "." if rel in [".", ""] else rel.replace("\\", "/")
    if rel != "." and not rel.endswith("/"):
        rel += "/"
    return rel


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
            continue

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
                        for line in f:
                            line = line.strip()
                            if line.startswith("PORT="):
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
    metadata: Dict
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

    # ── Fix 1: Dep-based service discovery (Node.js) ──────────────────
    node_stubs = _find_all_services_by_deps(project_path)

    # ── Fix 7: Python backend discovery ───────────────────────────────
    python_stubs = _find_python_services(project_path)

    # ── Merge + deduplicate (Python preferred if it has framework) ─────
    raw_stubs = _merge_node_python_stubs(node_stubs, python_stubs)
    
    # ── Fix 3/5: Suppress root phantom if children found ──────────────
    raw_stubs = _suppress_root_if_children_found(raw_stubs, project_path)

    # ── Populate per-service fields ───────────────────────────────────
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
            # ── Python stubs already have fields populated by _find_python_services ──
            if stub.get("language") == "Python":
                svc_dict = {
                    "name": svc_name,
                    "path": svc_rel_path,
                    "type": svc_type,
                    "language": "Python",
                    "framework": stub.get("framework"),
                    "port": stub.get("port", 8000),
                    "port_source": stub.get("port_source", "default"),
                    "entry_point": stub.get("entry_point"),
                    "env_file": env_file,
                    "package_manager": stub.get("package_manager", "pip"),
                    "dockerfile_strategy": "python_backend",
                }
                services.append(svc_dict)
                print(f"🐍 Python service '{svc_name}': framework={stub.get('framework')}, port={stub.get('port')}")
                continue

            # ── Node.js backend/monolith ───────────────────────────────
            # Extract port from service directory
            port_info = extract_port_from_project(svc_abs_path, framework, language)
            port = port_info.get("port", 3000)

            # Extract start command from service's package.json
            cmds = extract_nodejs_commands(svc_abs_path)
            entry_point = cmds.get("entry_point", "index.js")
            start_command = cmds.get("start_command", f"node {entry_point}")
            print(f"📦 {svc_type.title()} service '{svc_name}': entry_point={entry_point}, start_command={start_command}")

            svc_dict = {
                "name": svc_name,
                "path": svc_rel_path,
                "type": svc_type,
                "port": port,
                "port_source": port_info.get("source", "default"),
                "entry_point": entry_point,
                "start_command": start_command,
                "env_file": env_file,
                "package_manager": _detect_package_manager(svc_abs_path),
            }

            # ── Fix 2: Monolith gets extra fields ─────────────────
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
            fe_port = fe_port_info.get("port", 5173)
            print(f"📦 Frontend service '{svc_name}': build_output={build_output}, port={fe_port}")

            services.append({
                "name": svc_name,
                "path": svc_rel_path,
                "type": "frontend",
                "build_output": build_output,
                "port": fe_port,
                "port_source": fe_port_info.get("source", "default"),
                "env_file": env_file,
                "package_manager": _detect_package_manager(svc_abs_path),
            })

    # ── Fix 5 Step 1: Drop empty shells post-population ────────────────
    services = _drop_empty_shells(services)

    # ── Fallback: if dep-scan found nothing, use legacy single-service logic ──
    if not services:
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
        explicit_port = port_info.get("source") in ("env", "source")

        if not (has_manifest or entry_point or explicit_port):
            return []

        if static_only:
            single_cmds = extract_nodejs_commands(project_path)
            single_build_output = single_cmds.get("build_output", "dist")
            services.append({
                "name": "frontend",
                "path": ".",
                "type": "frontend",
                "build_output": single_build_output,
                "env_file": root_env_file,
            })
        else:
            svc_name = "frontend" if framework in ["React", "Next.js"] else "app"
            svc_type = "frontend" if framework in ["React", "Next.js"] else "backend"
            if svc_type == "frontend":
                single_cmds = extract_nodejs_commands(project_path)
                single_build_output = single_cmds.get("build_output", "dist")
                services.append({
                    "name": svc_name,
                    "path": ".",
                    "type": svc_type,
                    "build_output": single_build_output,
                    "env_file": root_env_file,
                })
            else:
                services.append({
                    "name": svc_name,
                    "path": ".",
                    "type": svc_type,
                    "env_file": root_env_file,
                })

    # ── Fix 2: Set architecture metadata ──────────────────────────────
    if has_monolith:
        metadata["architecture"] = "monolith"
    else:
        metadata.setdefault("architecture", "multi-service")

    # ── Compose hints (optional refinement) ───────────────────────────
    compose_path = None
    for fname in ("docker-compose.yml", "docker-compose.yaml"):
        candidate = os.path.join(project_path, fname)
        if os.path.exists(candidate):
            compose_path = candidate
            break

    if compose_path and yaml is not None:
        try:
            with open(compose_path, "r", encoding="utf-8", errors="ignore") as f:
                compose_data = yaml.safe_load(f) or {}
            compose_services = compose_data.get("services") or {}

            for svc_name, svc_def in compose_services.items():
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

                # Try to match by path
                matched = False
                for svc in services:
                    if svc.get("path") == rel_ctx:
                        svc["name"] = svc_name  # align name to compose
                        svc.setdefault("type", svc_type)
                        matched = True
                        break

                if matched:
                    continue

                # Match by name
                for svc in services:
                    if svc.get("name") == svc_name:
                        svc["path"] = rel_ctx
                        svc.setdefault("type", svc_type)
                        matched = True
                        break

                if not matched:
                    services.append({
                        "name": svc_name,
                        "path": rel_ctx,
                        "type": svc_type,
                    })
        except Exception:
            pass

    # Root monolith can coexist with compose hints that add child build contexts.
    # If a root monolith exists, suppress non-database subdirectory services to avoid duplication.
    if any(s.get("path") == "." and s.get("type") == "monolith" for s in services):
        services = [
            s for s in services
            if s.get("path") == "." or s.get("type") == "database"
        ]

    # ── Database service detection (smart cloud vs local) ─────────────
    backend_path = None
    for svc in services:
        if svc.get("type") in ("backend", "monolith"):
            backend_path = os.path.join(project_path, svc.get("path", "."))
            break

    if not backend_path:
        return services

    db_info = extract_database_info(backend_path, metadata.get("database"))

    if db_info.get("db_type"):
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

    return services


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

    if any(k in n for k in ["front", "client", "web", "ui","public"]):
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
                elif b_generic_env_port is not None:
                    # FIX: In fullstack project, treat backend/.env PORT as backend port
                    # (not just generic fallback). This ensures PORT=4000 from backend/.env
                    # takes priority over package.json default of 3000.
                    backend_env_port = b_generic_env_port

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
