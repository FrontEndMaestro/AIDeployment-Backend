"""
Detailed analysis of failing LLM tests to understand what's lacking.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_real_mern_llm import MERN_PROJECTS, check_response
from app.LLM.docker_deploy_agent import build_deploy_message, DOCKER_DEPLOY_SYSTEM_PROMPT
from app.LLM.llm_client import call_llama

def analyze_project(project):
    print("=" * 70)
    print(f"DETAILED ANALYSIS: {project['name']}")
    print(f"GitHub: {project['github']}")
    print("=" * 70)
    
    file_tree = f"""{project['project_name']}/
    backend/
        package.json
        server.js
    frontend/
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
    
    print("\nSending to LLM...")
    response = call_llama([
        {"role": "system", "content": DOCKER_DEPLOY_SYSTEM_PROMPT},
        {"role": "user", "content": message}
    ])
    
    print("\n" + "=" * 70)
    print("FULL LLM RESPONSE:")
    print("=" * 70)
    print(response)
    
    print("\n" + "=" * 70)
    print("VALIDATION RESULTS:")
    print("=" * 70)
    
    checks = project["expected_checks"]
    for check_id, pattern, should_exist, description in checks:
        found = pattern.lower() in response.lower()
        if should_exist:
            status = "[PASS]" if found else "[FAIL]"
        else:
            status = "[PASS]" if not found else "[FAIL]"
        print(f"{status} {check_id}: {description}")
        if status == "[FAIL]":
            print(f"       Expected pattern: \"{pattern}\" (should_exist={should_exist})")
            print(f"       Pattern found in response: {found}")
    
    return response


if __name__ == "__main__":
    # Analyze the first project (project_mern_memories) which failed the most
    project = MERN_PROJECTS[0]
    analyze_project(project)
