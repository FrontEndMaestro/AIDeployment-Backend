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
    build_gemini_deploy_message,
    parse_and_validate_generated_docker_response,
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

    def test_build_message_ssr_frontend_uses_runtime_container_port(self):
        """TC061A: SSR frontend should keep container_port aligned with runtime_port."""
        metadata = {"language": "JavaScript", "framework": "Nuxt", "runtime": "node:20-alpine"}
        services = [
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "runtime_port": 3000,
                "build_output": ".nuxt",
                "start_command": "npm start",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            }
        ]

        result = build_deploy_message(
            project_name="nuxt-app",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="",
            user_message="Generate Docker files",
            services=services,
            mode="GENERATE_MISSING",
        )

        self.assertIn("runtime_port: 3000, container_port: 3000", result)
        self.assertIn("container_source: ssr_default", result)
        self.assertIn("frontend_mode: ssr", result)


class TestGeneratedDockerValidation(unittest.TestCase):
    """Regression tests for path-aware generated file validation."""

    def test_parse_and_validate_multiproject_generated_files(self):
        metadata = {
            "schema_version": "ports_v2",
            "runtime": "node:20-alpine",
            "database": "MongoDB",
            "database_is_cloud": True,
            "database_port": 27017,
            "database_env_var": "MONGO_URI",
        }
        services = [
            {
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "runtime": "node:20-alpine",
                "runtime_port": 5000,
                "container_port": 5000,
                "entry_point": "server.js",
                "env_file": "./backend/.env",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "runtime": "nginx:alpine",
                "frontend_mode": "static_nginx",
                "runtime_port": 5173,
                "container_port": 80,
                "build_output": "dist",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            },
        ]
        response = """STATUS: Generated
GENERATED FILES:
**backend/Dockerfile**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV PORT=5000
EXPOSE 5000
CMD ["node", "server.js"]
```
**frontend/Dockerfile**
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```
**docker-compose.yml**
```yaml
services:
  backend:
    image: app-backend:latest
    build: ./backend
    ports:
      - "5000:5000"
    env_file:
      - ./backend/.env
  frontend:
    image: app-frontend:latest
    build: ./frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
```
"""

        files, errors = parse_and_validate_generated_docker_response(
            response,
            metadata,
            services,
        )

        self.assertEqual([], errors)
        self.assertEqual(
            ["backend/Dockerfile", "docker-compose.yml", "frontend/Dockerfile"],
            sorted(files),
        )

    def test_gemini_prompt_adds_builder_runtime_for_static_frontend(self):
        metadata = {"runtime": "node:20-alpine"}
        services = [
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "runtime": "nginx:alpine",
                "frontend_mode": "static_nginx",
                "runtime_port": 5173,
                "container_port": 80,
                "build_output": "dist",
            }
        ]

        result = build_gemini_deploy_message(
            project_name="app",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree=None,
            user_message="generate",
            services=services,
            mode="GENERATE_MISSING",
        )

        self.assertIn('"dockerfile_path": "frontend/Dockerfile"', result)
        self.assertIn('"builder_runtime": "node:20-alpine"', result)
        self.assertIn('"final_runtime": "nginx:alpine"', result)
        self.assertNotIn('"runtime": "nginx:alpine"', result)

    def test_gemini_prompt_includes_file_tree_for_path_context(self):
        result = build_gemini_deploy_message(
            project_name="app",
            metadata={},
            dockerfiles=[],
            compose_files=[],
            file_tree="backend/package.json\nfrontend/package.json",
            user_message="generate",
            services=[
                {
                    "name": "backend",
                    "path": "backend",
                    "type": "backend",
                    "runtime_port": 5000,
                    "container_port": 5000,
                }
            ],
            mode="GENERATE_MISSING",
        )

        self.assertIn('"file_tree": "backend/package.json\\nfrontend/package.json"', result)
        self.assertIn('"dockerfile_path": "backend/Dockerfile"', result)


    @patch("app.LLM.docker_deploy_agent.get_docker_llm_provider")
    def test_gemini_validation_mode_uses_validation_prompt_with_logs(self, mock_provider):
        from app.LLM.docker_deploy_agent import _response_message

        mock_provider.return_value = "gemini"
        system_prompt, message = _response_message(
            project_name="app",
            metadata={"schema_version": "ports_v2", "database": "Unknown"},
            dockerfiles=[{"path": "backend/Dockerfile", "content": "FROM node:20-alpine"}],
            compose_files=[{"path": "docker-compose.yml", "content": "services: {}"}],
            file_tree=None,
            user_message="build failed. Analyze these logs and fix Dockerfile.",
            logs=["failed to solve: failed to read dockerfile"],
            extra_instructions=None,
            services=[
                {
                    "name": "backend",
                    "path": "backend",
                    "type": "backend",
                    "runtime_port": 5000,
                    "container_port": 5000,
                }
            ],
            mode="VALIDATE_EXISTING",
        )

        self.assertIn("Validate existing Docker files", system_prompt)
        self.assertNotIn("STATUS: Generated", system_prompt)
        self.assertIn('"mode": "VALIDATE_EXISTING"', message)
        self.assertIn("failed to read dockerfile", message)


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

    @patch("app.LLM.docker_deploy_agent.get_docker_llm_provider")
    @patch("app.LLM.docker_deploy_agent.call_gemini")
    def test_gemini_stream_repairs_invalid_generated_files(self, mock_gemini, mock_provider):
        """Gemini stream path validates generated files before yielding to the UI."""
        from app.LLM.docker_deploy_agent import run_docker_deploy_chat_stream

        mock_provider.return_value = "gemini"
        invalid_response = """STATUS: Generated
GENERATED FILES:
**backend/Dockerfile**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV PORT=5000
EXPOSE 5000
CMD ["node", "server.js"]
```
"""
        valid_response = """STATUS: Generated
GENERATED FILES:
**backend/Dockerfile**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV PORT=5000
EXPOSE 5000
CMD ["node", "server.js"]
```
**docker-compose.yml**
```yaml
services:
  backend:
    image: app-backend:latest
    build: ./backend
    ports:
      - "5000:5000"
```
"""
        mock_gemini.side_effect = [invalid_response, valid_response]
        services = [
            {
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "runtime": "node:20-alpine",
                "runtime_port": 5000,
                "container_port": 5000,
                "entry_point": "server.js",
            }
        ]

        chunks = list(
            run_docker_deploy_chat_stream(
                project_name="app",
                metadata={"schema_version": "ports_v2", "database": "Unknown"},
                dockerfiles=[],
                compose_files=[],
                file_tree="",
                user_message="generate",
                services=services,
            )
        )

        self.assertEqual(2, mock_gemini.call_count)
        self.assertIn("docker-compose.yml", chunks[0]["token"])
        self.assertTrue(chunks[-1]["done"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
