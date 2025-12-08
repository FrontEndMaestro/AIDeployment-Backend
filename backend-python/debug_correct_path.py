"""Debug fullstack detection with CORRECT path"""
import sys
import os
sys.path.insert(0, '.')

from app.utils.detector import _detect_fullstack_structure, _read_env_key_values, detect_ports_for_project

# LATEST UPLOAD PATH
project_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-6936a14a609b7eea2f627972/react-job-portal-main'

print("="*60)
print("USING CORRECT PROJECT PATH")
print(f"Path: {project_path}")
print(f"Exists: {os.path.exists(project_path)}")
print("="*60)

if os.path.exists(project_path):
    print(f"\nContents: {os.listdir(project_path)}")
    
    print("\n" + "="*60)
    print("FULLSTACK DETECTION")
    print("="*60)
    fullstack = _detect_fullstack_structure(project_path)
    for k, v in fullstack.items():
        print(f"  {k}: {v}")
    
    print("\n" + "="*60)
    print("BACKEND .ENV READING")
    print("="*60)
    backend_path = fullstack.get("backend_path")
    if backend_path:
        backend_env = _read_env_key_values(backend_path)
        print(f"Backend .env keys: {backend_env}")
    else:
        print("No backend path detected")
    
    print("\n" + "="*60)
    print("DETECT_PORTS_FOR_PROJECT")
    print("="*60)
    ports = detect_ports_for_project(project_path, "JavaScript", "Express.js", None)
    for k, v in ports.items():
        print(f"  {k}: {v}")
else:
    print("PATH DOES NOT EXIST!")
