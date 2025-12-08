"""
Test script for LLM Docker generation with different MERN project configurations.
Calls the actual LLM and evaluates the generated Dockerfiles.
"""
import sys
import os
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.LLM.docker_deploy_agent import run_docker_deploy_chat, build_deploy_message, DOCKER_DEPLOY_SYSTEM_PROMPT
from app.LLM.llm_client import call_llama


# Test scenarios representing different MERN project types
TEST_SCENARIOS = [
    {
        "name": "Standard MERN - CRA Frontend + Express Backend",
        "project_name": "react-job-portal",
        "metadata": {
            "framework": "MERN Stack",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 4000,
            "frontend_port": 3000,
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": True,  # MongoDB Atlas
            "database_env_var": "MONGO_URI",
            "build_command": "npm run build",
            "start_command": "node server.js",
            "entry_point": "server.js",
            "build_output": "build",  # CRA uses build/
        },
        "services": [
            {
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "port": 4000,
                "port_source": "env"
            },
            {
                "name": "frontend", 
                "path": "frontend",
                "type": "frontend",
                "port": 3000,
                "port_source": "cra_default",
                "build_output": "build"
            }
        ],
        "expected_checks": [
            ("backend_port", "EXPOSE 4000", "Backend should expose port 4000"),
            ("frontend_build", "/app/build", "Frontend should use /app/build for CRA"),
            ("no_db_container", "mongo:", "Should NOT have mongo service (cloud DB)"),
            ("serve_spa", "serve", "Frontend should use serve for SPA"),
        ]
    },
    {
        "name": "Vite Frontend + Express Backend with Local MongoDB",
        "project_name": "idurar-erp",
        "metadata": {
            "framework": "MERN Stack",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 8888,
            "frontend_port": 5173,
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": False,  # Local MongoDB
            "database_env_var": "MONGO_URI",
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
                "port_source": "env"
            },
            {
                "name": "frontend",
                "path": "frontend", 
                "type": "frontend",
                "port": 5173,
                "port_source": "vite_default",
                "build_output": "dist"
            },
            {
                "name": "mongodb",
                "type": "database",
                "is_cloud": False,
                "docker_image": "mongo:latest"
            }
        ],
        "expected_checks": [
            ("backend_port", "8888", "Backend should expose port 8888"),
            ("frontend_build", "/app/dist", "Frontend should use /app/dist for Vite"),
            ("has_db_container", "mongo:", "Should have mongo service (local DB)"),
            ("entry_point", "src/server.js", "Should use correct entry point"),
        ]
    },
    {
        "name": "Next.js with Static Export",
        "project_name": "nextjs-blog",
        "metadata": {
            "framework": "Next.js",
            "language": "JavaScript",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "frontend_port": 3000,
            "build_command": "npm run build",
            "start_command": "npm start",
            "build_output": "out",  # next export uses out/
        },
        "services": [
            {
                "name": "frontend",
                "path": ".",
                "type": "frontend",
                "port": 3000,
                "port_source": "next_default",
                "build_output": "out"
            }
        ],
        "expected_checks": [
            ("frontend_build", "/app/out", "Should use /app/out for Next.js export"),
            ("serve_spa", "serve", "Should use serve for static files"),
        ]
    },
    {
        "name": "Express Backend Only (API)",
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
            "start_command": "node index.js",
            "entry_point": "index.js",
        },
        "services": [
            {
                "name": "api",
                "path": ".",
                "type": "backend",
                "port": 5000,
                "port_source": "source"
            }
        ],
        "expected_checks": [
            ("backend_port", "5000", "Should expose port 5000"),
            ("entry_point", "index.js", "Should use index.js as entry"),
            ("no_db_container", "mongo:", "Should NOT have mongo (cloud DB)"),
        ]
    },
    {
        "name": "TypeScript Backend + Vite Frontend",
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
                "port_source": "source"
            },
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "port": 5173,
                "port_source": "vite_default",
                "build_output": "dist"
            },
            {
                "name": "postgres",
                "type": "database",
                "is_cloud": False,
                "docker_image": "postgres:15-alpine"
            }
        ],
        "expected_checks": [
            ("backend_port", "3001", "Should expose port 3001"),
            ("has_db_container", "postgres:", "Should have postgres service"),
            ("ts_build", "dist/index.js", "Should use compiled TypeScript"),
        ]
    }
]


def check_llm_output(output: str, checks: list) -> dict:
    """Evaluate LLM output against expected checks."""
    results = {"passed": [], "failed": [], "details": {}}
    
    for check_id, pattern, description in checks:
        if check_id.startswith("no_"):
            # Negative check - pattern should NOT be present
            if pattern.lower() not in output.lower():
                results["passed"].append(check_id)
                results["details"][check_id] = f"[PASS] {description}"
            else:
                results["failed"].append(check_id)
                results["details"][check_id] = f"[FAIL] {description} - Found '{pattern}' but should NOT be present"
        else:
            # Positive check - pattern should be present
            if pattern.lower() in output.lower():
                results["passed"].append(check_id)
                results["details"][check_id] = f"[PASS] {description}"
            else:
                results["failed"].append(check_id)
                results["details"][check_id] = f"[FAIL] {description} - Expected '{pattern}' not found"
    
    return results


def extract_dockerfile_issues(output: str) -> list:
    """Extract common issues from LLM output."""
    issues = []
    
    # Check for placeholder comments
    if "# REPLACE" in output or "# TODO" in output or "# UPDATE" in output:
        issues.append("Contains placeholder comments that should be replaced with actual values")
    
    # Check for wrong defaults
    wrong_patterns = [
        (r"EXPOSE 3000", "Port 3000 may be hardcoded instead of using metadata"),
        (r"node:14", "Using outdated Node.js 14 instead of metadata.runtime"),
        (r"node:16", "Using Node.js 16 instead of metadata.runtime"),
        (r"/app/dist.*CRA\|react-scripts", "Using /app/dist for CRA (should be /app/build)"),
        (r"nginx", "Using nginx instead of serve for SPA"),
    ]
    
    for pattern, issue in wrong_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            issues.append(issue)
    
    # Check for missing verification header
    if "# VERIFICATION:" not in output:
        issues.append("Missing VERIFICATION comment header")
    
    return issues


def run_llm_test(scenario: dict) -> dict:
    """Run a single LLM test scenario."""
    print(f"\n{'='*60}")
    print(f"TEST: {scenario['name']}")
    print(f"Project: {scenario['project_name']}")
    print("-" * 60)
    
    # Build the message (without actually calling LLM yet to see prompt)
    message = build_deploy_message(
        project_name=scenario["project_name"],
        metadata=scenario["metadata"],
        dockerfiles=[],
        compose_files=[],
        file_tree="project/\n  backend/\n    package.json\n    server.js\n  frontend/\n    package.json\n    src/",
        user_message="Generate Docker configuration files for this project",
        logs=None,
        extra_instructions=None,
        services=scenario.get("services", []),
        mode="GENERATE_MISSING"
    )
    
    print(f"\nPrompt length: {len(message)} chars")
    print(f"Services: {len(scenario.get('services', []))}")
    
    # Call the LLM
    print("\nCalling LLM...")
    try:
        response = call_llama([
            {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ])
        
        if response.startswith("ERROR:"):
            print(f"LLM Error: {response}")
            return {
                "scenario": scenario["name"],
                "status": "ERROR",
                "error": response,
                "checks": None
            }
        
        print(f"Response length: {len(response)} chars")
        
        # Check for expected patterns
        check_results = check_llm_output(response, scenario["expected_checks"])
        
        # Extract any issues
        issues = extract_dockerfile_issues(response)
        
        # Print results
        print("\nCheck Results:")
        for check_id, detail in check_results["details"].items():
            print(f"  {detail}")
        
        if issues:
            print("\nDetected Issues:")
            for issue in issues:
                print(f"  - {issue}")
        
        return {
            "scenario": scenario["name"],
            "status": "COMPLETE",
            "passed": len(check_results["passed"]),
            "failed": len(check_results["failed"]),
            "total": len(scenario["expected_checks"]),
            "issues": issues,
            "response_preview": response[:500] + "..." if len(response) > 500 else response
        }
        
    except Exception as e:
        print(f"Exception: {e}")
        return {
            "scenario": scenario["name"],
            "status": "EXCEPTION",
            "error": str(e)
        }


def run_all_tests():
    """Run all test scenarios."""
    print("=" * 80)
    print("LLM DOCKER GENERATION TEST")
    print("=" * 80)
    
    results = []
    total_passed = 0
    total_failed = 0
    total_checks = 0
    
    for scenario in TEST_SCENARIOS:
        result = run_llm_test(scenario)
        results.append(result)
        
        if result["status"] == "COMPLETE":
            total_passed += result["passed"]
            total_failed += result["failed"]
            total_checks += result["total"]
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Scenarios tested: {len(TEST_SCENARIOS)}")
    print(f"Total checks: {total_checks}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    if total_checks > 0:
        print(f"Success rate: {total_passed/total_checks*100:.1f}%")
    
    # Collect all issues
    all_issues = []
    for r in results:
        if r.get("issues"):
            all_issues.extend(r["issues"])
    
    if all_issues:
        print("\n" + "-" * 40)
        print("COMMON ISSUES ACROSS ALL TESTS:")
        for issue in set(all_issues):
            count = all_issues.count(issue)
            print(f"  [{count}x] {issue}")
    
    return results


if __name__ == "__main__":
    results = run_all_tests()
    
    # Save results to file
    with open("llm_test_results.txt", "w", encoding="utf-8") as f:
        f.write("LLM DOCKER GENERATION TEST RESULTS\n")
        f.write("=" * 60 + "\n\n")
        
        for r in results:
            f.write(f"Scenario: {r['scenario']}\n")
            f.write(f"Status: {r['status']}\n")
            if r['status'] == 'COMPLETE':
                f.write(f"Passed: {r['passed']}/{r['total']}\n")
                if r.get('issues'):
                    f.write("Issues:\n")
                    for issue in r['issues']:
                        f.write(f"  - {issue}\n")
                f.write(f"\nResponse Preview:\n{r.get('response_preview', 'N/A')}\n")
            elif r.get('error'):
                f.write(f"Error: {r['error']}\n")
            f.write("\n" + "-" * 40 + "\n\n")
    
    print("\n\nResults saved to llm_test_results.txt")
