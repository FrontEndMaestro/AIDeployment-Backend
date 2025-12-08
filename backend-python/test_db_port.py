"""Test database port detection after fix"""
import sys
sys.path.insert(0, '.')

from app.utils.detector import detect_databases, detect_ports_for_project

project_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-6936a14a609b7eea2f627972/react-job-portal-main'

print("="*60)
print("PORT DETECTION (should show backend_port=4000)")
print("="*60)
ports = detect_ports_for_project(project_path, "JavaScript", "Express.js", None)
print(f"  backend_port: {ports['backend_port']}")
print(f"  frontend_port: {ports['frontend_port']}")

print()
print("="*60)
print("DATABASE DETECTION (should show port=27017)")
print("="*60)
db = detect_databases(
    project_path,
    dependencies=["express", "mongoose", "cors"],
    env_vars=["PORT", "MONGO_URI", "DB_URL"]
)
print(f"  database: {db['primary']}")
print(f"  database_port: {db['port']}")
