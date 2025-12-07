"""
Unit Tests for DevOps AutoPilot - Database Detection Module

These tests verify the database detection functionality including
PostgreSQL, MongoDB, MySQL, and Redis detection via dependencies
and environment variables.

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

from app.utils.detector import (
    parse_dependencies_file,
    detect_env_variables,
    DB_INDICATORS,
)


class TestDatabaseDetectionViaDependencies(unittest.TestCase):
    """Test cases for database detection through dependencies."""

    def setUp(self):
        """Initialize test environment."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Cleanup test artifacts."""
        shutil.rmtree(self.test_dir)

    def test_detect_mongodb_python(self):
        """TC063: Verify MongoDB detection via pymongo dependency."""
        req_path = os.path.join(self.test_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("fastapi==0.100.0\npymongo==4.5.0\nmotor==3.3.0")
        
        deps = parse_dependencies_file(req_path, "requirements.txt")
        
        # Check if MongoDB indicators match
        mongo_deps = DB_INDICATORS.get("MongoDB", {}).get("dependencies", [])
        found = any(dep in deps for dep in mongo_deps)
        self.assertTrue(found or "pymongo" in deps or "motor" in deps)

    def test_detect_postgresql_python(self):
        """TC064: Verify PostgreSQL detection via psycopg2."""
        req_path = os.path.join(self.test_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("django==4.2.0\npsycopg2-binary==2.9.9")
        
        deps = parse_dependencies_file(req_path, "requirements.txt")
        
        self.assertIn("psycopg2-binary", deps)

    def test_detect_mysql_nodejs(self):
        """TC065: Verify MySQL detection via mysql2 package."""
        pkg_path = os.path.join(self.test_dir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump({
                "dependencies": {"express": "^4.18.0", "mysql2": "^3.6.0"}
            }, f)
        
        deps = parse_dependencies_file(pkg_path, "package.json")
        
        self.assertIn("mysql2", deps)

    def test_detect_redis_python(self):
        """TC066: Verify Redis detection via redis-py."""
        req_path = os.path.join(self.test_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("celery==5.3.0\nredis==5.0.0\naioredis==2.0.0")
        
        deps = parse_dependencies_file(req_path, "requirements.txt")
        
        self.assertIn("redis", deps)

    def test_detect_mongoose_nodejs(self):
        """TC067: Verify MongoDB detection via mongoose ODM."""
        pkg_path = os.path.join(self.test_dir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump({
                "dependencies": {"express": "^4.18.0", "mongoose": "^8.0.0"}
            }, f)
        
        deps = parse_dependencies_file(pkg_path, "package.json")
        
        self.assertIn("mongoose", deps)


class TestDatabaseDetectionViaEnvVariables(unittest.TestCase):
    """Test cases for database detection through environment variables."""

    def setUp(self):
        """Create test directory with env file."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove test directory."""
        shutil.rmtree(self.test_dir)

    def test_detect_mongodb_env(self):
        """TC068: Verify MongoDB detection via MONGODB_URL env var."""
        env_path = os.path.join(self.test_dir, ".env")
        with open(env_path, "w") as f:
            f.write("MONGODB_URL=mongodb://localhost:27017/mydb\n")
            f.write("PORT=8000")
        
        env_vars = detect_env_variables(self.test_dir)
        
        self.assertIn("MONGODB_URL", env_vars)

    def test_detect_postgres_env(self):
        """TC069: Verify PostgreSQL detection via DATABASE_URL."""
        env_path = os.path.join(self.test_dir, ".env")
        with open(env_path, "w") as f:
            f.write("DATABASE_URL=postgresql://user:pass@localhost:5432/db\n")
        
        env_vars = detect_env_variables(self.test_dir)
        
        self.assertIn("DATABASE_URL", env_vars)

    def test_detect_redis_env(self):
        """TC070: Verify Redis detection via REDIS_URL env var."""
        env_path = os.path.join(self.test_dir, ".env.example")
        with open(env_path, "w") as f:
            f.write("REDIS_URL=redis://localhost:6379\n")
            f.write("REDIS_HOST=localhost")
        
        env_vars = detect_env_variables(self.test_dir)
        
        self.assertIn("REDIS_URL", env_vars)

    def test_detect_multiple_databases(self):
        """TC071: Verify detection of multiple database configs."""
        env_path = os.path.join(self.test_dir, ".env")
        with open(env_path, "w") as f:
            f.write("MONGO_URI=mongodb://localhost:27017\n")
            f.write("POSTGRES_URL=postgresql://localhost:5432\n")
            f.write("REDIS_HOST=localhost")
        
        env_vars = detect_env_variables(self.test_dir)
        
        self.assertIn("MONGO_URI", env_vars)
        self.assertIn("POSTGRES_URL", env_vars)
        self.assertIn("REDIS_HOST", env_vars)


class TestDatabaseIndicatorConfig(unittest.TestCase):
    """Test cases for database indicator configuration."""

    def test_postgresql_indicators_exist(self):
        """TC072: Verify PostgreSQL indicators are configured."""
        self.assertIn("PostgreSQL", DB_INDICATORS)
        self.assertIn("dependencies", DB_INDICATORS["PostgreSQL"])

    def test_mongodb_indicators_exist(self):
        """TC073: Verify MongoDB indicators are configured."""
        self.assertIn("MongoDB", DB_INDICATORS)

    def test_redis_indicators_exist(self):
        """TC074: Verify Redis indicators are configured."""
        self.assertIn("Redis", DB_INDICATORS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
