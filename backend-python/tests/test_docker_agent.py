"""
Unit Tests for DevOps AutoPilot - Docker Deploy Agent Module

These tests verify the LLM-based Docker configuration generation
and validation functionality.

Author: Abdul Ahad Abbassi
Project: DevOps AutoPilot - AI Deployment Agent
Date: December 2024
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.LLM.docker_deploy_agent import (
    _format_metadata,
    _format_dockerfiles,
    _format_compose_files,
    build_deploy_message,
)


class TestFormatMetadata(unittest.TestCase):
    """Test cases for metadata formatting."""

    def test_format_complete_metadata(self):
        """TC051: Verify complete metadata formatting."""
        metadata = {
            "language": "Python",
            "framework": "FastAPI",
            "runtime": "python:3.11-slim",
            "port": 8000,
            "start_command": "uvicorn main:app",
            "build_command": "pip install -r requirements.txt"
        }
        
        result = _format_metadata(metadata)
        
        self.assertIn("Python", result)
        self.assertIn("FastAPI", result)
        self.assertIn("FastAPI", result)

    def test_format_empty_metadata(self):
        """TC052: Verify empty metadata handling."""
        metadata = {}
        result = _format_metadata(metadata)
        
        # Should return valid string even for empty metadata
        self.assertIsInstance(result, str)

    def test_format_metadata_with_services(self):
        """TC053: Verify metadata with multiple services."""
        metadata = {
            "language": "JavaScript",
            "framework": "Express.js",
            "services": [
                {"name": "backend", "port": 8888},
                {"name": "frontend", "port": 5173}
            ]
        }
        
        result = _format_metadata(metadata)
        self.assertIn("JavaScript", result)


class TestFormatDockerfiles(unittest.TestCase):
    """Test cases for Dockerfile formatting."""

    def test_format_single_dockerfile(self):
        """TC054: Verify single Dockerfile formatting."""
        dockerfiles = [
            {"path": "Dockerfile", "content": "FROM python:3.11\nCOPY . ."}
        ]
        
        result = _format_dockerfiles(dockerfiles)
        
        self.assertIn("Dockerfile", result)
        self.assertIn("FROM python:3.11", result)

    def test_format_multiple_dockerfiles(self):
        """TC055: Verify multiple Dockerfiles formatting."""
        dockerfiles = [
            {"path": "backend/Dockerfile", "content": "FROM node:20"},
            {"path": "frontend/Dockerfile", "content": "FROM node:20-alpine"}
        ]
        
        result = _format_dockerfiles(dockerfiles)
        
        self.assertIn("backend/Dockerfile", result)
        self.assertIn("frontend/Dockerfile", result)

    def test_format_empty_dockerfiles(self):
        """TC056: Verify empty Dockerfile list handling."""
        dockerfiles = []
        result = _format_dockerfiles(dockerfiles)
        
        self.assertIsInstance(result, str)


class TestFormatComposeFiles(unittest.TestCase):
    """Test cases for docker-compose file formatting."""

    def test_format_compose_file(self):
        """TC057: Verify docker-compose.yml formatting."""
        compose_files = [
            {
                "path": "docker-compose.yml",
                "content": "version: '3.9'\nservices:\n  app:\n    build: ."
            }
        ]
        
        result = _format_compose_files(compose_files)
        
        self.assertIn("docker-compose.yml", result)
        self.assertIn("version:", result)

    def test_format_empty_compose(self):
        """TC058: Verify empty compose list handling."""
        compose_files = []
        result = _format_compose_files(compose_files)
        
        self.assertIsInstance(result, str)


class TestBuildDeployMessage(unittest.TestCase):
    """Test cases for deploy message building."""

    def test_build_validate_message(self):
        """TC059: Verify VALIDATE mode message generation."""
        metadata = {"language": "Python", "framework": "Flask", "port": 5000}
        dockerfiles = [{"path": "Dockerfile", "content": "FROM python:3.11"}]
        compose_files = []
        
        result = build_deploy_message(
            project_name="test-project",
            metadata=metadata,
            dockerfiles=dockerfiles,
            compose_files=compose_files,
            file_tree="├── app.py\n├── Dockerfile",
            user_message="Validate my Dockerfile",
            mode="VALIDATE_EXISTING"
        )
        
        self.assertIn("VALIDATE", result)
        self.assertIn("test-project", result)

    def test_build_generate_message(self):
        """TC060: Verify GENERATE mode message generation."""
        metadata = {"language": "JavaScript", "framework": "Express.js", "port": 3000}
        
        result = build_deploy_message(
            project_name="node-api",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="├── index.js\n├── package.json",
            user_message="Generate Dockerfile",
            mode="GENERATE_MISSING"
        )
        
        self.assertIn("GENERATE", result)

    def test_build_message_with_logs(self):
        """TC061: Verify message with error logs included."""
        metadata = {"language": "Python", "framework": "Django"}
        logs = ["Error: ModuleNotFoundError: No module named 'django'"]
        
        result = build_deploy_message(
            project_name="django-app",
            metadata=metadata,
            dockerfiles=[{"path": "Dockerfile", "content": "FROM python:3.11"}],
            compose_files=[],
            file_tree="├── manage.py",
            user_message="Fix build error",
            logs=logs,
            mode="VALIDATE_EXISTING"
        )
        
        self.assertIn("ModuleNotFoundError", result)


class TestDockerAgentIntegration(unittest.TestCase):
    """Integration tests for Docker agent with mocked LLM."""

    @patch('app.LLM.docker_deploy_agent.call_llama')
    def test_run_docker_deploy_chat(self, mock_llama):
        """TC062: Verify LLM integration with mocked response."""
        from app.LLM.docker_deploy_agent import run_docker_deploy_chat
        
        mock_llama.return_value = "STATUS: VALID\nREASON: Dockerfile is correct"
        
        result = run_docker_deploy_chat(
            project_name="test",
            metadata={"language": "Python"},
            dockerfiles=[{"path": "Dockerfile", "content": "FROM python:3.11"}],
            compose_files=[],
            file_tree="├── app.py",
            user_message="Validate"
        )
        
        self.assertIn("VALID", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
