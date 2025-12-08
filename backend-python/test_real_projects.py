"""Test detection on REAL uploaded projects"""
import sys
import os
sys.path.insert(0, '.')

from app.utils.detector import detect_framework

BASE = 'uploads/user_abdulahadabbassi2@gmail.com/extracted'

projects = [
    # (project_id, project_folder)
    ("6936a751db124936ffee4d35", "react-job-portal-main"),
    ("69348ddbf77662b34a43c036", "idurar-erp-crm-master"),
    ("6936a785db124936ffee4d36", "project-management-master"),
    ("692d81872ac6786ca08b6071", "MERN_Notes_App"),
]

print("="*70)
print("REAL-WORLD DETECTION TEST")
print("="*70)

for project_id, folder in projects:
    path = os.path.join(BASE, f"project-{project_id}", folder)
    
    if not os.path.exists(path):
        print(f"\n[SKIP] {folder} - path not found")
        continue
    
    print(f"\n{'='*60}")
    print(f"PROJECT: {folder}")
    print(f"{'='*60}")
    
    try:
        result = detect_framework(path, use_ml=False)
        
        print(f"\n  Framework: {result.get('framework')}")
        print(f"  Language: {result.get('language')}")
        print(f"  Backend Port: {result.get('backend_port')}")
        print(f"  Frontend Port: {result.get('frontend_port')}")
        print(f"  Database: {result.get('database')}")
        print(f"  Database Port: {result.get('database_port')}")
        print(f"  Start Command: {result.get('start_command')}")
        print(f"  Build Output: {result.get('services', [{}])[0].get('build_output') if result.get('services') else 'N/A'}")
        
        # Validation
        issues = []
        if result.get('backend_port') == 3000 and folder == "react-job-portal-main":
            issues.append("Backend port should be 4000 (from .env), not 3000")
        if result.get('database_port') == result.get('backend_port'):
            issues.append(f"Database port ({result.get('database_port')}) same as backend port!")
        
        if issues:
            print(f"\n  ⚠ ISSUES:")
            for i in issues:
                print(f"    - {i}")
        else:
            print(f"\n  ✓ Detection looks correct")
            
    except Exception as e:
        print(f"  [ERROR] {e}")

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
