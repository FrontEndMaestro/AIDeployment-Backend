"""
Test script to verify monorepo detection and LLM prompt for MERN-eCommerce-main.
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.detector import detect_framework, _detect_fullstack_structure, infer_services
from app.LLM.docker_deploy_agent import build_deploy_message

# Path to the project
PROJECT_PATH = r"C:\Users\abdul\Downloads\devops-autopilot\devops-autopilot\backend-python\uploads\user_abdulahadabbassi2@gmail.com\extracted\project-693998a41a9cb800f55a57f4\MERN-eCommerce-main"

def test_monorepo_detection():
    print("=" * 60)
    print("TESTING MONOREPO DETECTION")
    print("=" * 60)
    
    # Check if path exists
    if not os.path.exists(PROJECT_PATH):
        print(f"ERROR: Project path not found: {PROJECT_PATH}")
        return
    
    # Test _detect_fullstack_structure
    print("\n1. Testing _detect_fullstack_structure()...")
    structure = _detect_fullstack_structure(PROJECT_PATH)
    print(f"   Result: {structure}")
    
    # Test detect_framework (full detection)
    print("\n2. Testing detect_framework()...")
    metadata = detect_framework(PROJECT_PATH, use_ml=False)
    
    print(f"\n   Services detected: {len(metadata.get('services', []))}")
    for svc in metadata.get('services', []):
        print(f"   - {svc.get('name')}: type={svc.get('type')}, path={svc.get('path')}")
        print(f"     has_own_package_json={svc.get('has_own_package_json')}")
        print(f"     entry_point={svc.get('entry_point')}")
        print(f"     env_file={svc.get('env_file')}")
        print(f"     port={svc.get('port')}")
    
    # Test build_deploy_message
    print("\n3. Testing build_deploy_message()...")
    services = metadata.get('services', [])
    message = build_deploy_message(
        project_name="MERN-eCommerce-main",
        metadata=metadata,
        dockerfiles=[],
        compose_files=[],
        file_tree=None,
        user_message="generate",
        services=services,
        mode="GENERATE_MISSING"
    )
    
    # Write full message to file for inspection
    with open("test_monorepo_output.txt", "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("SERVICES DETECTED:\n")
        f.write("=" * 60 + "\n")
        for svc in services:
            f.write(f"\n{svc}\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write("FULL LLM MESSAGE:\n")
        f.write("=" * 60 + "\n")
        f.write(message)
    
    print("\n   Output written to: test_monorepo_output.txt")
    
    # Call actual LLM
    print("\n4. Calling actual LLM...")
    from app.LLM.docker_deploy_agent import run_docker_deploy_chat
    
    llm_response = run_docker_deploy_chat(
        project_name="mern-ecommerce-main",
        metadata=metadata,
        dockerfiles=[],
        compose_files=[],
        file_tree=None,
        user_message="generate",
        services=services
    )
    
    # Write LLM response to file
    with open("test_monorepo_llm_response.txt", "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("LLM RESPONSE:\n")
        f.write("=" * 60 + "\n")
        f.write(llm_response)
    
    print("\n   LLM response written to: test_monorepo_llm_response.txt")
    
    # Show key parts
    print("\n   Checking if LLM used correct build context...")
    if "build: ." in llm_response.lower() or 'build: "./"' in llm_response:
        print("   ✅ LLM used root as build context")
    elif "build: ./backend" in llm_response.lower():
        print("   ❌ LLM used ./backend as build context (WRONG for monorepo!)")
    
    if 'cmd ["node", "backend/' in llm_response.lower() or "backend/server.js" in llm_response:
        print("   ✅ LLM used backend/entry_point in CMD")
    elif 'cmd ["node", "server.js' in llm_response.lower():
        print("   ⚠️ LLM used just server.js in CMD (may need backend/ prefix)")

if __name__ == "__main__":
    test_monorepo_detection()
