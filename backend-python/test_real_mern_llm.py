"""
Test LLM Docker generation with REAL GitHub MERN project configurations.

This test uses actual package.json data from popular GitHub MERN repositories
to validate that the LLM generates correct Dockerfiles and docker-compose.yml files.

Projects tested:
1. adrianhajdin/project_mern_memories - CRA (react-scripts) + Express backend
2. idurar/idurar-erp-crm - Vite frontend + Express backend with MongoDB
3. Next.js SSR App - Server-side rendering with Next.js
4. Express API Only - Backend-only Express with MongoDB
5. TypeScript MERN - TypeScript backend + Vite frontend with PostgreSQL
"""
import sys
import os
import re
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.LLM.docker_deploy_agent import run_docker_deploy_chat, build_deploy_message, DOCKER_DEPLOY_SYSTEM_PROMPT
from app.LLM.llm_client import call_llama


# ============================================================================
# REAL GITHUB MERN PROJECT CONFIGURATIONS
# Data sourced directly from actual GitHub repositories
# ============================================================================

MERN_PROJECTS = [
    {
        # Project 1: adrianhajdin/project_mern_memories
        # Classic CRA + Express fullstack app
        "name": "project_mern_memories",
        "github": "adrianhajdin/project_mern_memories",
        "description": "MERN Memories App - Classic CRA frontend + Express backend with MongoDB",
        "project_name": "mern-memories",
        "metadata": {
            "framework": "MERN Stack",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 5000,  # From client/package.json proxy field
            "frontend_port": 3000,  # CRA default
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": True,  # Uses MongoDB Atlas
            "database_env_var": "CONNECTION_URL",
            "build_command": "npm run build",
            "start_command": "node index.js",
            "entry_point": "index.js",
            "build_output": "build",  # CRA uses build/
        },
        "services": [
            {
                "name": "backend",
                "path": "server",
                "type": "backend",
                "port": 5000,
                "port_source": "proxy",
                "entry_point": "index.js",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            },
            {
                "name": "frontend",
                "path": "client",
                "type": "frontend",
                "port": 3000,
                "port_source": "cra_default",
                "build_output": "build",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            }
        ],
        "expected_checks": [
            ("backend_port", "5000", True, "Backend should expose port 5000"),
            ("frontend_build_path", "/app/build", True, "CRA frontend should use /app/build"),
            ("backend_entry", "index.js", True, "Backend entry point should be index.js"),
            ("no_db_container", "mongo:", False, "Should NOT have mongo service (cloud DB)"),
            ("serve_for_spa", "serve", True, "Frontend should use serve for SPA"),
            ("multi_stage_frontend", "AS build", True, "Frontend should use multi-stage build"),
        ]
    },
    {
        # Project 2: idurar/idurar-erp-crm
        # Vite frontend + Express backend with dotenv configuration
        "name": "idurar_erp_crm",
        "github": "idurar/idurar-erp-crm",
        "description": "IDURAR ERP CRM - Vite frontend + Express backend with MongoDB",
        "project_name": "idurar-erp-crm",
        "metadata": {
            "framework": "MERN Stack",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 8888,  # Common port for this project
            "frontend_port": 5173,  # Vite default
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": False,  # Use local MongoDB
            "database_env_var": "DATABASE",
            "build_command": "npm run build",
            "start_command": "node src/server.js",
            "entry_point": "src/server.js",
            "build_output": "dist",  # Vite uses dist/
        },
        "services": [
            {
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "port": 8888,
                "port_source": "env",
                "entry_point": "src/server.js",
                "env_file": "backend/.env",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            },
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "port": 5173,
                "port_source": "vite_default",
                "build_output": "dist",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            },
            {
                "name": "mongodb",
                "type": "database",
                "is_cloud": False,
                "docker_image": "mongo:latest",
                "port": 27017
            }
        ],
        "expected_checks": [
            ("backend_port", "8888", True, "Backend should expose port 8888"),
            ("frontend_build_path", "/app/dist", True, "Vite frontend should use /app/dist"),
            ("backend_entry", "src/server.js", True, "Backend entry should be src/server.js"),
            ("has_db_container", "mongo:", True, "Should have mongo service (local DB)"),
            ("env_file", "env_file", True, "Should have env_file directive for backend"),
        ]
    },
    {
        # Project 3: Next.js Fullstack App
        # SSR with Next.js - common pattern
        "name": "nextjs_fullstack",
        "github": "example/nextjs-fullstack",
        "description": "Next.js 14 fullstack app with MongoDB",
        "project_name": "nextjs-app",
        "metadata": {
            "framework": "Next.js",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "frontend_port": 3000,
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": True,
            "database_env_var": "MONGODB_URI",
            "build_command": "npm run build",
            "start_command": "npm start",
            "build_output": ".next",
        },
        "services": [
            {
                "name": "app",
                "path": ".",
                "type": "frontend",
                "port": 3000,
                "port_source": "next_default",
                "build_output": ".next",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            }
        ],
        "expected_checks": [
            ("next_port", "3000", True, "Next.js should expose port 3000"),
            ("next_build", ".next", True, "Should reference .next directory"),
            ("npm_start", "npm", True, "Should use npm start for Next.js"),
            ("no_db_container", "mongo:", False, "Should NOT have mongo service (cloud DB)"),
        ]
    },
    {
        # Project 4: Express API Only (Backend-only)
        # No frontend, just REST API
        "name": "express_api_only",
        "github": "example/express-rest-api",
        "description": "Express.js REST API with MongoDB - backend only",
        "project_name": "express-api",
        "metadata": {
            "framework": "Express.js",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 5000,
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": True,
            "database_env_var": "MONGODB_URI",
            "start_command": "node server.js",
            "entry_point": "server.js",
        },
        "services": [
            {
                "name": "api",
                "path": ".",
                "type": "backend",
                "port": 5000,
                "port_source": "source",
                "entry_point": "server.js",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            }
        ],
        "expected_checks": [
            ("api_port", "5000", True, "API should expose port 5000"),
            ("entry_point", "server.js", True, "Entry point should be server.js"),
            ("no_db_container", "mongo:", False, "Should NOT have mongo service (cloud DB)"),
            ("no_frontend", "frontend", False, "Should NOT have frontend service"),
            ("single_service", "services:", True, "Should have services section"),
        ]
    },
    {
        # Project 5: TypeScript MERN with PostgreSQL
        # TypeScript backend with compiled output
        "name": "ts_mern_postgres",
        "github": "example/typescript-mern-postgres",
        "description": "TypeScript MERN Stack with PostgreSQL database",
        "project_name": "ts-mern-app",
        "metadata": {
            "framework": "MERN Stack",
            "language": "TypeScript",
            "runtime": "node:20-alpine",
            "backend_port": 3001,
            "frontend_port": 5173,
            "database": "PostgreSQL",
            "database_port": 5432,
            "database_is_cloud": False,
            "database_env_var": "DATABASE_URL",
            "build_command": "npm run build",
            "start_command": "node dist/index.js",
            "entry_point": "dist/index.js",
            "build_output": "dist",
        },
        "services": [
            {
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "port": 3001,
                "port_source": "source",
                "entry_point": "dist/index.js",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            },
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "port": 5173,
                "port_source": "vite_default",
                "build_output": "dist",
                "package_manager": {"manager": "npm", "has_lockfile": True}
            },
            {
                "name": "postgres",
                "type": "database",
                "is_cloud": False,
                "docker_image": "postgres:15-alpine",
                "port": 5432
            }
        ],
        "expected_checks": [
            ("backend_port", "3001", True, "Backend should expose port 3001"),
            ("ts_compiled", "dist/index.js", True, "Should use compiled TypeScript entry"),
            ("postgres_service", "postgres:", True, "Should have postgres service"),
            ("postgres_image", "postgres:15", True, "Should use postgres:15 image"),
            ("pg_env", "POSTGRES_PASSWORD", True, "PostgreSQL should have POSTGRES_PASSWORD"),
        ]
    }
]


def check_response(response: str, checks: list) -> dict:
    """
    Validate LLM response against expected checks.
    
    Each check is: (check_id, pattern, should_exist, description)
    """
    results = {"passed": [], "failed": [], "details": {}}
    
    for check_id, pattern, should_exist, description in checks:
        pattern_found = pattern.lower() in response.lower()
        
        if should_exist:
            # Pattern SHOULD be present
            if pattern_found:
                results["passed"].append(check_id)
                results["details"][check_id] = f"[PASS] {description}"
            else:
                results["failed"].append(check_id)
                results["details"][check_id] = f"[FAIL] {description} - Expected '{pattern}' NOT found"
        else:
            # Pattern should NOT be present
            if not pattern_found:
                results["passed"].append(check_id)
                results["details"][check_id] = f"[PASS] {description}"
            else:
                results["failed"].append(check_id)
                results["details"][check_id] = f"[FAIL] {description} - Found '{pattern}' but should NOT be present"
    
    return results


def extract_issues(response: str) -> list:
    """Extract common issues from LLM response."""
    issues = []
    
    # Check for placeholder text
    if "# REPLACE" in response or "# TODO" in response:
        issues.append("Contains placeholder comments")
    
    # Check for variable syntax that wasn't replaced
    if "${" in response or "{{" in response:
        issues.append("Contains unreplaced template variables")
    
    # Check for incorrect defaults
    if re.search(r"EXPOSE 3000", response) and "3001" in str(response):
        issues.append("May be using hardcoded port 3000 instead of metadata")
    
    # Check for outdated node versions
    if "node:14" in response or "node:16" in response:
        issues.append("Using outdated Node.js version instead of metadata.runtime")
    
    return issues


def test_project(project: dict, verbose: bool = True) -> dict:
    """Test LLM Docker generation for a single project."""
    print(f"\n{'='*70}")
    print(f"PROJECT: {project['name']}")
    print(f"GitHub: {project['github']}")
    print(f"Description: {project['description']}")
    print("-" * 70)
    
    # Build the message for LLM
    file_tree = f"""{project['project_name']}/
    {'backend/' if any(s.get('path') == 'backend' for s in project['services']) else ''}
        package.json
        server.js
    {'frontend/' if any(s.get('type') == 'frontend' for s in project['services']) else ''}
        package.json
        src/
    .env
    """
    
    message = build_deploy_message(
        project_name=project["project_name"],
        metadata=project["metadata"],
        dockerfiles=[],
        compose_files=[],
        file_tree=file_tree,
        user_message="Generate Docker configuration files for this project",
        logs=None,
        extra_instructions=None,
        services=project["services"],
        mode="GENERATE_MISSING"
    )
    
    if verbose:
        print(f"Prompt length: {len(message)} chars")
        print(f"Services: {len(project['services'])}")
    
    # Call LLM
    print("\nCalling LLM...")
    start_time = time.time()
    
    try:
        response = call_llama([
            {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ])
        
        elapsed = time.time() - start_time
        
        if response.startswith("ERROR:"):
            print(f"LLM Error: {response}")
            return {
                "project": project["name"],
                "status": "ERROR",
                "error": response
            }
        
        print(f"Response time: {elapsed:.1f}s")
        print(f"Response length: {len(response)} chars")
        
        # Validate response
        check_results = check_response(response, project["expected_checks"])
        issues = extract_issues(response)
        
        # Print results
        print("\nValidation Results:")
        for check_id, detail in check_results["details"].items():
            print(f"  {detail}")
        
        if issues:
            print("\nDetected Issues:")
            for issue in issues:
                print(f"  - {issue}")
        
        # Show response snippets
        if verbose:
            print(f"\n--- LLM Response (first 800 chars) ---")
            print(response[:800])
            print("..." if len(response) > 800 else "")
        
        return {
            "project": project["name"],
            "status": "COMPLETE",
            "passed": len(check_results["passed"]),
            "failed": len(check_results["failed"]),
            "total": len(project["expected_checks"]),
            "issues": issues,
            "response_length": len(response),
            "time_seconds": elapsed,
            "full_response": response
        }
        
    except Exception as e:
        import traceback
        print(f"Exception: {e}")
        return {
            "project": project["name"],
            "status": "EXCEPTION",
            "error": str(e),
            "traceback": traceback.format_exc()[:500]
        }


def run_all_tests(verbose: bool = True) -> list:
    """Run tests for all MERN projects."""
    print("=" * 80)
    print("LLM DOCKER GENERATION - REAL GITHUB MERN PROJECTS TEST")
    print("=" * 80)
    print(f"Testing {len(MERN_PROJECTS)} projects...")
    
    results = []
    total_passed = 0
    total_failed = 0
    total_checks = 0
    
    for project in MERN_PROJECTS:
        result = test_project(project, verbose=verbose)
        results.append(result)
        
        if result["status"] == "COMPLETE":
            total_passed += result["passed"]
            total_failed += result["failed"]
            total_checks += result["total"]
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Projects tested: {len(MERN_PROJECTS)}")
    print(f"Total checks: {total_checks}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total_checks > 0:
        rate = total_passed / total_checks * 100
        print(f"Success rate: {rate:.1f}%")
        
        if rate >= 90:
            print("\n>>> LLM handles real MERN projects WELL <<<")
        elif rate >= 70:
            print("\n>>> Some improvements may be needed <<<")
        else:
            print("\n>>> Prompt improvements needed <<<")
    
    # Per-project summary
    print("\n" + "-" * 40)
    print("PER-PROJECT RESULTS:")
    for r in results:
        if r["status"] == "COMPLETE":
            pct = r["passed"] / r["total"] * 100 if r["total"] > 0 else 0
            status = "PASS" if pct >= 80 else "PARTIAL" if pct >= 50 else "FAIL"
            print(f"  [{status}] {r['project']}: {r['passed']}/{r['total']} ({pct:.0f}%) in {r.get('time_seconds', 0):.1f}s")
        else:
            print(f"  [ERROR] {r['project']}: {r.get('error', 'Unknown error')[:50]}")
    
    return results


def save_results(results: list, output_file: str = "llm_mern_test_results.json"):
    """Save test results to JSON file."""
    # Remove full_response from results for cleaner output
    clean_results = []
    for r in results:
        clean = {k: v for k, v in r.items() if k != "full_response"}
        clean_results.append(clean)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(clean_results, f, indent=2)
    
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test LLM Docker generation with real MERN projects")
    parser.add_argument("-v", "--verbose", action="store_true", default=True, help="Show verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (minimal output)")
    parser.add_argument("-s", "--save", action="store_true", default=True, help="Save results to JSON")
    parser.add_argument("-p", "--project", type=str, help="Test specific project by name")
    
    args = parser.parse_args()
    
    if args.quiet:
        args.verbose = False
    
    if args.project:
        # Test single project
        matching = [p for p in MERN_PROJECTS if args.project.lower() in p["name"].lower()]
        if matching:
            result = test_project(matching[0], verbose=args.verbose)
            if args.save:
                save_results([result])
        else:
            print(f"Project '{args.project}' not found. Available: {[p['name'] for p in MERN_PROJECTS]}")
    else:
        # Test all projects
        results = run_all_tests(verbose=args.verbose)
        if args.save:
            save_results(results)
