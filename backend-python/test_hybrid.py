"""
Test LLM response for both monorepo and normal cases.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.detector import detect_framework
from app.LLM.docker_deploy_agent import run_docker_deploy_chat, build_deploy_message

# Test Case 1: Monorepo - MERN-eCommerce-main (backend has NO package.json)
MONOREPO_PATH = r"C:\Users\abdul\Downloads\devops-autopilot\devops-autopilot\backend-python\uploads\user_abdulahadabbassi2@gmail.com\extracted\project-693998a41a9cb800f55a57f4\MERN-eCommerce-main"

# Test Case 2: Normal - need to find a project with package.json inside backend
# Let's search for one or simulate it

def test_monorepo_case():
    """Test monorepo case where backend has NO package.json"""
    print("=" * 70)
    print("TEST CASE 1: MONOREPO (backend has NO package.json)")
    print("=" * 70)
    
    if not os.path.exists(MONOREPO_PATH):
        print(f"ERROR: Path not found: {MONOREPO_PATH}")
        return None
    
    metadata = detect_framework(MONOREPO_PATH, use_ml=False)
    services = metadata.get('services', [])
    
    print(f"\nServices detected: {len(services)}")
    for svc in services:
        print(f"  - {svc.get('name')}: has_own_package_json={svc.get('has_own_package_json')}")
    
    # Call LLM
    print("\nCalling LLM...")
    response = run_docker_deploy_chat(
        project_name="mern-ecommerce-main",
        metadata=metadata,
        dockerfiles=[],
        compose_files=[],
        file_tree=None,
        user_message="generate",
        services=services
    )
    
    # Save response
    with open("test_hybrid_monorepo.txt", "w", encoding="utf-8") as f:
        f.write(response)
    
    # Check key patterns
    print("\nChecking LLM response...")
    checks = {
        "Dockerfile.backend at root": "Dockerfile.backend" in response,
        "context: . for backend": "context: ." in response.lower() or "context:." in response,
        "dockerfile: Dockerfile.backend": "dockerfile: Dockerfile.backend" in response.lower() or "dockerfile:dockerfile.backend" in response.lower().replace(" ", ""),
        "COPY backend": "COPY backend" in response,
        "CMD with backend/": 'backend/server' in response or 'backend/' in response,
    }
    
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
    
    return response


def test_normal_case():
    """Test normal case where backend HAS its own package.json"""
    print("\n" + "=" * 70)
    print("TEST CASE 2: NORMAL (backend HAS package.json)")
    print("=" * 70)
    
    # Simulate normal fullstack metadata
    metadata = {
        "language": "JavaScript",
        "framework": "Express.js",
        "runtime": "node:20-alpine",
        "backend_port": 4000,
        "frontend_port": 5173,
        "database": "MongoDB",
        "database_is_cloud": True,
        "has_package_json": True,
    }
    
    services = [
        {
            "name": "backend",
            "path": "backend/",
            "type": "backend",
            "port": 4000,
            "entry_point": "src/server.js",
            "env_file": "./backend/.env",
            "package_manager": {"manager": "npm", "has_lockfile": True},
            "has_own_package_json": True,  # Normal case
        },
        {
            "name": "frontend",
            "path": "frontend/",
            "type": "frontend",
            "port": 5173,
            "build_output": "dist",
            "package_manager": {"manager": "npm", "has_lockfile": True},
            "has_own_package_json": True,
        }
    ]
    
    print(f"\nSimulated services:")
    for svc in services:
        print(f"  - {svc.get('name')}: has_own_package_json={svc.get('has_own_package_json')}")
    
    # Call LLM
    print("\nCalling LLM...")
    response = run_docker_deploy_chat(
        project_name="normal-mern-project",
        metadata=metadata,
        dockerfiles=[],
        compose_files=[],
        file_tree=None,
        user_message="generate",
        services=services
    )
    
    # Save response
    with open("test_hybrid_normal.txt", "w", encoding="utf-8") as f:
        f.write(response)
    
    # Check key patterns
    print("\nChecking LLM response...")
    checks = {
        "backend/Dockerfile (in folder)": "backend/Dockerfile" in response,
        "frontend/Dockerfile (in folder)": "frontend/Dockerfile" in response,
        "build: ./backend": "build: ./backend" in response.lower() or "build:./backend" in response.lower(),
        "build: ./frontend": "build: ./frontend" in response.lower() or "build:./frontend" in response.lower(),
        "CMD [node, src/server.js] or entry": 'src/server' in response or 'server.js' in response,
    }
    
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
    
    return response


if __name__ == "__main__":
    print("Testing Hybrid Dockerfile Approach\n")
    
    # Test monorepo
    monorepo_response = test_monorepo_case()
    
    # Test normal
    normal_response = test_normal_case()
    
    print("\n" + "=" * 70)
    print("DONE - Check test_hybrid_monorepo.txt and test_hybrid_normal.txt")
    print("=" * 70)
