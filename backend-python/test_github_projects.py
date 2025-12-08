"""
Test LLM Docker generation with REAL GitHub MERN projects.
Projects tested:
1. adrianhajdin/project_mern_memories - CRA frontend, Express backend
2. idurar/idurar-erp-crm - Vite frontend, Express backend with dotenv
"""
import requests
import json
import time

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

SYSTEM_PROMPT = """You are a Docker Configuration Engine. Generate Docker files based on metadata.

CRITICAL RULES:
1. Use EXACT values from metadata (runtime, ports, entry_point)
2. Include verification comment: # VERIFICATION: runtime=..., port=...
3. Never use default ports (3000, 8000) unless metadata specifies them
4. For frontends: CRA (react-scripts) uses /app/build, Vite uses /app/dist
5. Use 'serve -s' for SPAs, not nginx
6. For cloud databases: DO NOT add database container
7. For local databases: ADD database container to compose

Respond with the Dockerfile and docker-compose.yml content."""

# Real GitHub projects
GITHUB_PROJECTS = [
    {
        "name": "adrianhajdin/project_mern_memories",
        "description": "MERN Memories App - CRA frontend + Express backend with MongoDB",
        "backend": {
            "name": "mern-stack-api",
            "main": "index.js",
            "scripts": {"start": "nodemon index.js"},
            "dependencies": {
                "express": "^4.17.1",
                "mongoose": "^5.9.29",
                "cors": "^2.8.5"
            }
        },
        "frontend": {
            "name": "mern-stack-client",
            "proxy": "http://localhost:5000",
            "dependencies": {
                "react": "^16.12.0",
                "react-scripts": "3.4.1",
                "redux": "^4.0.5"
            },
            "scripts": {
                "start": "react-scripts start",
                "build": "react-scripts build"
            }
        },
        "expected_metadata": {
            "backend_port": 5000,  # From proxy
            "frontend_build": "build",  # CRA
            "backend_entry": "index.js"
        }
    },
    {
        "name": "idurar/idurar-erp-crm",
        "description": "IDURAR ERP CRM - Vite frontend + Express backend with MongoDB",
        "backend": {
            "name": "idurar-erp-crm",
            "scripts": {
                "start": "node src/server.js",
                "dev": "nodemon src/server.js"
            },
            "dependencies": {
                "express": "^4.18.2",
                "mongoose": "^8.1.1",
                "dotenv": "16.3.1"
            },
            "main": "server.js"
        },
        "frontend": {
            "name": "idurar-erp-crm-frontend",
            "dependencies": {
                "react": "^18.3.1",
                "vite": "^5.4.8"
            },
            "scripts": {
                "dev": "vite",
                "build": "vite build"
            }
        },
        "expected_metadata": {
            "backend_port": 8888,  # Common Express port
            "frontend_build": "dist",  # Vite
            "backend_entry": "src/server.js"
        }
    }
]

def call_llm(prompt):
    """Call Ollama API."""
    full_prompt = f"System: {SYSTEM_PROMPT}\n\nUser: {prompt}\n\nAssistant:"
    
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192}
            },
            timeout=180
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


def test_github_project(project):
    """Test LLM with a real GitHub project."""
    print(f"\n{'='*60}")
    print(f"PROJECT: {project['name']}")
    print(f"Description: {project['description']}")
    print("-" * 60)
    
    # Build the prompt using project data
    prompt = f"""Generate Docker configuration for this MERN project from GitHub:

PROJECT: {project['name']}

BACKEND (server folder):
- Package: {project['backend']['name']}
- Start script: {project['backend']['scripts'].get('start', 'node server.js')}
- Main entry: {project['backend'].get('main', 'index.js')}
- Dependencies: {', '.join(project['backend']['dependencies'].keys())}
- Has mongoose: YES (MongoDB will be used)

FRONTEND (client folder):
- Package: {project['frontend']['name']}
- Dependencies: {', '.join(project['frontend']['dependencies'].keys())}
- Build script: {project['frontend']['scripts'].get('build', 'npm run build')}
- Framework: {'CRA (react-scripts)' if 'react-scripts' in project['frontend']['dependencies'] else 'Vite' if 'vite' in project['frontend']['dependencies'] else 'Unknown'}

METADATA:
- Backend port: {project['expected_metadata']['backend_port']}
- Backend entry: {project['expected_metadata']['backend_entry']}
- Frontend build output: {project['expected_metadata']['frontend_build']}
- Database: MongoDB (assume cloud - DO NOT add mongo container)
- Runtime: node:20-alpine

Generate:
1. server/Dockerfile (backend)
2. client/Dockerfile (frontend) 
3. docker-compose.yml

Use EXACT metadata values. Include VERIFICATION comments."""

    print(f"\nCalling LLM...")
    start = time.time()
    response = call_llm(prompt)
    elapsed = time.time() - start
    
    if response.startswith("ERROR:"):
        print(f"LLM Error: {response}")
        return {"passed": 0, "failed": 0, "error": response}
    
    print(f"Response time: {elapsed:.1f}s")
    print(f"Output length: {len(response)} chars")
    
    # Validate response
    checks = []
    
    # Check 1: Backend port
    port = str(project['expected_metadata']['backend_port'])
    checks.append(("Backend port", port in response, f"Should contain port {port}"))
    
    # Check 2: Frontend build output
    build_out = project['expected_metadata']['frontend_build']
    checks.append(("Frontend build", f"/app/{build_out}" in response, f"Should use /app/{build_out}"))
    
    # Check 3: Backend entry point
    entry = project['expected_metadata']['backend_entry']
    checks.append(("Entry point", entry in response, f"Should contain {entry}"))
    
    # Check 4: No mongo container (cloud DB)
    has_mongo = "mongo:" in response.lower() and "services:" in response.lower()
    checks.append(("No mongo container", not has_mongo, "Should NOT have mongo service (cloud DB)"))
    
    # Check 5: Uses serve for SPA
    checks.append(("Uses serve", "serve" in response.lower(), "Should use serve for SPA"))
    
    # Check 6: Has verification comments
    checks.append(("Verification", "verification" in response.lower(), "Should have VERIFICATION comment"))
    
    # Print results
    print(f"\nValidation:")
    passed = 0
    failed = 0
    for name, result, desc in checks:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}: {desc}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nResult: {passed}/{len(checks)} passed")
    
    # Show snippet of output
    print(f"\n--- LLM Output (first 500 chars) ---")
    print(response[:500])
    print("...")
    
    return {"passed": passed, "failed": failed, "total": len(checks)}


def run_all_tests():
    """Run tests for all GitHub projects."""
    print("=" * 70)
    print("LLM DOCKER GENERATION - REAL GITHUB PROJECTS TEST")
    print("=" * 70)
    
    total_passed = 0
    total_failed = 0
    total_checks = 0
    
    for project in GITHUB_PROJECTS:
        result = test_github_project(project)
        total_passed += result.get("passed", 0)
        total_failed += result.get("failed", 0)
        total_checks += result.get("total", 0)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Projects tested: {len(GITHUB_PROJECTS)}")
    print(f"Total checks: {total_checks}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    if total_checks > 0:
        rate = total_passed / total_checks * 100
        print(f"Success rate: {rate:.1f}%")
        
        if rate >= 90:
            print("\n>>> LLM handles real GitHub projects WELL <<<")
        elif rate >= 70:
            print("\n>>> Some improvements may be needed <<<")
        else:
            print("\n>>> Prompt improvements needed <<<")


if __name__ == "__main__":
    run_all_tests()
