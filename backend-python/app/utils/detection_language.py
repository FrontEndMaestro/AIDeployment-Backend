"""
Language detection, framework detection, and dependency parsing.
Extracted from detector.py to reduce its size.
"""

import os
import json
import re
from typing import Dict, List, Tuple

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from .detection_constants import (
    LANGUAGE_INDICATORS,
    FRAMEWORK_INDICATORS,
    FRAMEWORK_LANGUAGES,
    _languages_compatible,
    _normalize_dep_name,
)


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
