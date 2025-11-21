import os
import json
import re
from typing import Dict, List, Tuple
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
                dependencies = [
                    line.split()[0] for line in content.split('\n')
                    if line.strip() and not line.startswith('module') and not line.startswith('go')
                ]
    
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
            "runtime": "php:8.2-apache",
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
    """Detect environment variables from .env files"""
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
    
    framework_scores = {}
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
    
    for framework, score in framework_scores.items():
        if score > best_score:
            best_score = score
            best_framework = framework
    
    confidence = min(best_score / 2.0, 1.0)
    
    if best_score > 0:
        print(f"   Heuristic Framework: {best_framework} (score: {best_score:.2f})")
    
    return best_framework, confidence


def detect_framework(project_path: str, use_ml: bool = True) -> Dict:
    """Hybrid detection: Heuristics first, ML as supplement"""
    
    print(f"\nStarting Hybrid Framework Detection")
    print(f"Project Path: {project_path}")
    print(f"ML Mode: {'Enabled' if use_ml else 'Disabled'}\n")
    
    actual_path = find_project_root(project_path, max_depth=3)
    
    results = {
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
        }
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
                    results["detection_confidence"]["method"] = "hybrid (ML framework)"
            
            except Exception as e:
                print(f"ML analysis failed, continuing with heuristic: {e}")
        
        runtime_info = get_runtime_info(results["language"], results["framework"])
        results.update(runtime_info)
        
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
        
        docker_info = detect_docker_files(actual_path)
        results["dockerfile"] = docker_info["dockerfile"]
        results["docker_compose"] = docker_info["docker_compose"]
        results["detected_files"].extend(docker_info["detected_files"])
        
        env_vars = detect_env_variables(actual_path)
        if env_vars:
            results["env_variables"] = env_vars
        
        results["detected_files"] = list(set(results["detected_files"]))
        
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