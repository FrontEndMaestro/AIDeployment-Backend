"""
Comprehensive MERN Detection Flow Audit
Tests all critical paths through the detection logic
"""
import sys
import os
import json
import tempfile
import shutil
sys.path.insert(0, '.')

from app.utils.detector import (
    detect_framework,
    _detect_fullstack_structure,
    detect_ports_for_project,
    detect_databases,
    heuristic_language_detection,
    heuristic_framework_detection,
    find_project_root
)
from app.utils.command_extractor import (
    extract_nodejs_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info
)

class TestScenario:
    def __init__(self, name):
        self.name = name
        self.temp_dir = None
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def create_temp_project(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mern_test_")
        return self.temp_dir
    
    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def check(self, description, condition, expected=None, actual=None):
        if condition:
            print(f"  [PASS] {description}")
            self.passed += 1
        else:
            msg = f"  [FAIL] {description}"
            if expected is not None:
                msg += f" (expected={expected}, actual={actual})"
            print(msg)
            self.failed += 1
            self.errors.append(description)


def test_fullstack_mern_with_env():
    """Test: Standard MERN fullstack with backend/.env containing PORT=5000"""
    test = TestScenario("Fullstack MERN with backend .env PORT")
    root = test.create_temp_project()
    
    try:
        # Create structure: root/backend + root/frontend
        backend = os.path.join(root, "backend")
        frontend = os.path.join(root, "frontend")
        os.makedirs(backend)
        os.makedirs(frontend)
        
        # Backend package.json
        with open(os.path.join(backend, "package.json"), "w") as f:
            json.dump({
                "name": "backend",
                "scripts": {"start": "node server.js", "dev": "nodemon server.js"},
                "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"}
            }, f)
        
        # Backend .env with PORT=5000
        with open(os.path.join(backend, ".env"), "w") as f:
            f.write("PORT=5000\nMONGO_URI=mongodb://localhost:27017/test\n")
        
        # Backend server.js
        with open(os.path.join(backend, "server.js"), "w") as f:
            f.write("const express = require('express');\napp.listen(process.env.PORT);\n")
        
        # Frontend package.json (Vite)
        with open(os.path.join(frontend, "package.json"), "w") as f:
            json.dump({
                "name": "frontend",
                "scripts": {"dev": "vite", "build": "vite build"},
                "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"}
            }, f)
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Test 1: Fullstack detection
        fs = _detect_fullstack_structure(root)
        test.check("Detects fullstack structure", fs["is_fullstack"] == True)
        test.check("Finds backend folder", fs["has_backend"] == True)
        test.check("Finds frontend folder", fs["has_frontend"] == True)
        
        # Test 2: Port detection
        ports = detect_ports_for_project(root, "JavaScript", "Express.js", None)
        test.check("Backend port is 5000 from .env", 
                  ports["backend_port"] == 5000,
                  expected=5000, actual=ports["backend_port"])
        test.check("Frontend port is 5173 (Vite default)", 
                  ports["frontend_port"] == 5173,
                  expected=5173, actual=ports["frontend_port"])
        
        # Test 3: Database detection
        db = detect_databases(root, ["express", "mongoose"], ["PORT", "MONGO_URI"])
        test.check("Detects MongoDB", db["primary"] == "MongoDB", 
                  expected="MongoDB", actual=db["primary"])
        test.check("Database port is 27017", db["port"] == 27017,
                  expected=27017, actual=db["port"])
        
        # Test 4: Command extraction
        cmds = extract_nodejs_commands(backend)
        test.check("Start command is node server.js", 
                  cmds["start_command"] == "node server.js",
                  expected="node server.js", actual=cmds["start_command"])
        test.check("Entry point is server.js",
                  cmds["entry_point"] == "server.js",
                  expected="server.js", actual=cmds["entry_point"])
        
    finally:
        test.cleanup()
    
    return test


def test_cra_frontend_express_backend():
    """Test: CRA frontend + Express backend with cloud MongoDB"""
    test = TestScenario("CRA Frontend + Express Backend (Cloud DB)")
    root = test.create_temp_project()
    
    try:
        backend = os.path.join(root, "server")
        frontend = os.path.join(root, "client")
        os.makedirs(backend)
        os.makedirs(frontend)
        
        # Backend with cloud MongoDB
        with open(os.path.join(backend, "package.json"), "w") as f:
            json.dump({
                "name": "api",
                "scripts": {"start": "node index.js"},
                "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"}
            }, f)
        
        with open(os.path.join(backend, ".env"), "w") as f:
            f.write("PORT=4000\nMONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/db\n")
        
        # CRA frontend
        with open(os.path.join(frontend, "package.json"), "w") as f:
            json.dump({
                "name": "client",
                "scripts": {"start": "react-scripts start", "build": "react-scripts build"},
                "dependencies": {"react": "^18.0.0", "react-scripts": "5.0.0"}
            }, f)
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Test fullstack detection
        fs = _detect_fullstack_structure(root)
        test.check("Detects fullstack (server/client)", fs["is_fullstack"] == True)
        
        # Test port detection
        ports = detect_ports_for_project(root, "JavaScript", "Express.js", None)
        test.check("Backend port is 4000", ports["backend_port"] == 4000,
                  expected=4000, actual=ports["backend_port"])
        test.check("Frontend port is 3000 (CRA default)", 
                  ports["frontend_port"] == 3000,
                  expected=3000, actual=ports["frontend_port"])
        
        # Test cloud DB detection
        db_info = extract_database_info(backend, "MongoDB")
        test.check("Detects cloud MongoDB", db_info["is_cloud"] == True,
                  expected=True, actual=db_info["is_cloud"])
        test.check("No container needed for cloud", db_info["needs_container"] == False,
                  expected=False, actual=db_info["needs_container"])
        
        # Test CRA build output
        cmds = extract_nodejs_commands(frontend)
        test.check("CRA build output is 'build'", cmds["build_output"] == "build",
                  expected="build", actual=cmds["build_output"])
        
    finally:
        test.cleanup()
    
    return test


def test_single_backend_no_frontend():
    """Test: Express backend only, no frontend folder"""
    test = TestScenario("Single Express Backend (No Frontend)")
    root = test.create_temp_project()
    
    try:
        # Just backend files at root
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({
                "name": "api-server",
                "main": "app.js",
                "scripts": {"start": "node app.js", "dev": "nodemon app.js"},
                "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"}
            }, f)
        
        with open(os.path.join(root, ".env"), "w") as f:
            f.write("PORT=8080\nDB_URL=mongodb://localhost:27017/mydb\n")
        
        with open(os.path.join(root, "app.js"), "w") as f:
            f.write("const app = require('express')();\napp.listen(8080);\n")
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Should NOT be fullstack
        fs = _detect_fullstack_structure(root)
        test.check("Not detected as fullstack", fs["is_fullstack"] == False)
        
        # Port from .env
        port_info = extract_port_from_project(root, "Express.js", "JavaScript")
        test.check("Port is 8080 from .env", port_info["port"] == 8080,
                  expected=8080, actual=port_info["port"])
        
        # Entry point from main field
        cmds = extract_nodejs_commands(root)
        test.check("Entry point is app.js", cmds["entry_point"] == "app.js",
                  expected="app.js", actual=cmds["entry_point"])
        
    finally:
        test.cleanup()
    
    return test


def test_typescript_backend():
    """Test: TypeScript Express backend with ts-node"""
    test = TestScenario("TypeScript Express Backend")
    root = test.create_temp_project()
    
    try:
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({
                "name": "ts-api",
                "scripts": {
                    "start": "ts-node src/index.ts",
                    "dev": "nodemon --exec ts-node src/index.ts",
                    "build": "tsc"
                },
                "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"},
                "devDependencies": {"typescript": "^5.0.0", "ts-node": "^10.0.0"}
            }, f)
        
        os.makedirs(os.path.join(root, "src"))
        with open(os.path.join(root, "src", "index.ts"), "w") as f:
            f.write("import express from 'express';\napp.listen(3001);\n")
        
        with open(os.path.join(root, ".env"), "w") as f:
            f.write("PORT=3001\n")
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Port detection should find 3001
        port_info = extract_port_from_project(root, "Express.js", "TypeScript")
        test.check("Port is 3001 from .env", port_info["port"] == 3001,
                  expected=3001, actual=port_info["port"])
        
        # Language detection
        lang, conf = heuristic_language_detection(root)
        test.check("Language is TypeScript or JavaScript", lang in ["TypeScript", "JavaScript"],
                  expected="TypeScript/JavaScript", actual=lang)
        
    finally:
        test.cleanup()
    
    return test


def test_nextjs_fullstack():
    """Test: Next.js with API routes (fullstack in one folder)"""
    test = TestScenario("Next.js Fullstack App")
    root = test.create_temp_project()
    
    try:
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({
                "name": "nextjs-app",
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start"
                },
                "dependencies": {"next": "^14.0.0", "react": "^18.0.0", "mongoose": "^7.0.0"}
            }, f)
        
        os.makedirs(os.path.join(root, "pages", "api"))
        with open(os.path.join(root, "pages", "api", "hello.js"), "w") as f:
            f.write("export default function handler(req, res) { res.json({}) }\n")
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Framework detection
        fw, conf = heuristic_framework_detection(root, "JavaScript")
        test.check("Framework is Next.js", fw == "Next.js",
                  expected="Next.js", actual=fw)
        
        # Build output for Next.js
        cmds = extract_nodejs_commands(root)
        test.check("Build output is .next", cmds["build_output"] == ".next",
                  expected=".next", actual=cmds["build_output"])
        
        # Port should be 3000 (Next.js default)
        frontend_port = extract_frontend_port(root)
        test.check("Frontend port is 3000 (Next.js default)", 
                  frontend_port["port"] == 3000,
                  expected=3000, actual=frontend_port["port"])
        
    finally:
        test.cleanup()
    
    return test


def test_nested_zip_structure():
    """Test: Nested folder from ZIP (project-main/actual-project)"""
    test = TestScenario("Nested ZIP Structure")
    root = test.create_temp_project()
    
    try:
        # Simulate: uploaded.zip extracts to project-main/
        nested = os.path.join(root, "my-project-main")
        os.makedirs(nested)
        
        with open(os.path.join(nested, "package.json"), "w") as f:
            json.dump({
                "name": "my-app",
                "scripts": {"start": "node server.js"},
                "dependencies": {"express": "^4.18.0"}
            }, f)
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Should find actual root
        actual_root = find_project_root(root, max_depth=3)
        test.check("Finds nested project root", actual_root == nested,
                  expected=nested, actual=actual_root)
        
    finally:
        test.cleanup()
    
    return test


def test_postgresql_database():
    """Test: Express with PostgreSQL instead of MongoDB"""
    test = TestScenario("Express with PostgreSQL")
    root = test.create_temp_project()
    
    try:
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({
                "name": "pg-api",
                "scripts": {"start": "node index.js"},
                "dependencies": {"express": "^4.18.0", "pg": "^8.11.0"}
            }, f)
        
        with open(os.path.join(root, ".env"), "w") as f:
            f.write("PORT=5000\nDATABASE_URL=postgresql://user:pass@localhost:5432/mydb\n")
        
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        
        # Database detection
        db = detect_databases(root, ["express", "pg"], ["PORT", "DATABASE_URL"])
        test.check("Detects PostgreSQL", db["primary"] == "PostgreSQL",
                  expected="PostgreSQL", actual=db["primary"])
        test.check("Database port is 5432", db["port"] == 5432,
                  expected=5432, actual=db["port"])
        
        # Backend port should NOT be confused with DB port
        port_info = extract_port_from_project(root, "Express.js", "JavaScript")
        test.check("Backend port is 5000 (not 5432)", port_info["port"] == 5000,
                  expected=5000, actual=port_info["port"])
        
    finally:
        test.cleanup()
    
    return test


def run_all_tests():
    """Run all test scenarios"""
    print("="*70)
    print("COMPREHENSIVE MERN DETECTION FLOW AUDIT")
    print("="*70)
    
    tests = [
        test_fullstack_mern_with_env,
        test_cra_frontend_express_backend,
        test_single_backend_no_frontend,
        test_typescript_backend,
        test_nextjs_fullstack,
        test_nested_zip_structure,
        test_postgresql_database,
    ]
    
    total_passed = 0
    total_failed = 0
    all_errors = []
    
    for test_fn in tests:
        try:
            result = test_fn()
            total_passed += result.passed
            total_failed += result.failed
            all_errors.extend(result.errors)
        except Exception as e:
            print(f"\n[ERROR] Test {test_fn.__name__} crashed: {e}")
            total_failed += 1
            all_errors.append(f"{test_fn.__name__}: {e}")
    
    # Summary
    print("\n" + "="*70)
    print("AUDIT SUMMARY")
    print("="*70)
    print(f"Total tests: {len(tests)}")
    print(f"Total checks: {total_passed + total_failed}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total_passed + total_failed > 0:
        rate = total_passed / (total_passed + total_failed) * 100
        print(f"Success rate: {rate:.1f}%")
        
        if all_errors:
            print(f"\nFailed checks:")
            for err in all_errors:
                print(f"  - {err}")
        
        if rate >= 95:
            print("\n✓ Detection flow is ROBUST for MERN projects")
        elif rate >= 85:
            print("\n⚠ Detection flow has minor issues")
        else:
            print("\n✗ Detection flow needs fixes")


if __name__ == "__main__":
    run_all_tests()
