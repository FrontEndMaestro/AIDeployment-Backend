"""Debug fullstack detection"""
import sys
sys.path.insert(0, '.')
import os

from app.utils.detector import _detect_fullstack_structure, _read_env_key_values

project_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-69369f75c6b8eec74911b96f/react-job-portal-main'

print("="*60)
print("1. CHECK IF PROJECT PATH EXISTS")
print("="*60)
print(f"Project path: {project_path}")
print(f"Exists: {os.path.exists(project_path)}")
print(f"Contents: {os.listdir(project_path) if os.path.exists(project_path) else 'N/A'}")

print("\n" + "="*60)
print("2. FULLSTACK STRUCTURE DETECTION")
print("="*60)
fullstack = _detect_fullstack_structure(project_path)
for k, v in fullstack.items():
    print(f"  {k}: {v}")

print("\n" + "="*60)
print("3. ROOT .ENV READING")
print("="*60)
root_env = _read_env_key_values(project_path)
print(f"Root .env keys: {root_env}")

print("\n" + "="*60)
print("4. BACKEND .ENV READING")
print("="*60)
backend_path = fullstack.get("backend_path")
if backend_path:
    backend_env = _read_env_key_values(backend_path)
    print(f"Backend path: {backend_path}")
    print(f"Backend .env exists: {os.path.exists(os.path.join(backend_path, '.env'))}")
    print(f"Backend .env keys: {backend_env}")
else:
    print("No backend path detected")

print("\n" + "="*60)
print("5. CHECK ACTUAL .ENV FILE")
print("="*60)
env_path = os.path.join(project_path, 'backend', '.env')
print(f"Checking: {env_path}")
print(f"Exists: {os.path.exists(env_path)}")
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        content = f.read()
    print(f"Content:\n{content[:500]}")
