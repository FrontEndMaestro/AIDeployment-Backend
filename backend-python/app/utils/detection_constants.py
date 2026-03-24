"""
Shared constants and tiny helpers used across detection modules.
Extracted from detector.py to reduce its size.
"""

from typing import Dict


# Concrete detection rules (these are highly reliable)
LANGUAGE_INDICATORS = {
    "Python": {
        "extensions": [".py"],
        "files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
        "imports": ["import django", "import flask", "import fastapi", "import requests", "from django", "from flask"],
        "weight": 1.0
    },
    "JavaScript": {
        "extensions": [".js", ".jsx"],
        "files": ["package.json", "package-lock.json", "yarn.lock"],
        "imports": ["require('", "import {", "import '", "from '", "export "],
        "weight": 1.0
    },
    "TypeScript": {
        "extensions": [".ts", ".tsx"],
        "files": ["tsconfig.json"],
        "imports": ["interface ", "type "],
        "weight": 1.0
    },
    "Java": {
        "extensions": [".java"],
        "files": ["pom.xml", "build.gradle", "settings.gradle"],
        "imports": ["import java", "package "],
        "weight": 1.0
    },
    "Go": {
        "extensions": [".go"],
        "files": ["go.mod", "go.sum"],
        "imports": ["package main", "import ("],
        "weight": 1.0
    },
    "Ruby": {
        "extensions": [".rb"],
        "files": ["Gemfile", "Gemfile.lock"],
        "imports": ["require '", "gem "],
        "weight": 1.0
    },
    "PHP": {
        "extensions": [".php"],
        "files": ["composer.json", "composer.lock"],
        "imports": ["<?php", "namespace ", "use "],
        "weight": 1.0
    }
}

FRAMEWORK_INDICATORS = {
    "Flask": {
        "markers": ["from flask import", "Flask(__name__)", "@app.route"],
        "files": [],
        "dependencies": ["flask", "Flask"],
        "confidence_weight": 0.95
    },
    "Django": {
        "markers": ["from django", "django.conf", "settings.INSTALLED_APPS", "manage.py"],
        "files": ["manage.py", "settings.py"],
        "dependencies": ["django", "Django"],
        "confidence_weight": 0.95
    },
    "FastAPI": {
        "markers": ["from fastapi import", "FastAPI()", "app.get(", "app.post("],
        "files": [],
        "dependencies": ["fastapi", "FastAPI"],
        "confidence_weight": 0.95
    },
    "Express.js": {
        "markers": ["require('express')", "const express", "app.listen", "app.get(", "app.post("],
        "files": [],
        "dependencies": ["express", "@types/express", "ts-node", "tsx"],
        "confidence_weight": 0.95
    },
    "Next.js": {
        "markers": ["next/", "getServerSideProps", "getStaticProps", "pages/"],
        "files": ["next.config.js"],
        "dirs": ["pages"],
        "dependencies": ["next"],
        "confidence_weight": 0.95
    },
    "React": {
        "markers": ["import React", "from 'react'", "useState(", "useEffect(", "JSX"],
        "files": [],
        "dependencies": ["react", "@types/react", "@types/react-dom"],
        "confidence_weight": 0.9
    },
    "Spring Boot": {
        "markers": ["@SpringBootApplication", "@RestController", "@GetMapping", "@Autowired"],
        "files": ["pom.xml", "application.properties"],
        "dependencies": ["spring-boot", "spring-web"],
        "confidence_weight": 0.95
    },
    "Laravel": {
        "markers": ["use Illuminate", "Route::", "Schema::", "artisan"],
        "files": ["artisan", "config/app.php"],
        "dependencies": ["laravel"],
        "confidence_weight": 0.95
    },
    "Rails": {
        "markers": ["rails", "ActiveRecord", "has_many", "belongs_to", "Gemfile"],
        "files": ["Gemfile", "config/routes.rb"],
        "dependencies": ["rails"],
        "confidence_weight": 0.95
    }
}

# Simple mapping to tie frameworks to primary language for scoring
FRAMEWORK_LANGUAGES: Dict[str, str] = {
    "Flask": "Python",
    "Django": "Python",
    "FastAPI": "Python",
    "Express.js": "JavaScript",
    "Next.js": "JavaScript",
    "React": "JavaScript",
    "Spring Boot": "Java",
    "Laravel": "PHP",
    "Rails": "Ruby",
}


def _languages_compatible(detected: str, expected: str) -> bool:
    """
    Treat JavaScript and TypeScript as compatible for JS ecosystem frameworks
    (e.g., React/Next/Express) so valid framework detections aren't erased.
    """
    if detected == expected:
        return True
    js_like = {"JavaScript", "TypeScript"}
    return detected in js_like and expected in js_like


# --- Database indicator config (for DB detection) ---

DB_INDICATORS = {
    "PostgreSQL": {
        "dependencies": [
            "psycopg2", "psycopg2-binary", "asyncpg", "pg", "pg-promise",
            "org.postgresql", "postgresql", "pgx", "pq"
        ],
        "env_keys": ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL"],
        "compose_images": ["postgres"]
    },
    "MySQL": {
        "dependencies": [
            "mysqlclient", "pymysql", "mysql-connector", "mysql-connector-python",
            "mysql2", "mysql", "mariadb-java-client", "mariadb"
        ],
        "env_keys": ["MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"],
        "compose_images": ["mysql", "mariadb"]
    },
    "MongoDB": {
        "dependencies": ["pymongo", "mongoengine", "mongoose", "mongodb", "motor"],
        "env_keys": ["MONGO_URI", "MONGODB_URI"],
        "compose_images": ["mongo"]
    },
    "SQLite": {
        "dependencies": ["sqlite3"],
        "env_keys": [],
        "compose_images": []
    },
    "Redis": {
        "dependencies": ["redis", "aioredis", "ioredis"],
        "env_keys": ["REDIS_URL", "REDIS_HOST"],
        "compose_images": ["redis"]
    }
}

DB_ENV_KEYWORDS = {
    "PostgreSQL": ["postgres", "postgresql", "pg"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongo", "mongodb"],
    "Redis": ["redis"],
    "SQLite": ["sqlite"],
}


# --- Service classification dep sets (Fix 1 / Fix 4) ---
BACKEND_DEPS = {
    "express", "fastify", "koa", "hapi", "@nestjs/core",
    "apollo-server", "graphql-yoga", "@hapi/hapi", "hono", "elysia",
}

FRONTEND_DEPS = {
    "react", "vue", "svelte", "next", "nuxt", "vite",
    "react-scripts", "react-dom", "@vitejs/plugin-react",
    "@vue/cli-service", "gatsby", "@sveltejs/kit",
}

WORKER_DEPS = {
    "celery", "dramatiq", "rq", "huey",          # Python workers
    "bull", "bullmq", "bee-queue", "agenda",      # Node workers
    "amqplib", "amqp", "kafkajs", "kafka-node",  # Message queue clients
}

DB_DRIVER_ONLY_DEPS = {
    "pg", "pg-promise", "mysql2", "mongoose",
    "pymongo", "psycopg2", "asyncpg",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".next", "coverage", "test", "tests", ".cache",
}

PYTHON_BACKEND_DEPS = {
    "fastapi", "flask", "django", "starlette", "tornado", "aiohttp", "sanic",
    "falcon", "bottle",
}

DB_KEYWORDS = {
    "postgres", "postgresql", "mysql", "mongo", "mongodb", "redis",
    "elasticsearch", "cassandra", "sqlite", "db", "database",
}

PYTHON_SKIP_DIRS = SKIP_DIRS | {"venv", ".venv", "env"}


def norm_path(p: str) -> str:
    """Normalise a path: backslashes -> forward, strip trailing slashes, empty -> '.'."""
    if not p:
        return "."
    p = p.replace("\\", "/").rstrip("/")
    return p if p else "."


def _normalize_dep_name(dep: str) -> str:
    """Best-effort normalize a dependency spec into a package name."""
    dep = (dep or "").strip()
    if not dep:
        return ""

    # Drop environment markers and direct references
    dep = dep.split(";", 1)[0].strip()
    if dep.startswith("@"):
        if "@" in dep[1:]:
            dep = dep.rsplit("@", 1)[0].strip()
    else:
        dep = dep.split("@", 1)[0].strip()

    # Strip extras (e.g., fastapi[standard])
    dep = dep.split("[", 1)[0].strip()

    # Strip version / comparator noise
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "="):
        if sep in dep:
            dep = dep.split(sep, 1)[0].strip()
            break

    # Some formats include whitespace (e.g., "pkg >= 1.0")
    dep = dep.split(None, 1)[0].strip()
    return dep
