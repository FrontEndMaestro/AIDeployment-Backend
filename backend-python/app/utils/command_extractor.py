"""
Node.js command extraction utilities for Docker deployment.
Parses package.json to find actual start commands and entry points.
Includes enhanced detection for custom build output directories.
"""
import os
import json
import re
from typing import Dict, Optional


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
    config_files = ["webpack.config.js", "webpack.config.ts", "webpack.prod.js"]
    
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
            
            # Parse the start script to extract the actual command
            # Common patterns: "node app.js", "nodemon server.js", "npm run serve"
            if start_script.startswith("node "):
                # Extract the file from "node app.js" or "node src/index.js"
                parts = start_script.split()
                if len(parts) >= 2:
                    result["entry_point"] = parts[1]
                    result["start_command"] = start_script
            elif start_script.startswith("nodemon "):
                # Convert nodemon to node for production
                parts = start_script.split()
                if len(parts) >= 2:
                    result["entry_point"] = parts[1]
                    result["start_command"] = f"node {parts[1]}"
            elif start_script.startswith("ts-node ") or "tsx " in start_script:
                # TypeScript - needs build first
                result["start_command"] = "npm start"
            else:
                # Use npm start for complex scripts
                result["start_command"] = "npm start"
                
                # Try to infer entry from script content
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
