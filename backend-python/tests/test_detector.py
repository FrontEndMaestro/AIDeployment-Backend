"""
Unit Tests for DevOps AutoPilot - Framework and Language Detection Module

These tests verify the core functionality of the detector module which is responsible
for identifying programming languages, frameworks, databases, and project structure.

Author: Abdul Ahad Abbassi
Project: DevOps AutoPilot - AI Deployment Agent
Date: December 2024
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.detector import (
    heuristic_language_detection,
    heuristic_framework_detection,
    parse_dependencies_file,
    detect_docker_files,
    detect_env_variables,
    find_project_root,
    get_runtime_info,
    _detect_fullstack_structure,
)


class TestHeuristicLanguageDetection(unittest.TestCase):
    """Test cases for heuristic language detection algorithm."""

    def setUp(self):
        """Create a temporary directory for test projects."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def test_detect_python_by_extension(self):
        """TC001: Verify Python detection via .py file extension."""
        # Create Python file
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write("print('Hello World')")

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Python")
        self.assertGreater(confidence, 0.0)

    def test_detect_python_by_requirements_file(self):
        """TC002: Verify Python detection via requirements.txt config file."""
        # Create requirements.txt
        with open(os.path.join(self.test_dir, "requirements.txt"), "w") as f:
            f.write("flask==2.0.0\nrequests==2.28.0")

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Python")
        self.assertGreater(confidence, 0.3)

    def test_detect_javascript_by_package_json(self):
        """TC003: Verify JavaScript detection via package.json."""
        # Create package.json
        pkg_content = {"name": "test-app", "dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "JavaScript")
        self.assertGreater(confidence, 0.3)

    def test_detect_typescript_by_tsconfig(self):
        """TC004: Verify TypeScript detection via tsconfig.json."""
        # Create tsconfig.json and .ts file
        with open(os.path.join(self.test_dir, "tsconfig.json"), "w") as f:
            json.dump({"compilerOptions": {}}, f)
        with open(os.path.join(self.test_dir, "app.ts"), "w") as f:
            f.write("const x: string = 'hello';")

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "TypeScript")

    def test_detect_java_by_pom_xml(self):
        """TC005: Verify Java detection via pom.xml."""
        # Create pom.xml
        pom_content = """<?xml version="1.0"?>
        <project>
            <artifactId>test-app</artifactId>
        </project>"""
        with open(os.path.join(self.test_dir, "pom.xml"), "w") as f:
            f.write(pom_content)

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Java")

    def test_detect_go_by_go_mod(self):
        """TC006: Verify Go detection via go.mod file."""
        # Create go.mod
        with open(os.path.join(self.test_dir, "go.mod"), "w") as f:
            f.write("module example.com/myapp\ngo 1.21")

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Go")

    def test_unknown_language_empty_directory(self):
        """TC007: Verify Unknown returned for empty directory."""
        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Unknown")
        self.assertEqual(confidence, 0.0)

    def test_detect_python_by_import_statements(self):
        """TC008: Verify Python detection via import patterns in code."""
        # Create Python file with imports
        with open(os.path.join(self.test_dir, "app.py"), "w") as f:
            f.write("from flask import Flask\napp = Flask(__name__)")

        language, confidence = heuristic_language_detection(self.test_dir)
        self.assertEqual(language, "Python")
        self.assertGreater(confidence, 0.3)


class TestHeuristicFrameworkDetection(unittest.TestCase):
    """Test cases for heuristic framework detection algorithm."""

    def setUp(self):
        """Create a temporary directory for test projects."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def test_detect_flask_framework(self):
        """TC009: Verify Flask framework detection via dependency."""
        # Create requirements.txt with Flask
        with open(os.path.join(self.test_dir, "requirements.txt"), "w") as f:
            f.write("flask==2.0.0")

        framework, confidence = heuristic_framework_detection(self.test_dir, "Python")
        self.assertEqual(framework, "Flask")
        self.assertGreater(confidence, 0.3)

    def test_detect_django_framework(self):
        """TC010: Verify Django framework detection."""
        # Create requirements.txt with Django
        with open(os.path.join(self.test_dir, "requirements.txt"), "w") as f:
            f.write("django==4.0.0")
        # Create manage.py
        with open(os.path.join(self.test_dir, "manage.py"), "w") as f:
            f.write("from django.conf import settings")

        framework, confidence = heuristic_framework_detection(self.test_dir, "Python")
        self.assertEqual(framework, "Django")

    def test_detect_fastapi_framework(self):
        """TC011: Verify FastAPI framework detection via code markers."""
        # Create requirements.txt and main.py
        with open(os.path.join(self.test_dir, "requirements.txt"), "w") as f:
            f.write("fastapi==0.100.0")
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write("from fastapi import FastAPI\napp = FastAPI()")

        framework, confidence = heuristic_framework_detection(self.test_dir, "Python")
        self.assertEqual(framework, "FastAPI")

    def test_detect_express_framework(self):
        """TC012: Verify Express.js framework detection."""
        # Create package.json with express
        pkg_content = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        framework, confidence = heuristic_framework_detection(self.test_dir, "JavaScript")
        self.assertEqual(framework, "Express.js")

    def test_detect_react_framework(self):
        """TC013: Verify React framework detection."""
        # Create package.json with React
        pkg_content = {"dependencies": {"react": "^18.0.0"}}
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        framework, confidence = heuristic_framework_detection(self.test_dir, "JavaScript")
        self.assertEqual(framework, "React")

    def test_detect_nextjs_framework(self):
        """TC014: Verify Next.js framework detection."""
        # Create package.json and next.config.js
        pkg_content = {"dependencies": {"next": "^13.0.0", "react": "^18.0.0"}}
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)
        with open(os.path.join(self.test_dir, "next.config.js"), "w") as f:
            f.write("module.exports = {}")

        framework, confidence = heuristic_framework_detection(self.test_dir, "JavaScript")
        self.assertEqual(framework, "Next.js")

    def test_unknown_framework_no_dependencies(self):
        """TC015: Verify Unknown returned when no framework detected."""
        # Create empty project
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write("print('hello')")

        framework, confidence = heuristic_framework_detection(self.test_dir, "Python")
        self.assertEqual(framework, "Unknown")


class TestParseDependenciesFile(unittest.TestCase):
    """Test cases for dependency file parsing."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_parse_requirements_txt(self):
        """TC016: Verify parsing of requirements.txt file."""
        req_path = os.path.join(self.test_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("flask==2.0.0\nrequests>=2.28.0\nnumpy~=1.24.0")

        deps = parse_dependencies_file(req_path, "requirements.txt")
        self.assertIn("flask", deps)
        self.assertIn("requests", deps)
        self.assertIn("numpy", deps)

    def test_parse_package_json(self):
        """TC017: Verify parsing of package.json dependencies."""
        pkg_path = os.path.join(self.test_dir, "package.json")
        pkg_content = {
            "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }
        with open(pkg_path, "w") as f:
            json.dump(pkg_content, f)

        deps = parse_dependencies_file(pkg_path, "package.json")
        self.assertIn("express", deps)
        self.assertIn("mongoose", deps)
        self.assertIn("jest", deps)

    def test_parse_go_mod(self):
        """TC018: Verify parsing of go.mod dependencies."""
        go_mod_path = os.path.join(self.test_dir, "go.mod")
        with open(go_mod_path, "w") as f:
            f.write(
                "module example.com/app\ngo 1.21\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n)"
            )

        deps = parse_dependencies_file(go_mod_path, "go.mod")
        self.assertIn("github.com/gin-gonic/gin", deps)


class TestDetectDockerFiles(unittest.TestCase):
    """Test cases for Docker file detection."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_detect_dockerfile_present(self):
        """TC019: Verify Dockerfile detection when present."""
        with open(os.path.join(self.test_dir, "Dockerfile"), "w") as f:
            f.write("FROM python:3.11\nCOPY . .")

        result = detect_docker_files(self.test_dir)
        self.assertTrue(result["dockerfile"])
        self.assertIn("Dockerfile", result["detected_files"])

    def test_detect_docker_compose_present(self):
        """TC020: Verify docker-compose.yml detection."""
        with open(os.path.join(self.test_dir, "docker-compose.yml"), "w") as f:
            f.write("version: '3.9'\nservices:\n  app:\n    build: .")

        result = detect_docker_files(self.test_dir)
        self.assertTrue(result["docker_compose"])
        self.assertIn("docker-compose.yml", result["detected_files"])

    def test_no_docker_files(self):
        """TC021: Verify negative result when no Docker files present."""
        result = detect_docker_files(self.test_dir)
        self.assertFalse(result["dockerfile"])
        self.assertFalse(result["docker_compose"])


class TestDetectEnvVariables(unittest.TestCase):
    """Test cases for environment variable detection."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_detect_env_variables(self):
        """TC022: Verify .env file parsing for variable names."""
        env_path = os.path.join(self.test_dir, ".env")
        with open(env_path, "w") as f:
            f.write("DATABASE_URL=mongodb://localhost:27017\n")
            f.write("SECRET_KEY=mysecret\n")
            f.write("# Comment line\n")
            f.write("API_KEY=abc123")

        env_vars = detect_env_variables(self.test_dir)
        self.assertIn("DATABASE_URL", env_vars)
        self.assertIn("SECRET_KEY", env_vars)
        self.assertIn("API_KEY", env_vars)
        self.assertEqual(len(env_vars), 3)

    def test_detect_env_example_file(self):
        """TC023: Verify .env.example file parsing."""
        env_path = os.path.join(self.test_dir, ".env.example")
        with open(env_path, "w") as f:
            f.write("MONGO_URI=\nPORT=8000")

        env_vars = detect_env_variables(self.test_dir)
        self.assertIn("MONGO_URI", env_vars)
        self.assertIn("PORT", env_vars)


class TestFindProjectRoot(unittest.TestCase):
    """Test cases for project root detection in nested structures."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_find_root_with_package_json(self):
        """TC024: Verify project root detection with package.json."""
        # Create nested structure with package.json at inner level
        inner_dir = os.path.join(self.test_dir, "wrapper", "actual-project")
        os.makedirs(inner_dir)
        with open(os.path.join(inner_dir, "package.json"), "w") as f:
            json.dump({"name": "app"}, f)

        root = find_project_root(self.test_dir)
        self.assertEqual(root, inner_dir)

    def test_find_root_at_current_level(self):
        """TC025: Verify detection when package.json at current level."""
        with open(os.path.join(self.test_dir, "requirements.txt"), "w") as f:
            f.write("flask")

        root = find_project_root(self.test_dir)
        self.assertEqual(root, self.test_dir)


class TestGetRuntimeInfo(unittest.TestCase):
    """Test cases for runtime information generation."""

    def test_python_runtime_info(self):
        """TC026: Verify Python runtime configuration."""
        info = get_runtime_info("Python", "Flask")
        self.assertEqual(info["runtime"], "python:3.11-slim")
        self.assertEqual(info["port"], 5000)
        self.assertIn("flask", info["start_command"])

    def test_javascript_runtime_info(self):
        """TC027: Verify JavaScript/Node.js runtime configuration."""
        info = get_runtime_info("JavaScript", "Express.js")
        self.assertEqual(info["runtime"], "node:20-alpine")
        self.assertEqual(info["port"], 3000)

    def test_java_runtime_info(self):
        """TC028: Verify Java runtime configuration."""
        info = get_runtime_info("Java", "Spring Boot")
        self.assertEqual(info["runtime"], "openjdk:17-slim")
        self.assertEqual(info["port"], 8080)


class TestDetectFullstackStructure(unittest.TestCase):
    """Test cases for fullstack project structure detection."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_detect_fullstack_structure(self):
        """TC029: Verify detection of frontend/backend folder structure."""
        # Create frontend folder
        frontend_dir = os.path.join(self.test_dir, "frontend")
        os.makedirs(frontend_dir)
        with open(os.path.join(frontend_dir, "package.json"), "w") as f:
            json.dump({"dependencies": {"react": "^18.0.0"}}, f)

        # Create backend folder
        backend_dir = os.path.join(self.test_dir, "backend")
        os.makedirs(backend_dir)
        with open(os.path.join(backend_dir, "package.json"), "w") as f:
            json.dump({"dependencies": {"express": "^4.18.0"}}, f)

        structure = _detect_fullstack_structure(self.test_dir)
        self.assertTrue(structure["is_fullstack"])
        self.assertTrue(structure["has_frontend"])
        self.assertTrue(structure["has_backend"])

    def test_detect_monolithic_structure(self):
        """TC030: Verify non-fullstack detection for single app."""
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump({"dependencies": {"express": "^4.18.0"}}, f)

        structure = _detect_fullstack_structure(self.test_dir)
        self.assertFalse(structure["is_fullstack"])


if __name__ == "__main__":
    # Run tests with verbosity
    unittest.main(verbosity=2)
