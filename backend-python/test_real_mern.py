"""
Test LLM Docker generation with REAL GitHub MERN projects.
Uses the ACTUAL system prompt from docker_deploy_agent.py.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.LLM.docker_deploy_agent import run_docker_deploy_chat, DOCKER_DEPLOY_SYSTEM_PROMPT

# Real MERN project metadata (simulating detected projects)
GITHUB_PROJECTS = [
    {
        "name": "mern-memories",
        "description": "MERN Memories App - CRA frontend + Express backend with MongoDB",
        "metadata": {
            "language": "JavaScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 5000,
            "frontend_port": 3000,
            "database": "MongoDB",
            "database_is_cloud": True,  # Cloud DB - no container
        },
        "services": [
            {
                "name": "backend",
                "path": "server/",
                "type": "backend",
                "port": 5000,
                "entry_point": "index.js",
                "env_file": "./server/.env",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
            {
                "name": "frontend",
                "path": "client/",
                "type": "frontend",
                "port": 3000,
                "build_output": "build",  # CRA uses build
                "package_manager": {"manager": "npm", "has_lockfile": True},
            }
        ],
        "checks": {
            "backend_port": "5000",
            "frontend_build": "build",
            "entry_point": "index.js",
            "no_mongo": True,  # Cloud DB
        }
    },
    {
        "name": "mern-blog-app",
        "description": "MERN Blog App - Vite frontend + Express backend with local MongoDB",
        "metadata": {
            "language": "JavaScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "frontend_port": 5173,
            "database": "MongoDB",
            "database_is_cloud": False,  # Local DB - add container
        },
        "services": [
            {
                "name": "backend",
                "path": "backend/",
                "type": "backend",
                "port": 3000,
                "entry_point": "src/server.js",
                "env_file": "./backend/.env",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
            {
                "name": "frontend",
                "path": "frontend/",
                "type": "frontend",
                "port": 5173,
                "build_output": "dist",  # Vite uses dist
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
            {
                "name": "mongo",
                "path": ".",
                "type": "database",
                "port": 27017,
                "docker_image": "mongo:latest",
                "is_cloud": False,
            }
        ],
        "checks": {
            "backend_port": "3000",
            "frontend_build": "dist",
            "entry_point": "src/server.js",
            "has_mongo": True,  # Local DB
        }
    },
    {
        "name": "react-job-portal",
        "description": "Job Portal - Vite frontend + Express backend with cloud MongoDB",
        "metadata": {
            "language": "JavaScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 4000,
            "frontend_port": 5173,
            "database": "MongoDB",
            "database_is_cloud": True,  # Cloud DB
        },
        "services": [
            {
                "name": "backend",
                "path": "backend/",
                "type": "backend",
                "port": 4000,
                "entry_point": "server.js",
                "env_file": "./backend/.env",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
            {
                "name": "frontend",
                "path": "frontend/",
                "type": "frontend",
                "port": 5173,
                "build_output": "dist",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            }
        ],
        "checks": {
            "backend_port": "4000",
            "frontend_build": "dist",
            "entry_point": "server.js",
            "no_mongo": True,
        }
    }
]


def test_project(project):
    """Test LLM with a project."""
    print(f"\n{'='*70}")
    print(f"PROJECT: {project['name']}")
    print(f"Description: {project['description']}")
    print("-" * 70)
    
    start = time.time()
    
    # Call LLM using actual function
    response = run_docker_deploy_chat(
        project_name=project["name"],
        metadata=project["metadata"],
        dockerfiles=[],
        compose_files=[],
        file_tree=None,
        user_message="generate",
        services=project["services"]
    )
    
    elapsed = time.time() - start
    print(f"Response time: {elapsed:.1f}s")
    print(f"Output length: {len(response)} chars")
    
    # Validate response
    checks = []
    
    # Check 1: Backend port
    port = project["checks"]["backend_port"]
    checks.append(("Backend port", port in response, f"Contains {port}"))
    
    # Check 2: Frontend build output
    build_out = project["checks"]["frontend_build"]
    checks.append(("Frontend build", build_out in response, f"Contains {build_out}"))
    
    # Check 3: Entry point
    entry = project["checks"]["entry_point"]
    checks.append(("Entry point", entry in response, f"Contains {entry}"))
    
    # Check 4: Image names
    img_name = f"{project['name']}-backend"
    checks.append(("Image name", img_name in response.lower(), f"Contains {img_name}"))
    
    # Check 5: COPY . . before build
    copy_check = "COPY . ." in response or "COPY . ./" in response
    checks.append(("COPY . .", copy_check, "Has COPY . . before build"))
    
    # Check 6: Mongo container
    has_mongo = "mongo:" in response.lower() and "services:" in response.lower()
    if project["checks"].get("has_mongo"):
        checks.append(("Has mongo", has_mongo, "Should have mongo service"))
    elif project["checks"].get("no_mongo"):
        checks.append(("No mongo", not has_mongo, "Should NOT have mongo (cloud)"))
    
    # Check 7: env_file
    has_env = "env_file" in response.lower()
    checks.append(("env_file", has_env, "Has env_file directive"))
    
    # Print results
    print(f"\nValidation:")
    passed = 0
    for name, result, desc in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {desc}")
        if result:
            passed += 1
    
    print(f"\nResult: {passed}/{len(checks)} passed")
    
    # Show snippet
    print(f"\n--- LLM Output (first 800 chars) ---")
    print(response[:800])
    if len(response) > 800:
        print("...")
    
    return {"passed": passed, "total": len(checks), "response": response}


def run_all_tests():
    """Run tests for all projects."""
    print("=" * 70)
    print("LLM DOCKER GENERATION - REAL MERN PROJECTS TEST")
    print(f"Model: Using settings from .env")
    print("=" * 70)
    
    results = []
    
    for project in GITHUB_PROJECTS:
        result = test_project(project)
        results.append(result)
    
    # Summary
    total_passed = sum(r["passed"] for r in results)
    total_checks = sum(r["total"] for r in results)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Projects tested: {len(GITHUB_PROJECTS)}")
    print(f"Total checks: {total_checks}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_checks - total_passed}")
    
    if total_checks > 0:
        rate = total_passed / total_checks * 100
        print(f"Success rate: {rate:.1f}%")
        
        if rate >= 90:
            print("\n🎉 EXCELLENT - LLM handles projects well!")
        elif rate >= 70:
            print("\n⚠️ GOOD - Some improvements may help")
        else:
            print("\n❌ NEEDS WORK - Prompt improvements needed")
    
    # Save responses
    with open("test_mern_responses.txt", "w", encoding="utf-8") as f:
        for i, project in enumerate(GITHUB_PROJECTS):
            f.write(f"\n{'='*70}\n")
            f.write(f"PROJECT: {project['name']}\n")
            f.write(f"{'='*70}\n")
            f.write(results[i]["response"])
            f.write("\n\n")
    
    print("\nFull responses saved to: test_mern_responses.txt")


if __name__ == "__main__":
    run_all_tests()
