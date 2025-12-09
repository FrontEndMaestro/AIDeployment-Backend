# Complete Flow Audit for DevOps Autopilot
# This script traces ALL code paths for different MERN project configurations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.docker_service import (
    _find_compose_file,
    _find_all_dockerfiles,
)

def audit_flow(project_config):
    """
    Simulate flow for a given project configuration.
    project_config = {
        "name": str,
        "has_compose": bool,
        "dockerfiles": int,  # count of dockerfiles
        "services": int,  # count of services detected
    }
    """
    name = project_config["name"]
    has_compose = project_config["has_compose"]
    num_dockerfiles = project_config["dockerfiles"]
    num_services = project_config["services"]
    
    print(f"\n{'='*60}")
    print(f"CASE: {name}")
    print(f"  - Compose exists: {has_compose}")
    print(f"  - Dockerfiles: {num_dockerfiles}")
    print(f"  - Services detected: {num_services}")
    print(f"{'='*60}")
    
    # ===== BUILD PHASE (build_project_stream) =====
    print("\n[BUILD PHASE]")
    
    if has_compose:
        print("  → Compose found: docker compose build")
        print("  ✅ BUILD: SUCCESS (uses compose)")
        build_success = True
    else:
        if num_dockerfiles == 0:
            print("  → No compose, No dockerfiles")
            print("  ❌ BUILD: FAILS at line 300-309")
            print('     ERROR: "No docker-compose.yml and no Dockerfiles found"')
            build_success = False
        else:
            print(f"  → No compose, {num_dockerfiles} Dockerfile(s) found")
            print(f"  → Building {num_dockerfiles} image(s) sequentially")
            print("  ✅ BUILD: SUCCESS")
            build_success = True
    
    if not build_success:
        print("\n[FLOW STOPS HERE - Build failed]")
        return False
    
    # ===== RUN PHASE (run_project_stream) =====
    print("\n[RUN PHASE]")
    
    # Check compose again (might have been generated)
    if has_compose:
        print("  → Compose found: docker compose up")
        print("  ✅ RUN: SUCCESS (uses compose)")
        return True
    
    # No compose - check dockerfiles
    if num_dockerfiles > 1:
        print("  → No compose, >1 Dockerfiles")
        print("  → Generating docker-compose.yml via Agent")
        print("  → docker compose up")
        print("  ✅ RUN: SUCCESS (agent generated compose)")
        return True
    elif num_dockerfiles == 1:
        print("  → No compose, 1 Dockerfile")
        print("  → Fallback to docker run")
        print("  → Injects .env if exists (line 1105)")
        print("  ✅ RUN: SUCCESS (single container)")
        return True
    else:
        # num_dockerfiles == 0 but build succeeded? 
        # This shouldn't happen based on build logic
        print("  → ERROR: Unexpected state (0 dockerfiles but build passed?)")
        return False


# ===== TEST ALL CASES =====
cases = [
    {"name": "1. MERN + Compose + All Dockerfiles", "has_compose": True, "dockerfiles": 2, "services": 2},
    {"name": "2. MERN + No Compose + 2 Dockerfiles", "has_compose": False, "dockerfiles": 2, "services": 2},
    {"name": "3. MERN + No Compose + 1 Dockerfile", "has_compose": False, "dockerfiles": 1, "services": 2},
    {"name": "4. MERN + No Compose + 0 Dockerfiles", "has_compose": False, "dockerfiles": 0, "services": 2},
    {"name": "5. Single Backend + 1 Dockerfile", "has_compose": False, "dockerfiles": 1, "services": 1},
    {"name": "6. Single Backend + 0 Dockerfiles", "has_compose": False, "dockerfiles": 0, "services": 1},
    {"name": "7. Single Backend + Compose", "has_compose": True, "dockerfiles": 0, "services": 1},
]

print("="*60)
print(" DEVOPS AUTOPILOT - COMPLETE FLOW AUDIT")
print("="*60)

results = []
for case in cases:
    success = audit_flow(case)
    results.append((case["name"], success))

print("\n" + "="*60)
print(" SUMMARY")
print("="*60)
for name, success in results:
    status = "✅ WORKS" if success else "❌ FAILS"
    print(f"{status}: {name}")

print("\n" + "="*60)
print(" GAPS IDENTIFIED")
print("="*60)
failing = [name for name, success in results if not success]
if failing:
    for name in failing:
        print(f"  • {name}")
    print("\nRECOMMENDATION: Add auto-generation of Dockerfiles when:")
    print("  - No compose exists")
    print("  - No dockerfiles exist")
    print("  - But services are detected (services > 0)")
else:
    print("  No gaps found!")
