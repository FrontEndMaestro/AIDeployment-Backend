import os
import subprocess
import re
import glob
import json
from typing import Dict, List
from .file_system import write_file


DOCKERFILE_TEMPLATES = {
    "Python": {
        "base": "python:3.11-slim",
        "key_files": ["requirements.txt", "setup.py", "pyproject.toml"],
    },
    "JavaScript": {
        "base": "node:20-alpine",
        "key_files": ["package.json"],
    },
    "TypeScript": {
        "base": "node:20-alpine",
        "key_files": ["package.json", "tsconfig.json"],
    },
    "Java": {
        "base": "openjdk:17-slim",
        "key_files": ["pom.xml", "build.gradle"],
    },
    "Go": {
        "base": "golang:1.21-alpine",
        "key_files": ["go.mod"],
    },
    "Ruby": {
        "base": "ruby:3.2-alpine",
        "key_files": ["Gemfile"],
    },
    "PHP": {
        "base": "php:8.2-apache",
        "key_files": ["composer.json"],
    }
}


def detect_mern_structure(project_path: str) -> Dict:
    """Detect MERN/fullstack structure"""
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
            
            if folder_lower in ['backend', 'server', 'api'] and os.path.exists(os.path.join(folder_path, 'package.json')):
                structure["has_backend"] = True
                structure["backend_path"] = folder_path
                structure["is_fullstack"] = True
                print(f"🔍 Found backend: {folder}")
            
            if folder_lower in ['frontend', 'client', 'web'] and os.path.exists(os.path.join(folder_path, 'package.json')):
                structure["has_frontend"] = True
                structure["frontend_path"] = folder_path
                structure["is_fullstack"] = True
                print(f"🔍 Found frontend: {folder}")
    
    return structure


def find_key_files_location(project_path: str, key_files: List[str]) -> Dict:
    """Find project files with fullstack detection"""
    
    mern_check = detect_mern_structure(project_path)
    
    if mern_check["is_fullstack"] and mern_check["has_backend"]:
        print(f"📦 Fullstack app detected - deploying backend")
        return {
            "found": True,
            "path": mern_check["backend_path"],
            "subfolder": os.path.relpath(mern_check["backend_path"], project_path),
            "is_fullstack": True
        }
    
    for key_file in key_files:
        if '*' in key_file:
            if glob.glob(os.path.join(project_path, key_file)):
                return {"found": True, "path": project_path, "subfolder": None, "is_fullstack": False}
        elif os.path.exists(os.path.join(project_path, key_file)):
            return {"found": True, "path": project_path, "subfolder": None, "is_fullstack": False}
    
    print(f"⚠️ Searching subfolders...")
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in [
            'node_modules', '__pycache__', '.git', 'venv', '.venv', 'env',
            'dist', 'build', '.next', 'target', 'bin', 'obj', 'out',
            'coverage', '.pytest_cache'
        ]]
        
        depth = root.replace(project_path, '').count(os.sep)
        if depth > 3:
            continue
        
        for key_file in key_files:
            if '*' in key_file:
                if glob.glob(os.path.join(root, key_file)):
                    subfolder = os.path.relpath(root, project_path)
                    print(f"📁 Found: {subfolder}")
                    return {"found": True, "path": root, "subfolder": subfolder, "is_fullstack": False}
            elif key_file in files:
                subfolder = os.path.relpath(root, project_path)
                print(f"📁 Found: {subfolder}")
                return {"found": True, "path": root, "subfolder": subfolder, "is_fullstack": False}
    
    return {"found": False, "path": project_path, "subfolder": None, "is_fullstack": False}


def detect_port(project_path: str, language: str) -> int:
    """Auto-detect port"""
    
    if language in ["JavaScript", "TypeScript"]:
        pkg_json = os.path.join(project_path, 'package.json')
        if os.path.exists(pkg_json):
            try:
                with open(pkg_json, 'r') as f:
                    data = json.load(f)
                    
                    scripts = data.get('scripts', {})
                    start = str(scripts.get('start', ''))
                    dev = str(scripts.get('dev', ''))
                    
                    for script in [start, dev]:
                        if '5000' in script:
                            return 5000
                        if '4000' in script:
                            return 4000
                        if '8080' in script:
                            return 8080
                    
                    return 3000
            except:
                pass
        return 3000
    
    elif language == "Python":
        return 8000
    elif language == "Java":
        return 8080
    elif language == "Go":
        return 8080
    elif language == "Ruby":
        return 3000
    elif language == "PHP":
        return 8000
    
    return 8000


def generate_nodejs_dockerfile(project_path: str, port: int) -> str:
    """Generate Node.js Dockerfile"""
    
    # Detect entry point
    entry_files = ['index.js', 'server.js', 'app.js', 'main.js', 'src/index.js', 'src/server.js']
    entry_point = 'index.js'
    
    for entry in entry_files:
        if os.path.exists(os.path.join(project_path, entry)):
            entry_point = entry
            break
    
    # Check for start script
    has_start = False
    pkg_json = os.path.join(project_path, 'package.json')
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json, 'r') as f:
                data = json.load(f)
                has_start = 'start' in data.get('scripts', {})
        except:
            pass
    
    start_cmd = 'npm start' if has_start else f'node {entry_point}'
    
    dockerfile = f"""FROM node:20-alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

ENV NODE_ENV=production
ENV PORT={port}

EXPOSE {port}

CMD {start_cmd}
"""
    return dockerfile


def generate_python_dockerfile(project_path: str, port: int) -> str:
    """Generate Python Dockerfile"""
    
    # Detect if needs PostgreSQL
    needs_pg = False
    req_file = os.path.join(project_path, 'requirements.txt')
    if os.path.exists(req_file):
        with open(req_file, 'r') as f:
            content = f.read().lower()
            needs_pg = 'psycopg2' in content
    
    pg_deps = ""
    if needs_pg:
        pg_deps = "\nRUN apt-get update && apt-get install -y gcc postgresql-client libpq-dev && rm -rf /var/lib/apt/lists/*\n"
    
    # Detect entry point
    entry_files = ['app.py', 'main.py', 'server.py', 'manage.py']
    entry_point = 'app.py'
    
    for entry in entry_files:
        if os.path.exists(os.path.join(project_path, entry)):
            entry_point = entry
            break
    
    # Check for Flask/Django
    is_flask = os.path.exists(os.path.join(project_path, 'app.py'))
    is_django = os.path.exists(os.path.join(project_path, 'manage.py'))
    
    if is_django:
        cmd = 'python manage.py runserver 0.0.0.0:8000'
    elif is_flask:
        cmd = 'python app.py'
    else:
        cmd = f'python {entry_point}'
    
    dockerfile = f"""FROM python:3.11-slim

WORKDIR /app
{pg_deps}
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT={port}

EXPOSE {port}

CMD {cmd}
"""
    return dockerfile


def generate_dockerfile_universal(language: str, project_path: str, port: int) -> str:
    """Universal Dockerfile generator"""
    
    if language in ["JavaScript", "TypeScript"]:
        return generate_nodejs_dockerfile(project_path, port)
    
    elif language == "Python":
        return generate_python_dockerfile(project_path, port)
    
    elif language == "Java":
        return f"""FROM openjdk:17-slim

WORKDIR /app

COPY pom.xml .
COPY src ./src

RUN apt-get update && apt-get install -y maven && \\
    mvn clean package -DskipTests && \\
    apt-get remove -y maven && apt-get autoremove -y

EXPOSE {port}

CMD ["java", "-jar", "target/*.jar"]
"""
    
    elif language == "Go":
        return f"""FROM golang:1.21-alpine

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN go build -o main .

EXPOSE {port}

CMD ["./main"]
"""
    
    elif language == "Ruby":
        return f"""FROM ruby:3.2-alpine

WORKDIR /app

COPY Gemfile Gemfile.lock ./
RUN bundle install

COPY . .

EXPOSE {port}

CMD ["ruby", "app.rb"]
"""
    
    elif language == "PHP":
        return f"""FROM php:8.2-apache

WORKDIR /var/www/html

COPY . .

RUN docker-php-ext-install pdo pdo_mysql

EXPOSE {port}

CMD ["apache2-foreground"]
"""
    
    else:
        return generate_nodejs_dockerfile(project_path, port)


def build_docker_image(
    project_path: str,
    image_tag: str,
    language: str = "Python",
    port: int = 8000,
    start_command: str = None,
    build_command: str = None,
    max_retries: int = 3
) -> Dict:
    """Universal Docker builder"""
    
    try:
        print(f"🐳 Building: {image_tag}")
        print(f"📂 Path: {project_path}")
        print(f"🔤 Language: {language}")
        
        template = DOCKERFILE_TEMPLATES.get(language, DOCKERFILE_TEMPLATES["JavaScript"])
        key_files = template["key_files"]
        
        location = find_key_files_location(project_path, key_files)
        
        if not location["found"]:
            return {
                "success": False,
                "message": f"Could not find required files: {', '.join(key_files)}"
            }
        
        actual_project_path = location["path"]
        print(f"✅ Project root: {actual_project_path}")
        
        # Auto-detect port
        detected_port = detect_port(actual_project_path, language)
        print(f"🔌 Detected port: {detected_port}")
        
        dockerfile_path = os.path.join(actual_project_path, "Dockerfile")
        
        print(f"📝 Generating Dockerfile...")
        content = generate_dockerfile_universal(language, actual_project_path, detected_port)
        write_file(dockerfile_path, content)
        
        dockerignore = "node_modules\n__pycache__\n.git\n.env\nvenv\ndist\nbuild\ntarget\n.next\n*.log\n"
        write_file(os.path.join(actual_project_path, ".dockerignore"), dockerignore)
        
        # Build
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            
            if attempt > 1:
                print(f"\n🔄 Attempt {attempt}/{max_retries}")
            
            print(f"🔨 Building Docker image...")
            
            process = subprocess.Popen(
                ["docker", "build", "-t", image_tag, "."],
                cwd=actual_project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout_bytes, stderr_bytes = process.communicate(timeout=600)
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            
            if process.returncode == 0:
                print(f"✅ Build successful!")
                return {
                    "success": True,
                    "image_tag": image_tag,
                    "dockerfile_path": dockerfile_path,
                    "project_root": actual_project_path,
                    "detected_port": detected_port
                }
            
            print(f"❌ Build failed")
            
            if attempt >= max_retries:
                return {"success": False, "message": stderr if stderr else stdout}
        
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Build timeout"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}