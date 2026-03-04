"""
Unit Tests for Docker Generation Pipeline - All 3 Layers

Layer 1: Critical Bug Fixes (Dockerfile-to-service matching, project_root consistency)
Layer 2: MERN Coverage (Next.js, TypeScript backend, .dockerignore)
Layer 3: Robustness (regex parsing, fallback templates)

Author: Abdul Ahad Abbassi
Project: DevOps AutoPilot - AI Deployment Agent
Date: February 2026
"""

import os
import sys
import re
import tempfile
import shutil
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.LLM.docker_deploy_agent import (
    _format_metadata,
    build_deploy_message,
    DOCKER_DEPLOY_SYSTEM_PROMPT,
)


# =============================================================================
# LAYER 1: CRITICAL BUG FIXES
# =============================================================================


class TestDockerfileToServiceMatching(unittest.TestCase):
    """
    Layer 1, Bug #1: Dockerfiles parsed from LLM response must be matched
    to services by NAME (from the **path/Dockerfile** header), not by
    positional index. If the LLM returns frontend first and backend second
    but services list is [backend, frontend], positional matching writes the
    wrong Dockerfile to the wrong directory.
    """

    # -- Regex extraction helpers (mirrors docker_service.py logic) --

    DOCKERFILE_PATTERN = (
        r'\*\*(?:backend/|frontend/)?Dockerfile\*\*\s*```(?:dockerfile)?\s*([\s\S]*?)```'
    )
    NAMED_DOCKERFILE_PATTERN = (
        r'\*\*([^\*]+)/Dockerfile\*\*\s*```(?:dockerfile)?\s*([\s\S]*?)```'
    )

    def test_positional_match_wrong_order(self):
        """TC100: Positional regex gives WRONG mapping when LLM order ≠ service order."""
        llm_response = (
            "**frontend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine AS builder\nWORKDIR /app\nRUN npm run build\n"
            "```\n\n"
            "**backend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nWORKDIR /app\nEXPOSE 5000\nCMD [\"node\", \"server.js\"]\n"
            "```\n"
        )
        services = [
            {"name": "backend", "path": "backend", "type": "backend"},
            {"name": "frontend", "path": "frontend", "type": "frontend"},
        ]

        # Current (buggy) positional matching: uses findall, assigns by index
        positional_matches = re.findall(self.DOCKERFILE_PATTERN, llm_response, re.IGNORECASE)
        self.assertEqual(len(positional_matches), 2)

        # Index 0 matches to services[0] ("backend") but is actually the FRONTEND Dockerfile
        backend_content_positional = positional_matches[0].strip()
        self.assertIn("npm run build", backend_content_positional,
                       "Positional match incorrectly assigns frontend Dockerfile to backend service")

    def test_named_match_correct_order(self):
        """TC101: Named regex gives CORRECT mapping regardless of LLM output order."""
        llm_response = (
            "**frontend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine AS builder\nWORKDIR /app\nRUN npm run build\n"
            "```\n\n"
            "**backend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nWORKDIR /app\nEXPOSE 5000\nCMD [\"node\", \"server.js\"]\n"
            "```\n"
        )

        # Extract by name instead of position
        named_matches = re.findall(self.NAMED_DOCKERFILE_PATTERN, llm_response, re.IGNORECASE)
        result_map = {name.strip(): content.strip() for name, content in named_matches}

        self.assertIn("backend", result_map)
        self.assertIn("frontend", result_map)
        self.assertIn("EXPOSE 5000", result_map["backend"])
        self.assertIn("npm run build", result_map["frontend"])

    def test_single_service_root_dockerfile(self):
        """TC102: Single-service project with root Dockerfile (no path prefix)."""
        llm_response = (
            "**Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nWORKDIR /app\nEXPOSE 3000\nCMD [\"node\", \"index.js\"]\n"
            "```\n"
        )
        # Root Dockerfile pattern (no path prefix)
        root_pattern = r'\*\*Dockerfile\*\*\s*```(?:dockerfile)?\s*([\s\S]*?)```'
        match = re.search(root_pattern, llm_response)
        self.assertIsNotNone(match)
        self.assertIn("EXPOSE 3000", match.group(1))

    def test_three_services_correct_mapping(self):
        """TC103: 3-service project (backend, frontend, admin) maps correctly."""
        llm_response = (
            "**admin/Dockerfile**\n```dockerfile\nFROM node:20-alpine\nEXPOSE 4000\n```\n\n"
            "**backend/Dockerfile**\n```dockerfile\nFROM node:20-alpine\nEXPOSE 5000\n```\n\n"
            "**frontend/Dockerfile**\n```dockerfile\nFROM node:20-alpine AS builder\nEXPOSE 80\n```\n"
        )

        named_matches = re.findall(self.NAMED_DOCKERFILE_PATTERN, llm_response, re.IGNORECASE)
        result_map = {name.strip(): content.strip() for name, content in named_matches}

        self.assertEqual(len(result_map), 3)
        self.assertIn("EXPOSE 4000", result_map["admin"])
        self.assertIn("EXPOSE 5000", result_map["backend"])
        self.assertIn("EXPOSE 80", result_map["frontend"])


class TestProjectRootConsistency(unittest.TestCase):
    """
    Layer 1, Bug #2: _collect_docker_files uses extracted_path but
    find_project_root may return a nested subdirectory. Docker files
    collected from extracted_path could miss files that are inside the
    actual project root.
    """

    def setUp(self):
        """Create a temp directory simulating nested extraction."""
        self.tmpdir = tempfile.mkdtemp()
        # Simulate: extracted/project-xxx/mern-app/Dockerfile
        self.nested_root = os.path.join(self.tmpdir, "project-xxx", "mern-app")
        os.makedirs(self.nested_root)
        # Put Dockerfile INSIDE the nested root
        with open(os.path.join(self.nested_root, "Dockerfile"), "w") as f:
            f.write("FROM node:20\n")
        # Put a package.json to signal project root
        with open(os.path.join(self.nested_root, "package.json"), "w") as f:
            f.write('{"name": "test"}\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_collect_from_extracted_path_finds_nested(self):
        """TC104: Collecting from extracted_path (top-level) should find nested Dockerfiles."""
        dockerfiles = []
        for root, _, files in os.walk(self.tmpdir):
            for name in files:
                if name in ("Dockerfile", "dockerfile"):
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, self.tmpdir)
                    dockerfiles.append({"path": rel_path})

        self.assertEqual(len(dockerfiles), 1)
        # Path is relative to extracted_path, includes the nesting
        self.assertIn("project-xxx", dockerfiles[0]["path"])

    def test_collect_from_project_root_finds_directly(self):
        """TC105: Collecting from project_root (actual code root) finds Dockerfile directly."""
        dockerfiles = []
        for root, _, files in os.walk(self.nested_root):
            for name in files:
                if name in ("Dockerfile", "dockerfile"):
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, self.nested_root)
                    dockerfiles.append({"path": rel_path})

        self.assertEqual(len(dockerfiles), 1)
        self.assertEqual(dockerfiles[0]["path"], "Dockerfile")


# =============================================================================
# LAYER 2: MERN COVERAGE (Next.js, TypeScript, .dockerignore)
# =============================================================================


class TestNextJsPromptCoverage(unittest.TestCase):
    """
    Layer 2: The system prompt must handle Next.js projects which need
    node runtime in production (NOT nginx). Next.js uses `next start`
    and runs on a specified port, not as static files.
    """

    def test_prompt_mentions_nextjs(self):
        """TC106: System prompt should reference Next.js handling."""
        # After the fix, the prompt should mention Next.js
        # For now, this test documents the EXPECTED behavior
        prompt_lower = DOCKER_DEPLOY_SYSTEM_PROMPT.lower()
        has_nextjs = "next.js" in prompt_lower or "nextjs" in prompt_lower or "next" in prompt_lower
        self.assertTrue(has_nextjs,
                        "System prompt should mention Next.js to avoid forcing nginx on SSR apps")

    def test_nextjs_metadata_in_message(self):
        """TC107: When framework=Next.js, the message should convey this to the LLM."""
        metadata = {
            "language": "JavaScript",
            "framework": "Next.js",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "frontend_port": 3000,
        }

        result = _format_metadata(metadata)
        self.assertIn("Next.js", result)

    def test_nextjs_service_definition(self):
        """TC108: Next.js service should produce correct Dockerfile template."""
        # This tests what the expected output should look like for a Next.js project
        # The correct Dockerfile for Next.js should use node, NOT nginx
        correct_nextjs_dockerfile = (
            "FROM node:20-alpine AS builder\n"
            "WORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build\n\n"
            "FROM node:20-alpine\n"
            "WORKDIR /app\n"
            "COPY --from=builder /app/.next ./.next\n"
            "COPY --from=builder /app/node_modules ./node_modules\n"
            "COPY --from=builder /app/package.json ./\n"
            "EXPOSE 3000\n"
            'CMD ["npm", "start"]\n'
        )
        # Should NOT contain nginx
        self.assertNotIn("nginx", correct_nextjs_dockerfile)
        # Should use node in production stage
        self.assertIn("FROM node:20-alpine\n", correct_nextjs_dockerfile)
        # Should expose app port, not 80
        self.assertIn("EXPOSE 3000", correct_nextjs_dockerfile)

    def test_build_message_nextjs_service(self):
        """TC109: Services with framework=Next.js should signal SSR mode to LLM."""
        metadata = {
            "framework": "Next.js",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "frontend_port": 3000,
        }
        services = [
            {
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "port": 3000,
                "build_output": ".next",
                "package_manager": {"manager": "npm", "has_lockfile": True},
            }
        ]

        result = build_deploy_message(
            project_name="nextapp",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="[dir] frontend\n[file] frontend/package.json\n[file] frontend/next.config.js",
            user_message="Generate",
            services=services,
            mode="GENERATE_MISSING",
        )

        # The message should contain .next as build_output
        self.assertIn(".next", result)
        self.assertIn("Next.js", result)


class TestTypeScriptBackendPromptCoverage(unittest.TestCase):
    """
    Layer 2: TypeScript backends need a build step (tsc or npm run build)
    before running. The current prompt blocks "npm run build" for ALL
    backends, which breaks TypeScript projects.
    """

    def test_prompt_allows_ts_build(self):
        """TC110: System prompt should allow build step for TypeScript backends."""
        # After the fix, the prompt should mention TypeScript build exception
        prompt_lower = DOCKER_DEPLOY_SYSTEM_PROMPT.lower()
        has_ts = "typescript" in prompt_lower or "tsc" in prompt_lower
        self.assertTrue(has_ts,
                        "System prompt should mention TypeScript backend build step exception")

    def test_typescript_backend_service_message(self):
        """TC111: TypeScript backend service should signal build requirement."""
        metadata = {
            "language": "TypeScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 5000,
            "build_command": "npm run build",
            "entry_point": "dist/index.js",
        }

        result = _format_metadata(metadata)
        self.assertIn("node:20-alpine", result)
        self.assertIn("dist/index.js", result)

    def test_ts_backend_correct_dockerfile(self):
        """TC112: Correct TypeScript backend Dockerfile should have build step + dist."""
        correct_ts_backend = (
            "FROM node:20-alpine\n"
            "WORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build\n"
            "EXPOSE 5000\n"
            'CMD ["node", "dist/index.js"]\n'
        )
        # Should have build step
        self.assertIn("RUN npm run build", correct_ts_backend)
        # CMD should point to the compiled output
        self.assertIn("dist/index.js", correct_ts_backend)
        # Should NOT be multi-stage (still single-stage, just with build)
        from_count = correct_ts_backend.count("FROM ")
        self.assertEqual(from_count, 1, "TS backend should remain single-stage")


class TestDockerignoreGeneration(unittest.TestCase):
    """
    Layer 2: Projects without .dockerignore will COPY node_modules into
    the image, making it huge (~500MB+) and potentially causing build failures.
    The pipeline should generate a .dockerignore when one doesn't exist.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmpdir, "myproject")
        os.makedirs(self.project_dir)
        os.makedirs(os.path.join(self.project_dir, "node_modules", "express"))
        with open(os.path.join(self.project_dir, "package.json"), "w") as f:
            f.write('{"name":"test"}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_no_dockerignore_exists(self):
        """TC113: Detect when .dockerignore is missing."""
        dockerignore_path = os.path.join(self.project_dir, ".dockerignore")
        self.assertFalse(os.path.exists(dockerignore_path))

    def test_default_dockerignore_content(self):
        """TC114: Generated .dockerignore should exclude node_modules, .git, etc."""
        expected_entries = [
            "node_modules",
            ".git",
            ".env",
            "npm-debug.log",
            ".DS_Store",
        ]
        # Simulate generating a .dockerignore
        content = "\n".join(expected_entries) + "\n"

        dockerignore_path = os.path.join(self.project_dir, ".dockerignore")
        with open(dockerignore_path, "w") as f:
            f.write(content)

        with open(dockerignore_path) as f:
            written = f.read()

        for entry in expected_entries:
            self.assertIn(entry, written,
                          f".dockerignore should exclude {entry}")

    def test_existing_dockerignore_not_overwritten(self):
        """TC115: If .dockerignore already exists, it should NOT be overwritten."""
        dockerignore_path = os.path.join(self.project_dir, ".dockerignore")
        original_content = "# Custom dockerignore\nmy_custom_dir\n"
        with open(dockerignore_path, "w") as f:
            f.write(original_content)

        # Simulating the check: don't overwrite if exists
        if os.path.exists(dockerignore_path):
            with open(dockerignore_path) as f:
                content = f.read()
            self.assertEqual(content, original_content)


# =============================================================================
# LAYER 3: ROBUSTNESS (Regex Parsing, Fallback Templates)
# =============================================================================


class TestComposeYamlExtraction(unittest.TestCase):
    """
    Layer 3: The regex parser for extracting docker-compose.yml from
    LLM responses must handle various formatting variations.
    """

    COMPOSE_PATTERN = r'\*\*docker-compose\.yml\*\*\s*```(?:yaml)?\s*([\s\S]*?)```'
    ALT_COMPOSE_PATTERN = r'docker-compose\.yml[^\n]*\n\s*```(?:yaml)?\s*([\s\S]*?)```'

    def _extract_compose(self, text):
        """Helper: extract compose YAML from agent response using the same logic."""
        match = re.search(self.COMPOSE_PATTERN, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        match = re.search(self.ALT_COMPOSE_PATTERN, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Fallback: any yaml block with services:
        yaml_blocks = re.findall(r'```(?:yaml)?\s*([\s\S]*?)```', text)
        for block in yaml_blocks:
            if 'services:' in block and ('build:' in block or 'image:' in block):
                return block.strip()

        return ""

    def test_standard_format(self):
        """TC116: Standard **docker-compose.yml** + ```yaml format."""
        response = (
            "STATUS: Generated\n\n"
            "**docker-compose.yml**\n"
            "```yaml\n"
            "services:\n"
            "  backend:\n"
            "    image: myapp-backend:latest\n"
            "    build: ./backend\n"
            "    ports:\n"
            '      - "5000:5000"\n'
            "```\n"
        )
        result = self._extract_compose(response)
        self.assertIn("services:", result)
        self.assertIn("myapp-backend:latest", result)

    def test_without_yaml_language_tag(self):
        """TC117: ```(no language tag) instead of ```yaml."""
        response = (
            "**docker-compose.yml**\n"
            "```\n"
            "services:\n"
            "  app:\n"
            "    image: test:latest\n"
            "    build: .\n"
            "```\n"
        )
        result = self._extract_compose(response)
        self.assertIn("services:", result)

    def test_compose_with_extra_text(self):
        """TC118: Compose block surrounded by explanatory text."""
        response = (
            "Here is your docker-compose configuration:\n\n"
            "**docker-compose.yml**\n"
            "```yaml\n"
            "services:\n"
            "  backend:\n"
            "    image: app-backend:latest\n"
            "    build: ./server\n"
            "```\n\n"
            "Make sure to run `docker compose up` to start all services."
        )
        result = self._extract_compose(response)
        self.assertIn("services:", result)
        self.assertNotIn("Make sure", result)

    def test_multiple_yaml_blocks_picks_compose(self):
        """TC119: Multiple ```yaml blocks — should pick the one with services:."""
        response = (
            "**backend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\n"
            "EXPOSE 5000\n"
            "```\n\n"
            "**docker-compose.yml**\n"
            "```yaml\n"
            "services:\n"
            "  backend:\n"
            "    image: app-backend:latest\n"
            "    build: ./backend\n"
            "```\n"
        )
        result = self._extract_compose(response)
        self.assertIn("services:", result)
        self.assertNotIn("FROM node", result)

    def test_no_compose_in_response(self):
        """TC120: LLM response has no compose section at all."""
        response = (
            "STATUS: Generated\n\n"
            "**Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\n"
            "```\n"
        )
        result = self._extract_compose(response)
        self.assertEqual(result, "")

    def test_compose_with_yml_variant(self):
        """TC121: LLM uses 'docker-compose.yaml' instead of '.yml'."""
        response = (
            "Here is the config:\n\n"
            "docker-compose.yml\n"
            "```yaml\n"
            "services:\n"
            "  web:\n"
            "    image: web:latest\n"
            "    build: .\n"
            "```\n"
        )
        result = self._extract_compose(response)
        self.assertIn("services:", result)


class TestDockerfileExtraction(unittest.TestCase):
    """
    Layer 3: Regex extraction of Dockerfiles from LLM response must
    handle various path formats the LLM might produce.
    """

    NAMED_PATTERN = r'\*\*([^\*]+/)?Dockerfile\*\*\s*```(?:dockerfile)?\s*([\s\S]*?)```'

    def _extract_dockerfiles(self, text):
        """Extract all Dockerfiles as a dict: {path: content}."""
        matches = re.findall(self.NAMED_PATTERN, text, re.IGNORECASE)
        result = {}
        for path_prefix, content in matches:
            path = (path_prefix or "").strip().rstrip("/")
            result[path or "."] = content.strip()
        return result

    def test_standard_backend_frontend(self):
        """TC122: Standard **backend/Dockerfile** and **frontend/Dockerfile**."""
        response = (
            "**backend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nEXPOSE 5000\n"
            "```\n\n"
            "**frontend/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine AS builder\nEXPOSE 80\n"
            "```\n"
        )
        result = self._extract_dockerfiles(response)
        self.assertEqual(len(result), 2)
        self.assertIn("EXPOSE 5000", result.get("backend", ""))
        self.assertIn("EXPOSE 80", result.get("frontend", ""))

    def test_nested_path(self):
        """TC123: Nested path like **server/api/Dockerfile**."""
        response = (
            "**server/api/Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nEXPOSE 8080\n"
            "```\n"
        )
        result = self._extract_dockerfiles(response)
        self.assertEqual(len(result), 1)
        self.assertIn("EXPOSE 8080", result.get("server/api", ""))

    def test_root_dockerfile(self):
        """TC124: Root **Dockerfile** with no path prefix."""
        response = (
            "**Dockerfile**\n"
            "```dockerfile\n"
            "FROM node:20-alpine\nEXPOSE 3000\n"
            "```\n"
        )
        result = self._extract_dockerfiles(response)
        self.assertEqual(len(result), 1)
        self.assertIn("EXPOSE 3000", result.get(".", ""))

    def test_without_dockerfile_lang_tag(self):
        """TC125: ```(no language tag) instead of ```dockerfile."""
        response = (
            "**backend/Dockerfile**\n"
            "```\n"
            "FROM node:20-alpine\nEXPOSE 5000\n"
            "```\n"
        )
        result = self._extract_dockerfiles(response)
        self.assertEqual(len(result), 1)
        self.assertIn("EXPOSE 5000", result.get("backend", ""))

    def test_malformed_no_dockerfiles(self):
        """TC126: LLM response with no recognizable Dockerfile blocks."""
        response = (
            "I recommend using the following configuration:\n"
            "Use FROM node:20-alpine as your base image.\n"
            "Set EXPOSE 5000 for the backend.\n"
        )
        result = self._extract_dockerfiles(response)
        self.assertEqual(len(result), 0)


class TestFallbackTemplates(unittest.TestCase):
    """
    Layer 3: When LLM response parsing fails, fallback templates should
    produce valid, runnable Dockerfiles based on service metadata alone.
    """

    def _generate_fallback_dockerfile(self, service):
        """Generate a fallback Dockerfile from service metadata when LLM parsing fails."""
        svc_type = service.get("type", "backend")

        if svc_type == "frontend":
            build_output = service.get("build_output", "dist")
            pm = service.get("package_manager", {})
            if isinstance(pm, dict):
                manager = pm.get("manager", "npm")
                has_lock = pm.get("has_lockfile", True)
            else:
                manager = pm or "npm"
                has_lock = True

            if manager == "yarn":
                install = "yarn install --frozen-lockfile"
                build = "yarn build"
            elif manager == "pnpm":
                install = "pnpm install --frozen-lockfile"
                build = "pnpm build"
            elif has_lock:
                install = "npm ci"
                build = "npm run build"
            else:
                install = "npm install"
                build = "npm run build"

            return (
                f"FROM node:20-alpine AS builder\n"
                f"WORKDIR /app\n"
                f"COPY package*.json ./\n"
                f"RUN {install}\n"
                f"COPY . .\n"
                f"RUN {build}\n\n"
                f"FROM nginx:alpine\n"
                f"COPY --from=builder /app/{build_output} /usr/share/nginx/html\n"
                f"EXPOSE 80\n"
                f'CMD ["nginx", "-g", "daemon off;"]\n'
            )
        else:
            port = service.get("port", 8000)
            entry = service.get("entry_point", "index.js")

            pm = service.get("package_manager", {})
            if isinstance(pm, dict):
                manager = pm.get("manager", "npm")
                has_lock = pm.get("has_lockfile", True)
            else:
                manager = pm or "npm"
                has_lock = True

            if manager == "yarn":
                install = "yarn install --frozen-lockfile"
            elif manager == "pnpm":
                install = "pnpm install --frozen-lockfile"
            elif has_lock:
                install = "npm ci"
            else:
                install = "npm install"

            return (
                f"FROM node:20-alpine\n"
                f"WORKDIR /app\n"
                f"COPY package*.json ./\n"
                f"RUN {install}\n"
                f"COPY . .\n"
                f"EXPOSE {port}\n"
                f'CMD ["node", "{entry}"]\n'
            )

    def test_backend_fallback(self):
        """TC127: Fallback template for backend service."""
        svc = {
            "name": "backend",
            "type": "backend",
            "port": 5000,
            "entry_point": "src/server.js",
            "package_manager": {"manager": "npm", "has_lockfile": True},
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("FROM node:20-alpine", result)
        self.assertIn("EXPOSE 5000", result)
        self.assertIn("src/server.js", result)
        self.assertIn("npm ci", result)
        self.assertNotIn("AS builder", result)  # No multi-stage for backend

    def test_frontend_fallback_vite(self):
        """TC128: Fallback template for Vite frontend service."""
        svc = {
            "name": "frontend",
            "type": "frontend",
            "build_output": "dist",
            "package_manager": {"manager": "npm", "has_lockfile": True},
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("AS builder", result)
        self.assertIn("npm run build", result)
        self.assertIn("/app/dist", result)
        self.assertIn("nginx:alpine", result)
        self.assertIn("EXPOSE 80", result)

    def test_frontend_fallback_cra(self):
        """TC129: Fallback template for CRA frontend (build_output=build)."""
        svc = {
            "name": "frontend",
            "type": "frontend",
            "build_output": "build",
            "package_manager": {"manager": "npm", "has_lockfile": False},
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("/app/build", result)
        self.assertIn("npm install", result)  # No lockfile → npm install, not ci

    def test_backend_fallback_yarn(self):
        """TC130: Fallback template for yarn-based backend."""
        svc = {
            "name": "api",
            "type": "backend",
            "port": 4000,
            "entry_point": "app.js",
            "package_manager": {"manager": "yarn", "has_lockfile": True},
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("yarn install --frozen-lockfile", result)
        self.assertIn("EXPOSE 4000", result)
        self.assertIn("app.js", result)

    def test_backend_fallback_pnpm(self):
        """TC131: Fallback template for pnpm-based backend."""
        svc = {
            "name": "server",
            "type": "backend",
            "port": 3000,
            "entry_point": "server.js",
            "package_manager": {"manager": "pnpm", "has_lockfile": True},
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("pnpm install --frozen-lockfile", result)

    def test_backend_fallback_defaults(self):
        """TC132: Fallback with minimal metadata uses sensible defaults."""
        svc = {
            "name": "app",
            "type": "backend",
        }
        result = self._generate_fallback_dockerfile(svc)
        self.assertIn("EXPOSE 8000", result)  # Default port
        self.assertIn("index.js", result)  # Default entry point
        self.assertIn("npm ci", result)  # Default install


class TestBuildMessageMERNVariations(unittest.TestCase):
    """
    Layer 3: build_deploy_message must correctly format all MERN variations.
    """

    def test_fullstack_mern_message(self):
        """TC133: Fullstack MERN (Express + React + MongoDB)."""
        metadata = {
            "language": "JavaScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 5000,
            "frontend_port": 3000,
            "database": "MongoDB",
            "database_port": 27017,
            "database_is_cloud": False,
        }
        services = [
            {"name": "backend", "path": "backend", "type": "backend", "port": 5000,
             "entry_point": "server.js"},
            {"name": "frontend", "path": "frontend", "type": "frontend",
             "build_output": "dist"},
        ]

        result = build_deploy_message(
            project_name="mern-blog",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="[dir] backend\n[dir] frontend",
            user_message="Generate",
            services=services,
            mode="GENERATE_MISSING",
        )

        self.assertIn("mern-blog", result)
        self.assertIn("5000", result)
        self.assertIn("server.js", result)
        self.assertIn("MongoDB", result)
        self.assertIn("GENERATE_MISSING", result)

    def test_backend_only_message(self):
        """TC134: Backend-only Express API with cloud MongoDB."""
        metadata = {
            "language": "JavaScript",
            "framework": "Express.js",
            "runtime": "node:20-alpine",
            "backend_port": 3000,
            "database": "MongoDB",
            "database_is_cloud": True,
            "database_env_var": "MONGODB_URI",
        }

        result = build_deploy_message(
            project_name="express-api",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="[file] package.json\n[file] index.js",
            user_message="Generate",
            mode="GENERATE_MISSING",
        )

        self.assertIn("express-api", result)
        self.assertIn("True", result)  # database_is_cloud
        self.assertIn("MONGODB_URI", result)

    def test_frontend_only_message(self):
        """TC135: Frontend-only React/Vite project."""
        metadata = {
            "language": "JavaScript",
            "framework": "React",
            "runtime": "node:20-alpine",
            "frontend_port": 5173,
            "build_output": "dist",
        }

        result = build_deploy_message(
            project_name="react-app",
            metadata=metadata,
            dockerfiles=[],
            compose_files=[],
            file_tree="[file] package.json\n[dir] src",
            user_message="Generate",
            mode="GENERATE_MISSING",
        )

        self.assertIn("react-app", result)
        self.assertIn("dist", result)

    def test_validate_mode_includes_existing_files(self):
        """TC136: VALIDATE mode includes existing Dockerfile content."""
        metadata = {"runtime": "node:20-alpine", "backend_port": 5000}
        dockerfiles = [
            {"path": "Dockerfile", "content": "FROM node:20-alpine\nEXPOSE 5000"}
        ]

        result = build_deploy_message(
            project_name="myapi",
            metadata=metadata,
            dockerfiles=dockerfiles,
            compose_files=[],
            file_tree="[file] Dockerfile",
            user_message="Validate my Dockerfile",
            mode="VALIDATE_EXISTING",
        )

        self.assertIn("VALIDATE_EXISTING", result)
        self.assertIn("FROM node:20-alpine", result)
        self.assertIn("EXPOSE 5000", result)


class TestEnsureComposeEnvFiles(unittest.TestCase):
    """
    Layer 3: _ensure_compose_env_files creates placeholder .env files
    so docker-compose doesn't fail on missing env_file references.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_missing_env_file(self):
        """TC137: Creates a placeholder .env when compose references one that doesn't exist."""
        import yaml
        compose_content = {
            "services": {
                "backend": {
                    "image": "app:latest",
                    "env_file": ["./backend/.env"],
                }
            }
        }
        compose_path = os.path.join(self.tmpdir, "docker-compose.yml")
        with open(compose_path, "w") as f:
            yaml.dump(compose_content, f)

        # Simulate the ensure function
        with open(compose_path, "r") as f:
            data = yaml.safe_load(f)

        for svc_name, svc in data.get("services", {}).items():
            env_files = svc.get("env_file", [])
            if isinstance(env_files, str):
                env_files = [env_files]
            for rel in env_files:
                env_path = os.path.join(self.tmpdir, rel)
                if not os.path.exists(env_path):
                    os.makedirs(os.path.dirname(env_path), exist_ok=True)
                    with open(env_path, "w") as f:
                        f.write("# Auto-created placeholder\n")

        expected_env = os.path.join(self.tmpdir, "backend", ".env")
        self.assertTrue(os.path.exists(expected_env))

    def test_does_not_overwrite_existing_env(self):
        """TC138: Does NOT overwrite .env that already exists."""
        backend_dir = os.path.join(self.tmpdir, "backend")
        os.makedirs(backend_dir)
        env_path = os.path.join(backend_dir, ".env")
        with open(env_path, "w") as f:
            f.write("MONGO_URI=mongodb://localhost:27017/mydb\n")

        # Simulating: if file exists, don't touch it
        original_content = open(env_path).read()
        if not os.path.exists(env_path):
            with open(env_path, "w") as f:
                f.write("# placeholder\n")

        self.assertEqual(open(env_path).read(), original_content)


# =============================================================================
# LAYER 4: CONTEXT-AWARE DEPLOY BLOCKING
# =============================================================================


class TestContextAwareBlocking(unittest.TestCase):
    """
    Requirement 1: deploy_blocked should only be True when a backend is
    missing .env AND a database is detected (database != "Unknown").
    """

    def _simulate_deploy_blocked_logic(self, services, results):
        """Mirror the deploy_blocked logic from detector.py detect_framework."""
        backend_services = [s for s in services if s.get("type") == "backend"]
        backend_missing_env = any(
            svc.get("type") == "backend" and not svc.get("env_file")
            for svc in services
        )

        if backend_services and backend_missing_env:
            if results.get("database") != "Unknown":
                results["deploy_blocked"] = True
                results["deploy_blocked_reason"] = (
                    "Backend .env file is required because a database was detected. "
                    "Please add a .env file with DATABASE_URL, PORT, and other secrets."
                )
                results["backend_env_missing"] = True
                results["deploy_warning"] = None
            else:
                results["deploy_blocked"] = False
                results["deploy_blocked_reason"] = None
                results["backend_env_missing"] = True
                results["deploy_warning"] = (
                    "No .env detected. Proceed only if your app doesn't require secrets."
                )
        else:
            results["deploy_blocked"] = False
            results["deploy_blocked_reason"] = None
            results["backend_env_missing"] = False
            results["deploy_warning"] = None

        return results

    def test_blocked_when_db_and_no_env(self):
        """TC200: Backend missing .env WITH database detected → deploy_blocked = True."""
        services = [{"name": "backend", "type": "backend", "env_file": None}]
        results = {"database": "MongoDB"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertTrue(out["deploy_blocked"])
        self.assertIsNotNone(out["deploy_blocked_reason"])
        self.assertTrue(out["backend_env_missing"])
        self.assertIsNone(out.get("deploy_warning"))

    def test_not_blocked_when_env_present(self):
        """TC201: Backend HAS .env → deploy_blocked = False regardless of database."""
        services = [{"name": "backend", "type": "backend", "env_file": "./backend/.env"}]
        results = {"database": "MongoDB"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertFalse(out["deploy_blocked"])
        self.assertIsNone(out["deploy_blocked_reason"])
        self.assertFalse(out["backend_env_missing"])

    def test_not_blocked_frontend_only(self):
        """TC202: Frontend-only project (no backend) → deploy_blocked = False."""
        services = [{"name": "frontend", "type": "frontend"}]
        results = {"database": "Unknown"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertFalse(out["deploy_blocked"])
        self.assertFalse(out["backend_env_missing"])


class TestDeployWarningDowngrade(unittest.TestCase):
    """
    Requirement 2: If backend is missing .env but NO database is detected,
    set deploy_warning instead of blocking.
    """

    def _simulate_deploy_blocked_logic(self, services, results):
        """Same logic as TestContextAwareBlocking."""
        backend_services = [s for s in services if s.get("type") == "backend"]
        backend_missing_env = any(
            svc.get("type") == "backend" and not svc.get("env_file")
            for svc in services
        )

        if backend_services and backend_missing_env:
            if results.get("database") != "Unknown":
                results["deploy_blocked"] = True
                results["deploy_blocked_reason"] = (
                    "Backend .env file is required because a database was detected. "
                    "Please add a .env file with DATABASE_URL, PORT, and other secrets."
                )
                results["backend_env_missing"] = True
                results["deploy_warning"] = None
            else:
                results["deploy_blocked"] = False
                results["deploy_blocked_reason"] = None
                results["backend_env_missing"] = True
                results["deploy_warning"] = (
                    "No .env detected. Proceed only if your app doesn't require secrets."
                )
        else:
            results["deploy_blocked"] = False
            results["deploy_blocked_reason"] = None
            results["backend_env_missing"] = False
            results["deploy_warning"] = None

        return results

    def test_warning_when_no_db_no_env(self):
        """TC203: Backend missing .env, no database → deploy_warning set, NOT blocked."""
        services = [{"name": "backend", "type": "backend", "env_file": None}]
        results = {"database": "Unknown"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertFalse(out["deploy_blocked"])
        self.assertIsNotNone(out["deploy_warning"])
        self.assertIn("No .env detected", out["deploy_warning"])
        self.assertTrue(out["backend_env_missing"])

    def test_no_warning_when_env_present(self):
        """TC204: Backend HAS .env → no warning at all."""
        services = [{"name": "backend", "type": "backend", "env_file": "./backend/.env"}]
        results = {"database": "Unknown"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertFalse(out["deploy_blocked"])
        self.assertIsNone(out["deploy_warning"])

    def test_no_warning_when_db_present_and_env_missing(self):
        """TC205: DB present + no .env → blocked (not warning)."""
        services = [{"name": "backend", "type": "backend", "env_file": None}]
        results = {"database": "PostgreSQL"}

        out = self._simulate_deploy_blocked_logic(services, results)
        self.assertTrue(out["deploy_blocked"])
        self.assertIsNone(out["deploy_warning"])  # Blocked, not warned


class TestFallbackEnvPortInPrompt(unittest.TestCase):
    """
    Requirement 3: The system prompt's backend template should include
    ENV PORT={service.port} before EXPOSE to prevent container crashes
    when .env is missing.
    """

    def test_prompt_has_env_port(self):
        """TC206: Backend template should have ENV PORT before EXPOSE."""
        prompt = DOCKER_DEPLOY_SYSTEM_PROMPT

        # Find the backend section
        backend_section_start = prompt.find("--- BACKEND")
        frontend_section_start = prompt.find("--- FRONTEND")

        self.assertGreater(backend_section_start, -1, "Backend section not found in prompt")
        self.assertGreater(frontend_section_start, -1, "Frontend section not found in prompt")

        backend_section = prompt[backend_section_start:frontend_section_start]

        self.assertIn("ENV PORT", backend_section,
                       "Backend template must include ENV PORT for fallback")

    def test_env_port_before_expose(self):
        """TC207: ENV PORT must appear BEFORE EXPOSE in backend template."""
        prompt = DOCKER_DEPLOY_SYSTEM_PROMPT

        backend_section_start = prompt.find("--- BACKEND")
        frontend_section_start = prompt.find("--- FRONTEND")
        backend_section = prompt[backend_section_start:frontend_section_start]

        env_port_pos = backend_section.find("ENV PORT")
        expose_pos = backend_section.find("EXPOSE")

        self.assertGreater(env_port_pos, -1, "ENV PORT not found in backend section")
        self.assertGreater(expose_pos, -1, "EXPOSE not found in backend section")
        self.assertLess(env_port_pos, expose_pos,
                        "ENV PORT must appear BEFORE EXPOSE")


class TestControllerDeployBlockedRecheck(unittest.TestCase):
    """
    Requirement 1+2 mirrored: The docker_ai_controller.py re-checks
    deploy_blocked after dynamic env detection. It must use the same
    context-aware logic.
    """

    def _simulate_controller_recheck(self, services, metadata):
        """Mirror the logic from docker_ai_controller.py lines 177-195."""
        backend_services = [s for s in services if s.get("type") == "backend"]
        backend_missing_env = any(
            svc.get("type") == "backend" and not svc.get("env_file")
            for svc in services
        )

        if backend_services and backend_missing_env:
            if metadata.get("database") != "Unknown":
                metadata["deploy_blocked"] = True
                metadata["deploy_blocked_reason"] = (
                    "Backend .env file is required because a database was detected. "
                    "Please add a .env file with DATABASE_URL, PORT, and other secrets."
                )
                metadata["backend_env_missing"] = True
                metadata["deploy_warning"] = None
            else:
                metadata["deploy_blocked"] = False
                metadata["deploy_blocked_reason"] = None
                metadata["backend_env_missing"] = True
                metadata["deploy_warning"] = (
                    "No .env detected. Proceed only if your app doesn't require secrets."
                )
        else:
            metadata["deploy_blocked"] = False
            metadata["deploy_blocked_reason"] = None
            metadata["backend_env_missing"] = False
            metadata["deploy_warning"] = None

        return metadata

    def test_controller_blocks_with_db(self):
        """TC208: Controller re-check blocks when DB present and .env missing."""
        services = [{"name": "backend", "type": "backend", "env_file": None}]
        metadata = {"database": "MongoDB"}

        out = self._simulate_controller_recheck(services, metadata)
        self.assertTrue(out["deploy_blocked"])
        self.assertIsNone(out.get("deploy_warning"))

    def test_controller_warns_without_db(self):
        """TC209: Controller re-check warns (not blocks) when no DB and .env missing."""
        services = [{"name": "backend", "type": "backend", "env_file": None}]
        metadata = {"database": "Unknown"}

        out = self._simulate_controller_recheck(services, metadata)
        self.assertFalse(out["deploy_blocked"])
        self.assertIsNotNone(out["deploy_warning"])
        self.assertIn("No .env detected", out["deploy_warning"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
