"""
Unit Tests for DevOps AutoPilot - Command Extractor Module

These tests verify the functionality of extracting build and start commands
from various project configuration files (package.json, requirements.txt, etc.)

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

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.command_extractor import (
    extract_nodejs_commands,
    extract_python_commands,
    extract_database_info,
    _parse_vite_config,
    _parse_vue_config,
    _parse_webpack_config,
)


class TestExtractNodejsCommands(unittest.TestCase):
    """Test cases for Node.js command extraction from package.json."""

    def setUp(self):
        """Create a temporary directory for test projects."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def test_extract_start_command_node(self):
        """TC031: Verify extraction of 'node app.js' start command."""
        pkg_content = {
            "scripts": {"start": "node app.js"},
            "dependencies": {},
        }
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["start_command"], "node app.js")
        self.assertEqual(result["entry_point"], "app.js")
        self.assertTrue(result["has_start_script"])

    def test_extract_nodemon_converts_to_node(self):
        """TC032: Verify nodemon command converts to node for production."""
        pkg_content = {
            "scripts": {"start": "nodemon server.js"},
            "dependencies": {},
        }
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["start_command"], "node server.js")
        self.assertEqual(result["entry_point"], "server.js")

    def test_extract_main_entry_fallback(self):
        """TC033: Verify fallback to 'main' field when no start script."""
        pkg_content = {"main": "index.js", "dependencies": {}}
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["entry_point"], "index.js")
        self.assertEqual(result["start_command"], "node index.js")

    def test_detect_vite_build_output(self):
        """TC034: Verify Vite project uses 'dist' as build output."""
        pkg_content = {
            "scripts": {"build": "vite build"},
            "dependencies": {"vite": "^5.0.0"},
        }
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["build_output"], "dist")
        self.assertEqual(result["build_command"], "npm run build")

    def test_detect_cra_build_output(self):
        """TC035: Verify Create React App uses 'build' as output."""
        pkg_content = {
            "scripts": {"build": "react-scripts build"},
            "dependencies": {"react-scripts": "^5.0.0"},
        }
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["build_output"], "build")

    def test_detect_nextjs_build_output(self):
        """TC036: Verify Next.js uses '.next' as build output."""
        pkg_content = {
            "scripts": {"build": "next build"},
            "dependencies": {"next": "^14.0.0"},
        }
        with open(os.path.join(self.test_dir, "package.json"), "w") as f:
            json.dump(pkg_content, f)

        result = extract_nodejs_commands(self.test_dir)
        self.assertEqual(result["build_output"], ".next")

    def test_no_package_json(self):
        """TC037: Verify empty result when no package.json exists."""
        result = extract_nodejs_commands(self.test_dir)
        self.assertIsNone(result["start_command"])
        self.assertIsNone(result["entry_point"])
        self.assertFalse(result["has_start_script"])


class TestExtractPythonCommands(unittest.TestCase):
    """Test cases for Python command extraction."""

    def setUp(self):
        """Create a temporary directory for test projects."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def test_detect_django_manage_py(self):
        """TC038: Verify Django project detection via manage.py."""
        with open(os.path.join(self.test_dir, "manage.py"), "w") as f:
            f.write("#!/usr/bin/env python\nimport django")

        result = extract_python_commands(self.test_dir)
        self.assertEqual(result["entry_point"], "manage.py")
        self.assertIn("runserver", result["start_command"])
        self.assertIn("0.0.0.0:8000", result["start_command"])

    def test_detect_fastapi_app(self):
        """TC039: Verify FastAPI application detection."""
        fastapi_content = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
"""
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write(fastapi_content)

        result = extract_python_commands(self.test_dir)
        self.assertEqual(result["entry_point"], "main.py")
        self.assertIn("uvicorn", result["start_command"])

    def test_detect_flask_app(self):
        """TC040: Verify Flask application detection."""
        flask_content = """
from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World"
"""
        with open(os.path.join(self.test_dir, "app.py"), "w") as f:
            f.write(flask_content)

        result = extract_python_commands(self.test_dir)
        self.assertEqual(result["entry_point"], "app.py")
        self.assertIn("flask", result["start_command"].lower())


class TestParseViteConfig(unittest.TestCase):
    """Test cases for Vite configuration parsing."""

    def setUp(self):
        """Create a temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_parse_custom_outdir(self):
        """TC041: Verify extraction of custom outDir from vite.config.js."""
        vite_config = """
export default {
    build: {
        outDir: 'public'
    }
}
"""
        with open(os.path.join(self.test_dir, "vite.config.js"), "w") as f:
            f.write(vite_config)

        result = _parse_vite_config(self.test_dir)
        self.assertEqual(result, "public")

    def test_parse_default_when_no_outdir(self):
        """TC042: Verify None returned when no custom outDir."""
        vite_config = """
export default {
    plugins: []
}
"""
        with open(os.path.join(self.test_dir, "vite.config.js"), "w") as f:
            f.write(vite_config)

        result = _parse_vite_config(self.test_dir)
        self.assertIsNone(result)


class TestParseVueConfig(unittest.TestCase):
    """Test cases for Vue CLI configuration parsing."""

    def setUp(self):
        """Create a temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_parse_custom_output_dir(self):
        """TC043: Verify extraction of outputDir from vue.config.js."""
        vue_config = """
module.exports = {
    outputDir: 'dist-custom',
    lintOnSave: false
}
"""
        with open(os.path.join(self.test_dir, "vue.config.js"), "w") as f:
            f.write(vue_config)

        result = _parse_vue_config(self.test_dir)
        self.assertEqual(result, "dist-custom")


class TestParseWebpackConfig(unittest.TestCase):
    """Test cases for Webpack configuration parsing."""

    def setUp(self):
        """Create a temporary directory."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_parse_output_path(self):
        """TC044: Verify extraction of output.path from webpack.config.js."""
        webpack_config = """
const path = require('path');
module.exports = {
    output: {
        path: path.resolve(__dirname, 'build'),
        filename: 'bundle.js'
    }
}
"""
        with open(os.path.join(self.test_dir, "webpack.config.js"), "w") as f:
            f.write(webpack_config)

        result = _parse_webpack_config(self.test_dir)
        self.assertEqual(result, "build")


class TestExtractDatabaseInfo(unittest.TestCase):
    """Test synthesized DB env defaults when no .env is present."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_synthesizes_mongodb_default_env(self):
        result = extract_database_info(self.test_dir, detected_db="mongodb")
        self.assertEqual(result["db_type"], "mongodb")
        self.assertTrue(result["needs_container"])
        self.assertEqual(result["env_var_name"], "MONGO_URI=mongodb://mongo:27017/app")

    def test_synthesizes_postgresql_default_env(self):
        result = extract_database_info(self.test_dir, detected_db="postgresql")
        self.assertEqual(result["db_type"], "postgresql")
        self.assertTrue(result["needs_container"])
        self.assertEqual(
            result["env_var_name"],
            "DATABASE_URL=postgresql://postgres:postgres@postgres:5432/app",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
