"""Debug the actual port detection flow"""
import sys
sys.path.insert(0, '.')

from app.utils.detector import detect_ports_for_project, detect_databases

project_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-69369f75c6b8eec74911b96f/react-job-portal-main'
backend_path = project_path + '/backend'
frontend_path = project_path + '/frontend'

print("="*60)
print("TESTING detect_ports_for_project FROM detector.py")
print("="*60)

# Test the actual function used by the app
result = detect_ports_for_project(
    project_path=project_path,
    language="JavaScript",
    framework="Express.js",
    base_port=None
)

print("\nResult from detect_ports_for_project():")
for k, v in result.items():
    print(f"  {k}: {v}")

print("\n" + "="*60)
print("TESTING detect_databases FROM detector.py")
print("="*60)

db_result = detect_databases(
    project_path=project_path,
    dependencies=["express", "mongoose", "cors"],
    env_vars=["PORT", "MONGO_URI"]
)

print("\nResult from detect_databases():")
for k, v in db_result.items():
    print(f"  {k}: {v}")
