"""
Node.js command extraction utilities for Docker deployment.
Parses package.json to find actual start commands and entry points.
Includes enhanced detection for custom build output directories.
"""
import os
import json
import re
from typing import Dict, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _parse_vite_config(project_path: str) -> Optional[str]:
    """
    Parse vite.config.js/ts for custom outDir.
    Example: build: { outDir: 'public' }
    """
    config_files = ["vite.config.js", "vite.config.ts", "vite.config.mjs"]
    
    for config_file in config_files:
        config_path = os.path.join(project_path, config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Pattern: outDir: 'custom_dir' or outDir: "custom_dir"
                patterns = [
                    r"outDir\s*:\s*['\"]([^'\"]+)['\"]",
                    r"outDir\s*:\s*`([^`]+)`",
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        out_dir = match.group(1)
                        print(f"📦 Found custom outDir in {config_file}: {out_dir}")
                        return out_dir
                        
            except Exception as e:
                print(f"Error parsing {config_file}: {e}")
    
    return None


def _parse_vue_config(project_path: str) -> Optional[str]:
    """
    Parse vue.config.js for custom outputDir.
    Example: outputDir: 'public'
    """
    config_path = os.path.join(project_path, "vue.config.js")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Pattern: outputDir: 'custom_dir'
            patterns = [
                r"outputDir\s*:\s*['\"]([^'\"]+)['\"]",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    out_dir = match.group(1)
                    print(f"📦 Found custom outputDir in vue.config.js: {out_dir}")
                    return out_dir
                    
        except Exception as e:
            print(f"Error parsing vue.config.js: {e}")
    
    return None


def _parse_webpack_config(project_path: str) -> Optional[str]:
    """
    Parse webpack.config.js for output.path.
    Example: output: { path: path.resolve(__dirname, 'public') }
    """
    # Extended config paths including nested directories (Fix 4)
    config_files = [
        "webpack.config.js", "webpack.config.ts", "webpack.prod.js",
        # Nested config paths (Fix 4)
        "configs/webpack.config.js", "configs/webpack.prod.js",
        "config/webpack.config.js", "config/webpack.prod.js",
        "build/webpack.config.js", "build/webpack.prod.js",
    ]
    
    for config_file in config_files:
        config_path = os.path.join(project_path, config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Patterns for webpack output path
                patterns = [
                    # path.resolve(__dirname, 'dist')
                    r"path\.resolve\s*\([^,]+,\s*['\"]([^'\"]+)['\"]\)",
                    # path.join(__dirname, 'dist')
                    r"path\.join\s*\([^,]+,\s*['\"]([^'\"]+)['\"]\)",
                    # path: 'dist'
                    r"path\s*:\s*['\"]([^'\"]+)['\"]",
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        out_dir = match.group(1)
                        # Clean up the path
                        out_dir = out_dir.strip('./')
                        if out_dir and out_dir not in ['__dirname', '']:
                            print(f"📦 Found custom output.path in {config_file}: {out_dir}")
                            return out_dir
                            
            except Exception as e:
                print(f"Error parsing {config_file}: {e}")
    
    return None


def _parse_gitignore_for_build_dir(project_path: str) -> Optional[str]:
    """
    Check .gitignore for common build output patterns.
    Many projects gitignore their build output directory.
    """
    gitignore_path = os.path.join(project_path, ".gitignore")
    
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Common build output patterns (order matters - more specific first)
            build_patterns = [
                ("build/", "build"),
                ("build", "build"),
                ("/build", "build"),
                ("dist/", "dist"),
                ("dist", "dist"),
                ("/dist", "dist"),
                ("out/", "out"),
                ("/out", "out"),
                ("public/", "public"),
                (".next/", ".next"),
                (".next", ".next"),
            ]
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                for pattern, output in build_patterns:
                    if line == pattern or line.startswith(pattern):
                        print(f"📦 Found build output in .gitignore: {output}")
                        return output
                        
        except Exception as e:
            print(f"Error parsing .gitignore: {e}")
    
    return None


def extract_nodejs_commands(project_path: str) -> Dict[str, Optional[str]]:
    """
    Extract actual start commands from package.json scripts.
    Returns dict with:
      - start_command: The actual start command (e.g., "node app.js", "npm start")
      - entry_point: The main file (e.g., "app.js", "server.js", "index.js")
      - build_command: Build script if exists
      - build_output: Build output directory (e.g., "dist", "build", ".next")
    """
    result = {
        "start_command": None,
        "entry_point": None,
        "build_command": None,
        "build_output": None,  # NEW: Track build output directory
        "has_start_script": False,
    }
    
    # Find package.json (search up to 2 levels deep for monorepos)
    pkg_paths = [
        os.path.join(project_path, "package.json"),
        os.path.join(project_path, "backend", "package.json"),
        os.path.join(project_path, "server", "package.json"),
    ]
    
    pkg_json_path = None
    for p in pkg_paths:
        if os.path.exists(p):
            pkg_json_path = p
            break
    
    if not pkg_json_path:
        return result
    
    try:
        with open(pkg_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        scripts = data.get("scripts", {})
        main_entry = data.get("main", None)
        
        # Check for start script
        if "start" in scripts:
            result["has_start_script"] = True
            start_script = scripts["start"]
            
            # Helper function to extract entry point from complex scripts (Fix 2)
            def extract_entry_from_script(script: str) -> Optional[str]:
                """
                Extract the actual .js/.ts file from complex scripts like:
                'NODE_ENV=production node --max-old-space-size=4096 server/index.js'
                Skips: env vars (containing '='), flags (starting with '-')
                """
                parts = script.split()
                for part in parts:
                    # Skip env vars (e.g., NODE_ENV=production)
                    if '=' in part:
                        continue
                    # Skip flags (e.g., --max-old-space-size=4096)
                    if part.startswith('-'):
                        continue
                    # Skip 'node', 'nodemon', 'npx', etc.
                    if part in ('node', 'nodemon', 'npx', 'ts-node', 'tsx', 'npm', 'yarn', 'pnpm'):
                        continue
                    # Must be a .js or .ts file path
                    if part.endswith('.js') or part.endswith('.ts') or part.endswith('.mjs'):
                        return part
                    # Or a path without extension (e.g., 'server/index')
                    if '/' in part and not part.startswith('-'):
                        return part
                return None
            
            # Parse the start script to extract the actual command
            # Common patterns: "node app.js", "nodemon server.js", "npm run serve"
            if start_script.startswith("node "):
                # Extract the file using smart parsing (Fix 2)
                entry = extract_entry_from_script(start_script)
                if entry:
                    result["entry_point"] = entry
                    result["start_command"] = f"node {entry}"
                else:
                    # Fallback to simple parsing
                    parts = start_script.split()
                    if len(parts) >= 2:
                        result["entry_point"] = parts[1]
                        result["start_command"] = start_script
            elif start_script.startswith("nodemon "):
                # Convert nodemon to node for production
                entry = extract_entry_from_script(start_script)
                if entry:
                    result["entry_point"] = entry
                    result["start_command"] = f"node {entry}"
                else:
                    parts = start_script.split()
                    if len(parts) >= 2:
                        result["entry_point"] = parts[1]
                        result["start_command"] = f"node {parts[1]}"
            elif start_script.startswith("ts-node ") or "tsx " in start_script:
                # TypeScript - needs build first
                result["start_command"] = "npm start"
            elif start_script.startswith("pm2 "):
                # PM2 process manager - don't use ecosystem.config.js as entry
                # Try to get actual entry from dev script instead
                result["start_command"] = "npm start"
                dev_script = scripts.get("dev", "")
                if dev_script:
                    entry = extract_entry_from_script(dev_script)
                    if entry:
                        result["entry_point"] = entry
                        result["start_command"] = f"node {entry}"
                        print(f"📦 PM2 detected, using entry from dev script: {entry}")
            else:
                # Try to infer entry from script content using smart parsing (Fix 2)
                entry = extract_entry_from_script(start_script)
                if entry:
                    result["entry_point"] = entry
                    result["start_command"] = f"node {entry}"
                else:
                    # Use npm start for complex scripts
                    result["start_command"] = "npm start"

                    # Fallback to simple pattern matching
                    for pattern in ["node ", "nodemon "]:
                        if pattern in start_script:
                            idx = start_script.find(pattern) + len(pattern)
                            rest = start_script[idx:].split()[0] if start_script[idx:].split() else None
                            if rest:
                                result["entry_point"] = rest
                                break
        
        # Fallback: check "main" field
        if not result["entry_point"] and main_entry:
            result["entry_point"] = main_entry
            if not result["start_command"]:
                result["start_command"] = f"node {main_entry}"
        
        # Fallback: detect common entry files
        if not result["entry_point"]:
            pkg_dir = os.path.dirname(pkg_json_path)
            common_entries = ["app.js", "server.js", "index.js", "main.js", 
                             "src/index.js", "src/app.js", "src/server.js"]
            for entry in common_entries:
                if os.path.exists(os.path.join(pkg_dir, entry)):
                    result["entry_point"] = entry
                    if not result["start_command"]:
                        result["start_command"] = f"node {entry}"
                    break
        
        # Check for build script and determine build output directory
        if "build" in scripts:
            result["build_command"] = "npm run build"
            
            # Detect build output based on dependencies and framework
            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}
            
            # Create React App (CRA) -> outputs to "build/"
            if "react-scripts" in all_deps:
                result["build_output"] = "build"
                print("📦 Detected Create React App (CRA) -> build output: build/")
            
            # Vite -> outputs to "dist/"
            elif "vite" in all_deps:
                result["build_output"] = "dist"
                print("📦 Detected Vite -> build output: dist/")
            
            # Next.js -> outputs to ".next/" or "out/" for static export
            elif "next" in all_deps:
                build_script = scripts.get("build", "")
                if "next export" in build_script or "export" in scripts:
                    result["build_output"] = "out"
                else:
                    result["build_output"] = ".next"
                print(f"📦 Detected Next.js -> build output: {result['build_output']}/")
            
            # Vue CLI -> outputs to "dist/"
            elif "@vue/cli-service" in all_deps:
                result["build_output"] = "dist"
                print("📦 Detected Vue CLI -> build output: dist/")
            
            # Angular -> outputs to "dist/<project-name>/"
            elif "@angular/cli" in all_deps or "@angular/core" in all_deps:
                result["build_output"] = "dist"
                print("📦 Detected Angular -> build output: dist/")
            
            # Remix -> outputs to "build/" (Fix 3)
            elif "@remix-run/react" in all_deps or "@remix-run/node" in all_deps:
                result["build_output"] = "build"
                print("📦 Detected Remix -> build output: build/")
            
            # Gatsby -> outputs to "public/" (Fix 3)
            elif "gatsby" in all_deps:
                result["build_output"] = "public"
                print("📦 Detected Gatsby -> build output: public/")
            
            # Default to "dist" for unknown build tools
            else:
                result["build_output"] = "dist"
                print("📦 Unknown build tool -> defaulting to: dist/")
            
            # --- Enhanced detection: Check config files for custom outDir ---
            # These can override the dependency-based defaults
            pkg_dir = os.path.dirname(pkg_json_path)
            
            # Check vite.config.js for custom outDir
            vite_out = _parse_vite_config(pkg_dir)
            if vite_out:
                result["build_output"] = vite_out
                print(f"📦 Config override: vite.config -> {vite_out}")
            
            # Check vue.config.js for custom outputDir
            vue_out = _parse_vue_config(pkg_dir)
            if vue_out:
                result["build_output"] = vue_out
                print(f"📦 Config override: vue.config -> {vue_out}")
            
            # Check webpack.config.js for custom output.path
            webpack_out = _parse_webpack_config(pkg_dir)
            if webpack_out:
                result["build_output"] = webpack_out
                print(f"📦 Config override: webpack.config -> {webpack_out}")
            
            # Last resort: check .gitignore for build output patterns
            # Only if we're still using a default value
            if result["build_output"] in ["dist", "build"] and not any([vite_out, vue_out, webpack_out]):
                gitignore_out = _parse_gitignore_for_build_dir(pkg_dir)
                if gitignore_out and gitignore_out != result["build_output"]:
                    # Only override if .gitignore suggests something different
                    print(f"📦 .gitignore suggests different output: {gitignore_out} (current: {result['build_output']})")
                    # Don't auto-override, just log for awareness
        
        print(f"📦 package.json analysis: entry={result['entry_point']}, start={result['start_command']}, build_output={result['build_output']}")
        
    except Exception as e:
        print(f"Error parsing package.json: {e}")
    
    return result


def extract_python_commands(project_path: str) -> Dict[str, Optional[str]]:
    """
    Extract actual start commands for Python projects.
    Looks at manage.py, pyproject.toml, etc.
    """
    result = {
        "start_command": None,
        "entry_point": None,
    }
    
    # Check for Django manage.py
    if os.path.exists(os.path.join(project_path, "manage.py")):
        result["entry_point"] = "manage.py"
        result["start_command"] = "python manage.py runserver 0.0.0.0:8000"
        return result

    # Prefer explicit start commands when present (avoid hardcoding uvicorn <module>:app).
    def _find_explicit_start_command() -> Optional[str]:
        # Procfile (e.g., Heroku)
        procfile_path = os.path.join(project_path, "Procfile")
        if os.path.exists(procfile_path):
            try:
                with open(procfile_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]

                # Prefer web: if present
                for ln in lines:
                    if ":" not in ln:
                        continue
                    proc_type, cmd = ln.split(":", 1)
                    cmd = cmd.strip()
                    if proc_type.strip() == "web" and "uvicorn" in cmd:
                        return cmd

                # Otherwise, first process containing uvicorn
                for ln in lines:
                    if ":" not in ln:
                        continue
                    _, cmd = ln.split(":", 1)
                    cmd = cmd.strip()
                    if "uvicorn" in cmd:
                        return cmd
            except Exception:
                pass

        # pyproject.toml [tool.scripts] (and common variants like tool.pdm.scripts)
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if os.path.exists(pyproject_path) and tomllib is not None:
            try:
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f) or {}

                tool = data.get("tool") or {}
                script_tables = [
                    tool.get("scripts"),
                    (tool.get("pdm") or {}).get("scripts"),
                ]

                for scripts in script_tables:
                    if not isinstance(scripts, dict):
                        continue
                    for val in scripts.values():
                        cmd = None
                        if isinstance(val, str):
                            cmd = val
                        elif isinstance(val, dict):
                            cmd = val.get("cmd") or val.get("command") or val.get("shell")
                        if cmd and "uvicorn" in cmd:
                            return cmd.strip()
            except Exception:
                pass

        # Common start scripts that may contain uvicorn (start.sh, entrypoint.sh, etc.)
        for fname in [
            "start.sh", "run.sh", "entrypoint.sh", "docker-entrypoint.sh", "startup.sh",
            "start.bat", "run.bat",
        ]:
            fpath = os.path.join(project_path, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "uvicorn" in line:
                            if line.startswith("exec "):
                                line = line[5:].strip()
                            return line
            except Exception:
                pass

        return None

    explicit = _find_explicit_start_command()
    if explicit:
        result["start_command"] = explicit
        return result
    
    # Check for common entry files
    for entry in ["app.py", "main.py", "run.py", "server.py", "wsgi.py"]:
        if os.path.exists(os.path.join(project_path, entry)):
            result["entry_point"] = entry
            
            # Check if it's FastAPI/uvicorn
            with open(os.path.join(project_path, entry), 'r', encoding='utf-8') as f:
                content = f.read()
                if "FastAPI" in content or "fastapi" in content:
                    # Infer the app variable name
                    result["start_command"] = f"uvicorn {entry[:-3]}:app --host 0.0.0.0 --port 8000"
                elif "Flask" in content:
                    result["start_command"] = "flask run --host=0.0.0.0"
                else:
                    result["start_command"] = f"python {entry}"
            break
    
    return result


# ============================================================================
# PORT EXTRACTION FUNCTIONS
# ============================================================================

def _parse_env_for_port(project_path: str) -> Optional[int]:
    """
    Parse .env or .env.example files for PORT variable.
    Returns the port number if found, None otherwise.
    """
    env_files = [".env", ".env.example", ".env.sample", ".env.local", ".env.development"]
    
    for env_file in env_files:
        env_path = os.path.join(project_path, env_file)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Pattern: PORT=4000 or PORT = 4000
                match = re.search(r'^PORT\s*=\s*(\d+)', content, re.MULTILINE)
                if match:
                    port = int(match.group(1))
                    print(f"🔌 Found PORT={port} in {env_file}")
                    return port
                    
            except Exception as e:
                print(f"Error parsing {env_file}: {e}")
    
    return None


def _scan_source_for_port(project_path: str, language: str = "javascript") -> Optional[int]:
    """
    Scan source files for port patterns like app.listen(4000) or server.listen(5000).
    Returns the port number if found, None otherwise.
    """
    if language in ("javascript", "typescript", "JavaScript", "TypeScript"):
        # Node.js source files to scan (including TypeScript and lib folder)
        source_files = [
            # JavaScript files
            "server.js", "app.js", "index.js", "main.js",
            "src/server.js", "src/app.js", "src/index.js", "src/main.js",
            "server/index.js", "server/app.js",
            # TypeScript files (Fix 1)
            "server.ts", "app.ts", "index.ts", "main.ts",
            "src/server.ts", "src/app.ts", "src/index.ts", "src/main.ts",
            "server/index.ts", "server/app.ts",
            # lib folder (Fix 5) - including CLI tools
            "lib/index.js", "lib/server.js", "lib/app.js", "lib/cli.js",
            "lib/index.ts", "lib/server.ts", "lib/app.ts", "lib/cli.ts",
        ]
        
        # Node.js port patterns
        patterns = [
            # app.listen(4000) or server.listen(5000)
            r'\.listen\s*\(\s*(\d{4,5})\s*[,)]',
            # process.env.PORT || 4000
            r'process\.env\.PORT\s*\|\|\s*(\d{4,5})',
            # const PORT = 4000
            r'(?:const|let|var)\s+PORT\s*=\s*(\d{4,5})',
            # port: 4000
            r'port\s*:\s*(\d{4,5})',
        ]
    elif language in ("python", "Python"):
        # Python source files
        source_files = [
            "app.py", "main.py", "server.py", "run.py", "wsgi.py",
            "src/main.py", "src/app.py"
        ]
        
        # Python port patterns
        patterns = [
            # port=8000 or port = 8000
            r'port\s*=\s*(\d{4,5})',
            # app.run(port=5000)
            r'run\s*\([^)]*port\s*=\s*(\d{4,5})',
            # uvicorn.run(..., port=8000)
            r'uvicorn\.run\s*\([^)]*port\s*=\s*(\d{4,5})',
        ]
    else:
        return None
    
    for source_file in source_files:
        file_path = os.path.join(project_path, source_file)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                for pattern in patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        port = int(match.group(1))
                        # Validate port is reasonable (not 0 or too large)
                        if 1000 <= port <= 65535:
                            print(f"🔌 Found port {port} in {source_file}")
                            return port
                            
            except Exception as e:
                print(f"Error scanning {source_file}: {e}")
    
    return None


def _get_framework_default_port(framework: str, language: str) -> int:
    """
    Get default port based on framework/language.
    """
    framework_ports = {
        "Express.js": 3000,
        "Next.js": 3000,
        "React": 3000,  # CRA default
        "Vue": 8080,
        "Angular": 4200,
        "Flask": 5000,
        "Django": 8000,
        "FastAPI": 8000,
        "Spring Boot": 8080,
        "Rails": 3000,
        "Gatsby": 8000,  # Fix 6
        "Remix": 3000,   # Fix 6
    }
    
    language_ports = {
        "JavaScript": 3000,
        "TypeScript": 3000,
        "Python": 8000,
        "Java": 8080,
        "Go": 8080,
        "Ruby": 3000,
    }
    
    return framework_ports.get(framework) or language_ports.get(language) or 3000


def extract_port_from_project(project_path: str, framework: str = "Unknown", language: str = "Unknown") -> Dict[str, any]:
    """
    Extract backend port using priority:
    1. .env file
    2. Source code scanning
    3. Framework defaults
    
    Returns dict with:
      - port: The detected port number
      - source: Where the port was detected from ("env", "source", "default")
    """
    result = {
        "port": None,
        "source": None,
    }
    
    # Priority 1: Check .env files
    env_port = _parse_env_for_port(project_path)
    if env_port:
        result["port"] = env_port
        result["source"] = "env"
        print(f"🔌 Port detected from .env: {env_port}")
        return result
    
    # Priority 2: Scan source code
    source_port = _scan_source_for_port(project_path, language)
    if source_port:
        result["port"] = source_port
        result["source"] = "source"
        print(f"🔌 Port detected from source code: {source_port}")
        return result
    
    # Priority 3: Framework defaults
    default_port = _get_framework_default_port(framework, language)
    result["port"] = default_port
    result["source"] = "default"
    print(f"🔌 Using framework default port: {default_port}")
    
    return result


def extract_frontend_port(project_path: str) -> Dict[str, any]:
    """
    Extract frontend dev server port from vite.config.js or other frontend configs.
    """
    result = {
        "port": None,
        "source": None,
    }
    
    # Check vite.config.js
    vite_configs = ["vite.config.js", "vite.config.ts", "vite.config.mjs"]
    for config_file in vite_configs:
        config_path = os.path.join(project_path, config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Pattern: port: 5173 or port: 3000
                match = re.search(r'port\s*:\s*(\d{4,5})', content)
                if match:
                    result["port"] = int(match.group(1))
                    result["source"] = config_file
                    print(f"🔌 Frontend port from {config_file}: {result['port']}")
                    return result
            except Exception:
                pass
    
    # Check .env for VITE_PORT or similar
    env_port = _parse_env_for_port(project_path)
    if env_port:
        result["port"] = env_port
        result["source"] = "env"
        return result
    
    # Check package.json dependencies for default
    pkg_path = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            
            if "vite" in deps:
                result["port"] = 5173
                result["source"] = "vite_default"
            elif "react-scripts" in deps:
                result["port"] = 3000
                result["source"] = "cra_default"
            elif "next" in deps:
                result["port"] = 3000
                result["source"] = "next_default"
            elif "@vue/cli-service" in deps:
                result["port"] = 8080
                result["source"] = "vue_default"
            elif "@angular/cli" in deps:
                result["port"] = 4200
                result["source"] = "angular_default"
            else:
                result["port"] = 3000
                result["source"] = "default"
                
        except Exception:
            result["port"] = 3000
            result["source"] = "default"
    else:
        result["port"] = 3000
        result["source"] = "default"
    
    print(f"🔌 Frontend port: {result['port']} (source: {result['source']})")
    return result


# ============================================================================
# DATABASE DETECTION FUNCTIONS
# ============================================================================

# Database env var names (in priority order)
DB_ENV_VARS = [
    # MongoDB
    "MONGO_URI", "MONGODB_URI", "MONGO_URL", "MONGODB_URL", "DB_URL",
    "DATABASE_URL", "MONGO_CONNECTION_STRING",
    # PostgreSQL
    "POSTGRES_URL", "POSTGRES_URI", "DATABASE_URL", "PG_URL",
    # MySQL
    "MYSQL_URL", "MYSQL_URI",
    # Redis
    "REDIS_URL", "REDIS_URI",
]

# Cloud database indicators
CLOUD_DB_PATTERNS = [
    # MongoDB Atlas
    "mongodb+srv://",
    "mongodb.net",
    ".mongodb.com",
    # AWS
    ".amazonaws.com",
    ".rds.amazonaws.com",
    # Google Cloud
    ".cloudsql.",
    # Azure
    ".database.azure.com",
    ".cosmos.azure.com",
    # Heroku
    ".heroku.com",
    # ElephantSQL
    ".elephantsql.com",
    # PlanetScale
    ".psdb.cloud",
    # Supabase
    ".supabase.co",
    # Neon
    ".neon.tech",
    # Railway
    ".railway.app",
]


def _parse_env_for_database(project_path: str) -> Dict[str, any]:
    """
    Parse .env files for database connection URLs.
    Returns dict with:
      - db_type: "mongodb", "postgresql", "mysql", "redis", or None
      - is_cloud: True if cloud database, False if local
      - env_var_name: Name of the environment variable (e.g., "MONGO_URI")
      - connection_url: The actual URL (for analysis, not to expose)
    """
    result = {
        "db_type": None,
        "is_cloud": False,
        "env_var_name": None,
        "connection_url": None,
    }
    
    env_files = [".env", ".env.example", ".env.sample", ".env.local", ".env.development"]
    
    for env_file in env_files:
        env_path = os.path.join(project_path, env_file)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                for var_name in DB_ENV_VARS:
                    # Pattern: VAR_NAME=value or VAR_NAME = value
                    pattern = rf'^{var_name}\s*=\s*(.+)$'
                    match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
                    if match:
                        url = match.group(1).strip().strip('"\'')
                        result["env_var_name"] = var_name
                        result["connection_url"] = url
                        
                        # Detect database type from URL
                        url_lower = url.lower()
                        if "mongodb" in url_lower or "mongo" in var_name.lower():
                            result["db_type"] = "mongodb"
                        elif "postgres" in url_lower or "pg" in var_name.lower():
                            result["db_type"] = "postgresql"
                        elif "mysql" in url_lower:
                            result["db_type"] = "mysql"
                        elif "redis" in url_lower:
                            result["db_type"] = "redis"
                        
                        # Check if it's a cloud database
                        for cloud_pattern in CLOUD_DB_PATTERNS:
                            if cloud_pattern in url_lower:
                                result["is_cloud"] = True
                                print(f"☁️ Detected CLOUD database: {result['db_type']} (from {env_file})")
                                break
                        
                        # Check for localhost/local indicators
                        if not result["is_cloud"]:
                            if "localhost" in url_lower or "127.0.0.1" in url_lower or "host.docker.internal" in url_lower:
                                result["is_cloud"] = False
                                print(f"🏠 Detected LOCAL database: {result['db_type']} (from {env_file})")
                            else:
                                # Unknown host - assume cloud for safety
                                result["is_cloud"] = True
                                print(f"☁️ Detected database (assuming cloud): {result['db_type']} (from {env_file})")
                        
                        return result
                        
            except Exception as e:
                print(f"Error parsing {env_file} for database: {e}")
    
    return result


def extract_database_info(project_path: str, detected_db: str = None) -> Dict[str, any]:
    """
    Extract complete database information for Docker deployment.
    
    Returns dict with:
      - db_type: "mongodb", "postgresql", "mysql", "redis", or None
      - is_cloud: True if cloud database (don't add container)
      - needs_container: True if should add database container to compose
      - env_var_name: Name of env var to pass through
      - default_port: Default port for this database type
      - docker_image: Docker image to use if container needed
    """
    result = {
        "db_type": None,
        "is_cloud": False,
        "needs_container": False,
        "env_var_name": None,
        "default_port": None,
        "docker_image": None,
    }
    
    # Database defaults
    db_defaults = {
        "mongodb": {"port": 27017, "image": "mongo:latest"},
        "postgresql": {"port": 5432, "image": "postgres:15-alpine"},
        "mysql": {"port": 3306, "image": "mysql:8"},
        "redis": {"port": 6379, "image": "redis:alpine"},
    }
    
    # First, check .env for database URL
    env_db = _parse_env_for_database(project_path)
    
    if env_db.get("db_type"):
        result["db_type"] = env_db["db_type"]
        result["is_cloud"] = env_db["is_cloud"]
        result["env_var_name"] = env_db["env_var_name"]
        
        # Only need container if LOCAL database
        result["needs_container"] = not env_db["is_cloud"]
        
        if result["db_type"] in db_defaults:
            result["default_port"] = db_defaults[result["db_type"]]["port"]
            result["docker_image"] = db_defaults[result["db_type"]]["image"]
    
    # Fallback to detected_db from dependency analysis
    elif detected_db:
        db_lower = detected_db.lower()
        for db_name in db_defaults:
            if db_name in db_lower:
                result["db_type"] = db_name
                result["default_port"] = db_defaults[db_name]["port"]
                result["docker_image"] = db_defaults[db_name]["image"]
                # No .env found, assume local development
                result["is_cloud"] = False
                result["needs_container"] = True
                print(f"🏠 No DB URL in .env, assuming LOCAL {db_name} container needed")
                break
    
    print(f"🗄️ Database detection: type={result['db_type']}, cloud={result['is_cloud']}, needs_container={result['needs_container']}")
    return result
