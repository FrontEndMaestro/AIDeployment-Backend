# DevOps AutoPilot — Complete System Documentation

**Author:** Abdul Ahad Abbassi  
**Date:** February 2026  
**Purpose:** Comprehensive technical reference covering all inputs, AI prompts, environment handling, and data flow

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Configuration & Settings](#3-configuration--settings)
4. [API Endpoints (Full Reference)](#4-api-endpoints-full-reference)
5. [User Upload Flow](#5-user-upload-flow)
6. [Project Extraction Flow](#6-project-extraction-flow)
7. [Analysis Pipeline — Detection Modules](#7-analysis-pipeline--detection-modules)
8. [AI / LLM Integration](#8-ai--llm-integration)
9. [Docker AI Controller — Deploy Flow](#9-docker-ai-controller--deploy-flow)
10. [Environment File (.env) Handling](#10-environment-file-env-handling)
11. [Deploy Blocked / Deploy Warning Logic](#11-deploy-blocked--deploy-warning-logic)
12. [Authentication](#12-authentication)
13. [Database Schema (MongoDB)](#13-database-schema-mongodb)
14. [Frontend Integration](#14-frontend-integration)
15. [AWS Terraform Deployment](#15-aws-terraform-deployment)

---

## 1. System Overview

DevOps AutoPilot is a full-stack AI-powered DevOps tool that:

1. Accepts a **user's project archive** (ZIP / TAR / TGZ)
2. **Extracts** and **analyses** it automatically (language, framework, ports, DB, services)
3. Feeds structured project metadata into a **local LLM** (Llama / Qwen via Ollama)
4. The LLM **generates or validates** `Dockerfile`s and `docker-compose.yml`
5. Allows the user to **build, run, and push** Docker images from the UI
6. (Optional) Generates **Terraform** configs for AWS ECS/ECR deployment

### Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.11+) |
| Database | MongoDB 7.x (Motor async) |
| LLM Runtime | Ollama — `qwen2.5-coder:7b` (local) |
| ML Analyser | scikit-learn (language/framework classification) |
| Frontend | React + TypeScript (Vite) |
| Docker Operation | Python `subprocess` + Docker CLI |

---

## 2. Architecture

```
User Browser
    │
    ▼
React Frontend (port 5173)
    │  REST + SSE streaming
    ▼
FastAPI Backend (port 8000)
    ├── upload_controller     ← receives zip/tar
    ├── extract_controller    ← unzips to ./extracted/user_X/
    ├── analyze_controller    ← runs detector.py (orchestrator)
    ├── docker_ai_controller  ← calls LLM + runs docker
    └── aws_deploy_controller ← calls LLM for Terraform
         │
    Detection Modules (app/utils/)
    ├── detector.py                ← orchestrator + re-export hub
    ├── detection_constants.py     ← shared constants & helpers
    ├── detection_language.py      ← language/framework detection
    ├── detection_ports.py         ← port detection (env, pkg, Docker)
    ├── detection_database.py      ← database detection & scoring
    ├── detection_services.py      ← service inference
    ├── command_extractor.py       ← Node.js/Python command extraction
    └── ml_analyzer.py             ← ML-based classification
         │
         ▼
    LLM Layer (app/LLM/)
    ├── llm_client.py         ← HTTP calls to Ollama
    ├── docker_deploy_agent.py← system prompt + user message builder
    └── terraform_deploy_agent.py
         │
         ▼
    Ollama (http://localhost:11434)
    └── Model: qwen2.5-coder:7b
         │
         ▼
    MongoDB (localhost:27017)
    └── DB: devops_autopilot → collection: projects
```

---

## 3. Configuration & Settings

All configuration lives in `backend-python/app/config/settings.py` and is loaded from `backend-python/.env`.

```python
# backend-python/.env (example)
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=devops_autopilot
HOST=0.0.0.0
PORT=8000
UPLOAD_DIR=./uploads
EXTRACTED_DIR=./extracted
MAX_FILE_SIZE=104857600          # 100 MB
ENVIRONMENT=development

# LLM
OLLAMA_URL=http://localhost:11434/api/generate
LLM_MODEL_NAME=qwen2.5-coder:7b
LLM_TEMPERATURE=0.1
LLM_TOP_P=0.9
LLM_TIMEOUT=600                  # seconds

# Docker Hub (optional, for push)
DOCKER_HUB_USERNAME=myuser
DOCKER_HUB_PASSWORD=mypassword

# AWS (optional, for Terraform)
AWS_PROFILE=my-terraform
AWS_DEFAULT_REGION=us-east-1
TERRAFORM_PATH=terraform
```

### Key Defaults

| Setting | Value | Purpose |
|---|---|---|
| `LLM_MODEL_NAME` | `qwen2.5-coder:7b` | Local code-focused LLM |
| `LLM_TEMPERATURE` | `0.1` | Near-deterministic output |
| `LLM_TOP_P` | `0.9` | Nucleus sampling |
| `LLM_TIMEOUT` | `600s` | 10-minute max wait |
| `num_ctx` | `16384` (non-stream) / `8192` (stream) | Context window |
| `MAX_FILE_SIZE` | `100 MB` | Upload cap |

---

## 4. API Endpoints (Full Reference)

All endpoints are prefixed with `/api`. Authentication via JWT Bearer token (except `/auth`).

### Auth Routes (`/api/auth`)

| Method | Path | Description | Inputs |
|---|---|---|---|
| POST | `/register` | Create user account | `username`, `email`, `password` |
| POST | `/login` | Get JWT token | `username`, `password` |
| GET | `/me` | Current user info | Bearer token |

### Project Upload (`/api/projects`)

| Method | Path | Description | Inputs |
|---|---|---|---|
| POST | `/upload` | Upload zip/tar file | `file` (multipart), `project_name` (optional), Bearer token |
| GET | `/` | List all user projects | Bearer token |
| GET | `/{id}` | Get project by ID | Bearer token |
| DELETE | `/{id}` | Delete project + files | Bearer token |

### Extraction (`/api/projects/{id}`)

| Method | Path | Description |
|---|---|---|
| POST | `/extract` | Unzip to `./extracted/user_X/` |
| GET | `/files` | List extracted files/folders |
| GET | `/extraction-status` | Check status |
| DELETE | `/cleanup` | Remove extracted files |

### Analysis (`/api/projects/{id}`)

| Method | Path | Description | Inputs |
|---|---|---|---|
| POST | `/analyze` | Run detector.py | `use_ml: bool` (default true) |
| GET | `/analysis` | Get stored analysis | — |

### Docker AI (`/api/projects/{id}`)

| Method | Path | Description |
|---|---|---|
| GET | `/docker-context` | Get metadata + Dockerfiles + file tree (re-checks .env) |
| POST | `/docker-generate` | Call LLM to generate/validate Dockerfiles |
| POST | `/docker-chat` | Free-form chat with LLM about Docker |
| POST | `/docker-stream` | SSE-streamed LLM generation |
| POST | `/docker-build` | `docker build` — streams output |
| POST | `/docker-run` | `docker run` — streams output |
| POST | `/docker-push` | `docker push` — streams output |

### AWS Deployment (`/api/projects/{id}`)

| Method | Path | Description |
|---|---|---|
| POST | `/aws-deploy` | Generate Terraform + apply |
| GET | `/aws-status` | Check Terraform state |
| POST | `/aws-destroy` | Run `terraform destroy` |

---

## 5. User Upload Flow

```
User selects file → POST /api/projects/upload
    │
    ▼
upload_controller.py
    ├── Validates: allowed extensions = [.zip, .tar, .gz, .tgz]
    ├── Saves to: ./uploads/user_{username}/{timestamp}-{filename}
    ├── Creates MongoDB document with status = "uploaded"
    └── Returns: { project_id, project_name, file_size }
```

**Initial MongoDB document fields created at upload:**

```json
{
  "user_id": "<ObjectId>",
  "username": "alice",
  "project_name": "mern-blog",
  "file_name": "mern-blog.zip",
  "file_path": "./uploads/user_alice/20260220120000-mern-blog.zip",
  "file_size": 1048576,
  "status": "uploaded",
  "extracted_path": null,
  "metadata": {
    "framework": "Unknown",
    "language": "Unknown",
    "runtime": null,
    "dependencies": [],
    "port": null,
    "env_variables": []
  }
}
```

---

## 6. Project Extraction Flow

```
POST /api/projects/{id}/extract
    │
    ▼
extract_controller.py
    ├── Sets status = "extracting"
    ├── Calls extractor.extract_file(file_path, project_id, user_workspace)
    │       └── Unzips to: ./extracted/user_{username}/{project_id}/
    ├── Records: files_count, folders_count
    ├── Sets status = "extracted"
    └── Returns: { extracted_path, files_count, folders_count }
```

---

## 7. Analysis Pipeline — Detection Modules

This is the heart of the detection system. Triggered by `POST /api/projects/{id}/analyze`.

### 7.0 Module Architecture

The detection logic is split across 5 focused modules + an orchestrator:

| Module | LOC | Responsibility |
|---|---|---|
| `detection_constants.py` | ~220 | All shared constants (`LANGUAGE_INDICATORS`, `DB_INDICATORS`, `BACKEND_DEPS`, etc.) and helpers (`norm_path`, `_normalize_dep_name`) |
| `detection_language.py` | ~310 | `parse_dependencies_file`, `heuristic_language_detection`, `heuristic_framework_detection`, `get_runtime_info` |
| `detection_ports.py` | ~530 | Port detection: `detect_ports_for_project`, `_detect_port_from_package_json`, `_scan_js_for_port_hint`, Docker compose/EXPOSE parsing |
| `detection_database.py` | ~230 | `detect_databases`, `_infer_database_port`, `detect_db_and_ports` |
| `detection_services.py` | ~530 | `infer_services`, `_find_all_services_by_deps`, `_find_python_services`, root suppression, empty-shell dropping |
| `detector.py` (orchestrator) | ~620 | `detect_framework`, `find_project_root`, Docker/env helpers + **re-exports all symbols** from the modules above |

> **Import compatibility:** `detector.py` re-exports every symbol from the 5 modules, so all existing `from app.utils.detector import X` paths continue to work unchanged.

### 7.1 What `detect_framework()` Does

Runs a hybrid heuristic + ML pipeline on the extracted project folder:

```
detect_framework(project_path, use_ml=True)          # detector.py
    │
    ├── 1. find_project_root()                        # detector.py
    ├── 2. heuristic_language_detection()              # detection_language.py
    │       ├── Scores: file extensions (+0.3), config files (+0.7), import patterns (+0.4)
    │       └── Languages: Python, JavaScript, TypeScript, Java, Go, Ruby, PHP
    ├── 3. heuristic_framework_detection()             # detection_language.py
    │       ├── Scores: package.json/requirements.txt deps (+0.8), file markers (+0.5)
    │       └── Frameworks: Express.js, React, Next.js, Flask, Django, FastAPI, Spring Boot...
    ├── 4. (if use_ml=True) ML supplement              # ml_analyzer.py
    ├── 5. Scan dependency files                       # detection_language.py
    │       parse_dependencies_file() for:
    │           package.json → deps + devDeps
    │           requirements.txt → skip comments, flags, extras notation
    │           pom.xml → <artifactId> tags
    │           go.mod → module paths
    ├── 6. detect_docker_files()                       # detector.py
    ├── 7. detect_env_variables()                      # detector.py
    ├── 8. detect_db_and_ports()                       # detection_database.py
    │       ├── detect_databases()                     # detection_database.py
    │       │       Databases: MongoDB, PostgreSQL, MySQL, SQLite, Redis
    │       └── detect_ports_for_project()             # detection_ports.py
    │               ├── _read_env_key_values()         # detector.py
    │               ├── _detect_port_from_package_json()# detection_ports.py
    │               ├── _scan_js_for_port_hint()       # detection_ports.py
    │               └── _parse_docker_compose_ports()  # detection_ports.py
    ├── 9. infer_services()                            # detection_services.py
    └── 10. deploy_blocked check                       # detector.py (see Section 11)
```

### 7.2 Full Output of `detect_framework()`

The result dict stored as `project.metadata` in MongoDB:

```json
{
  "framework": "Express.js",
  "language": "JavaScript",
  "runtime": "node:20-alpine",
  "dependencies": ["express", "mongoose", "react", "..."],
  "port": 5000,
  "build_command": "npm install",
  "start_command": "node server.js",
  "entry_point": "server.js",
  "build_output": null,
  "env_variables": ["PORT", "MONGO_URI", "JWT_SECRET"],
  "dockerfile": false,
  "docker_compose": false,
  "detected_files": ["package.json"],
  "has_package_json": true,
  "has_requirements_txt": false,
  "has_manage_py": false,
  "static_only": false,

  "detection_confidence": {
    "language": 0.95,
    "framework": 0.80,
    "method": "heuristic"
  },

  "database": "MongoDB",
  "databases": ["MongoDB"],
  "database_detection": {
    "MongoDB": { "score": 1.8, "evidence": ["dependency:mongoose", "env:MONGO_URI"] }
  },
  "database_port": 27017,
  "database_is_cloud": false,
  "database_env_var": "MONGO_URI",

  "backend_port": 5000,
  "frontend_port": 3000,

  "docker_backend_ports": null,
  "docker_frontend_ports": null,
  "docker_database_ports": null,
  "docker_other_ports": null,
  "docker_backend_container_ports": null,
  "docker_frontend_container_ports": null,
  "docker_database_container_ports": null,
  "docker_other_container_ports": null,
  "docker_expose_ports": null,

  "services": [
    {
      "name": "backend",
      "path": "backend",
      "type": "backend",
      "port": 5000,
      "port_source": "env",
      "entry_point": "server.js",
      "env_file": "./backend/.env",
      "package_manager": { "manager": "npm", "has_lockfile": true }
    },
    {
      "name": "frontend",
      "path": "frontend",
      "type": "frontend",
      "port": 3000,
      "build_output": "dist",
      "package_manager": { "manager": "npm", "has_lockfile": true }
    }
  ],

  "deploy_blocked": false,
  "deploy_blocked_reason": null,
  "backend_env_missing": false,
  "deploy_warning": null
}
```

### 7.3 Service Inference (`infer_services`)

For each detected service, the system builds a service definition dict with:

| Field | Source | Description |
|---|---|---|
| `name` | folder name | e.g. `"backend"`, `"frontend"` |
| `path` | folder path relative to root | e.g. `"backend"`, `"."` |
| `type` | `_infer_service_type()` | `backend / frontend / worker / other` |
| `port` | env file → package.json scripts → JS code scan → default | Listen port |
| `port_source` | detection method | `env / source / pkg_json / default` |
| `entry_point` | `extract_nodejs_commands()` | e.g. `"server.js"` |
| `build_output` | package.json scripts | e.g. `"dist"`, `"build"`, `".next"` |
| `env_file` | `.env` file existence check | e.g. `"./backend/.env"` |
| `package_manager` | lockfile detection | `{manager: "npm", has_lockfile: true}` |

### 7.4 Database Detection Scoring

Each database is scored from multiple signal sources:

| Signal | Weight |
|---|---|
| Dependency match (e.g. `mongoose` → MongoDB) | +1.0 |
| Env var key match (e.g. `MONGO_URI`) | +0.8 |
| docker-compose image match (e.g. `mongo:latest`) | +0.7 |

The **highest scoring** database becomes `primary`.

### 7.5 Port Detection Priority

For JS/TS backends (highest to lowest priority):

1. `PORT=XXXX` in `.env` or `.env.local` (source: `"env"`)
2. `PORT=XXXX` in `package.json` scripts (source: `"pkg_json"`)
3. `app.listen(XXXX)` in source code via regex scan (source: `"source"`)
4. Language default: `3000` for Node.js (source: `"default"`)

---

## 8. AI / LLM Integration

### 8.1 LLM Client (`llm_client.py`)

All LLM calls go through Ollama's HTTP API.

**Non-streaming call:**
```python
POST http://localhost:11434/api/generate
{
  "model": "qwen2.5-coder:7b",
  "prompt": "System: ...\n\nUser: ...\n\nAssistant:",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_ctx": 16384
  }
}
```

**Streaming call** (used for Docker generate/chat in UI):
```python
POST http://localhost:11434/api/generate
{  "stream": true, "options": { "num_ctx": 8192 }  }
# SSE: yields {"token": "...", "done": false}
```

### 8.2 System Prompt (Full — `docker_deploy_agent.py`)

The system prompt is fixed and instructs the LLM on exactly how to generate Docker configs:

```
You are a Docker configuration generator. Produce CORRECT, WORKING Docker configs with ZERO errors.
Use ONLY values from the input. Never assume or invent values.

STEP 1: EXTRACT VALUES
  - PROJECT_NAME, RUNTIME, BACKEND_PORT, FRONTEND_PORT, DATABASE, DATABASE_PORT, DATABASE_IS_CLOUD
  - Per-service: name, path, type, port, entry_point, build_output, env_file, package_manager

STEP 2: DETERMINE TYPE PER SERVICE
  - STATIC_ONLY=True or RUNTIME=nginx → Static site
  - type=frontend AND build_output → Frontend (React/Vue multi-stage build)
  - type=backend → Backend (Node.js server, single-stage)

STEP 3: GENERATE DOCKERFILES

  BACKEND (single-stage):
    FROM {RUNTIME}
    WORKDIR /app
    COPY package*.json ./
    RUN {INSTALL_CMD}         ← npm ci / npm install / yarn install --frozen-lockfile
    COPY . .
    ENV PORT={service.port}   ← ALWAYS set env fallback
    EXPOSE {service.port}
    CMD {CMD_ARRAY}           ← ["node", "{entry_point}"] or ["npm", "start"]

  FRONTEND (multi-stage required):
    FROM {RUNTIME} AS builder
    WORKDIR /app
    COPY package*.json ./
    RUN {INSTALL_CMD}
    COPY . .
    RUN {BUILD_CMD}

    FROM nginx:alpine
    COPY --from=builder /app/{BUILD_OUTPUT} /usr/share/nginx/html
    EXPOSE 80
    CMD ["nginx", "-g", "daemon off;"]

  NEXT.JS (SSR — no nginx):
    FROM {RUNTIME} AS builder / ... / FROM {RUNTIME}
    COPY --from=builder /app/.next ./.next
    EXPOSE {service.port}
    CMD ["npm", "start"]

STEP 4: GENERATE docker-compose.yml
  - Backend: image + build + ports + env_file (if present) + depends_on database
  - Frontend: image + build + ports ("FRONTEND_PORT:80") + depends_on backend
  - Database container: ONLY if DATABASE_IS_CLOUD=False
  - No "version:" field in compose
  - All services must have BOTH "image:" and "build:"

STEP 5: VALIDATE (check single-stage, correct ports, compose rules)

STEP 6: RESPOND
  FORMAT:
    STATUS: Generated | Valid | Invalid
    REASON: summary
    GENERATED FILES:
      **{path}/Dockerfile**
      ```dockerfile … ```
      **docker-compose.yml**
      ```yaml … ```
```

### 8.3 User Message Construction (`build_deploy_message`)

Every LLM call constructs a structured user message from 8 sections:

```
1. MODE: GENERATE_MISSING | VALIDATE_EXISTING
2. PROJECT_NAME: {name} ← USE IN: image: {name}-backend:latest
3. Dockerfile count summary
4. Compose file count summary
5. === CONFIGURATION VALUES ===
   RUNTIME: node:20-alpine ← USE IN: FROM node:20-alpine
   BACKEND_PORT: 5000 ← USE IN: EXPOSE 5000, ports: "5000:5000"
   FRONTEND_PORT: 3000 ← USE IN: ports: "3000:80"
   DATABASE: MongoDB
   DATABASE_PORT: 27017
   DATABASE_IS_CLOUD: True | False
   DATABASE_ENV_VAR: MONGO_URI
   BUILD_COMMAND: npm install
   START_COMMAND: node server.js
   ENTRY_POINT: server.js
   BUILD_OUTPUT: dist
   Environment variables: PORT, MONGO_URI, JWT_SECRET
   Dependencies: express, mongoose, react ...
6. Existing Dockerfile contents (if any)
7. Existing docker-compose.yml contents (if any)
8. File tree (depth=4, max 200 entries)
9. ⚠️⚠️⚠️ SERVICE DEFINITIONS (per service):
   - name: backend, path: backend, type: backend, PORT: 5000 (from env),
     entry_point: server.js, env_file: ./backend/.env,
     package_manager: npm (USE: npm ci)
   - name: frontend, path: frontend, type: frontend, PORT: 3000,
     build_output: dist (USE /app/dist), package_manager: npm (USE: npm ci, npm run build)
10. User message: "Generate all required Docker files..."
    (auto-enhanced when mode=GENERATE_MISSING and user said just "generate")
```

### 8.4 Mode Auto-Detection

| Condition | Mode |
|---|---|
| Dockerfiles or docker-compose.yml exist in project | `VALIDATE_EXISTING` |
| No Docker files found | `GENERATE_MISSING` |

---

## 9. Docker AI Controller — Deploy Flow

`docker_ai_controller.py` orchestrates the full Docker deploy cycle:

### 9.1 Fetching Context (`GET /docker-context`)

1. Validates project ownership
2. Resolves `extracted_path` → `project_root` (handles nested zip structure)
3. Collects existing Dockerfiles + compose files from disk
4. Builds file tree (text + structured JSON for UI)
5. **Dynamically re-checks `.env` files** on disk (even if analysis was done before user added `.env`)
6. Recalculates `deploy_blocked` / `deploy_warning` based on current disk state
7. Returns: `metadata`, `dockerfiles`, `compose_files`, `file_tree`

### 9.2 Generating Docker Files (`POST /docker-stream`)

1. Retrieves project + metadata from MongoDB
2. Collects existing Docker files from disk
3. Calls `run_docker_deploy_chat_stream()` → Ollama SSE stream
4. Yields tokens to frontend via Server-Sent Events
5. Frontend parses `STATUS:` / `GENERATED FILES:` sections from the stream
6. Frontend saves generated files to disk via a separate file-write endpoint

### 9.3 Build / Run / Push

These use Python `subprocess` calls to the Docker CLI and stream output line-by-line:

```python
# Build
docker build -t {project_name}-{service}:latest ./{service_path}

# Run
docker run -d -p {host_port}:{container_port} {image_name}

# Push
docker tag {image} {hub_username}/{image}
docker push {hub_username}/{image}
```

---

## 10. Environment File (.env) Handling

### 10.1 During Analysis (detection modules)

The detection modules read `.env` files at **two layers** — root and nested service directories:

**Files read for key-value detection** (`_read_env_key_values` in `detector.py`):
- `.env`
- `.env.local`
- `.env.development`
- `.env.production`
- `.env.test`
- `.env.example`

**Files read for key-only listing** (`detect_env_variables` in `detector.py`):
- `.env`
- `.env.example`
- `.env.sample`
- `.env.local`

**For DB detection** (`detection_database.py`), the system also reads nested `.env` files inside `backend/`, `server/`, `api/` etc. and merges all key-value pairs before scoring.

**Port from `.env`** — these keys are checked (priority order):

| Keys → Backend Port | Keys → Frontend Port | Keys → Generic (fallback) |
|---|---|---|
| `BACKEND_PORT`, `SERVER_PORT`, `API_PORT` | `FRONTEND_PORT`, `CLIENT_PORT`, `VITE_PORT`, `REACT_APP_PORT` | `PORT` |

### 10.2 During Docker Generation (LLM prompt)

When a service has an `.env` file, the LLM is instructed to add it to `docker-compose.yml`:

```yaml
backend:
  env_file:
    - ./backend/.env    ← added only if env_file is set in service definition
```

If the backend service has **no `.env` file**, the LLM is still told to `ENV PORT={service.port}` in the Dockerfile as a fallback so the container doesn't fail if no env is provided at runtime.

### 10.3 Dynamic Re-Check on Deploy Page

Every time the user opens the Deploy page (`GET /docker-context`), the system **re-checks disk** for `.env` files — not relying on the stored MongoDB metadata. This allows a user to:

1. Upload project (no `.env`)
2. System shows "deploy blocked" warning
3. User manually adds `.env` to the extracted folder on disk
4. User refreshes Deploy page → system detects `.env`, clears the warning

**`.env` files checked per service directory:**
- `.env`
- `.env.local`
- `.env.production`

---

## 11. Deploy Blocked / Deploy Warning Logic

This logic runs in **two places** and produces consistent output both times:

### Where it runs:
1. `detector.py → detect_framework()` — at analysis time
2. `docker_ai_controller.py → get_docker_context_handler()` — at deploy page load

### Decision Matrix:

| Condition | `deploy_blocked` | `deploy_warning` | UI Effect |
|---|---|---|---|
| Backend exists + DB detected + **no .env** | `True` | `null` | 🔴 Red banner, Build/Run/Push buttons disabled |
| Backend exists + **no DB** + **no .env** | `False` | `"No .env detected..."` | 🟡 Amber banner, buttons remain enabled |
| Backend exists + **.env present** | `False` | `null` | ✅ No banner |
| Frontend-only / no backend services | `False` | `null` | ✅ No banner |

### Output fields set on `metadata`:

```json
{
  "deploy_blocked": true,
  "deploy_blocked_reason": "Backend .env file is required because a database was detected...",
  "backend_env_missing": true,
  "deploy_warning": null
}
```

---

## 12. Authentication

- **JWT-based** via `python-jose`
- Token issued on `/api/auth/login`, valid for 30 days
- Passed as `Authorization: Bearer <token>` header
- `decode_access_token()` validates signature + expiry + user existence
- All project endpoints check `user_id` ownership before operating

---

## 13. Database Schema (MongoDB)

**Collection: `projects`**

```json
{
  "_id": "ObjectId",
  "user_id": "string (user ObjectId)",
  "username": "string",
  "project_name": "string",
  "file_name": "string",
  "file_path": "string (absolute path)",
  "file_size": "number (bytes)",
  "upload_date": "datetime",
  "status": "uploaded | extracting | extracted | analyzing | analyzed | completed | failed",
  "extracted_path": "string | null",
  "extraction_date": "datetime | null",
  "files_count": "number",
  "folders_count": "number",
  "extraction_logs": ["string"],
  "metadata": {
    "framework": "Express.js | React | Flask | ...",
    "language": "JavaScript | Python | ...",
    "runtime": "node:20-alpine | python:3.11-slim | ...",
    "dependencies": ["express", "mongoose", "..."],
    "port": 5000,
    "backend_port": 5000,
    "frontend_port": 3000,
    "database_port": 27017,
    "database": "MongoDB | PostgreSQL | Unknown",
    "database_is_cloud": false,
    "database_env_var": "MONGO_URI",
    "env_variables": ["PORT", "MONGO_URI"],
    "dockerfile": false,
    "docker_compose": false,
    "deploy_blocked": false,
    "deploy_blocked_reason": null,
    "backend_env_missing": false,
    "deploy_warning": null,
    "services": [
      {
        "name": "backend",
        "path": "backend",
        "type": "backend",
        "port": 5000,
        "port_source": "env",
        "entry_point": "server.js",
        "env_file": "./backend/.env",
        "package_manager": { "manager": "npm", "has_lockfile": true }
      }
    ],
    "detection_confidence": {
      "language": 0.95,
      "framework": 0.80,
      "method": "heuristic"
    }
  },
  "analysis_date": "datetime | null",
  "analysis_logs": ["string"],
  "logs": [{ "message": "string", "timestamp": "datetime" }],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## 14. Frontend Integration

**File:** `devops-autopilot-frontend/src/pages/DeployPage.tsx`

### Key UI States

| State | Condition | Component shown |
|---|---|---|
| Deploy Blocked | `metadata.deploy_blocked === true` | 🔴 Red banner + disabled buttons |
| Deploy Warning | `!deploy_blocked && deploy_warning != null` | 🟡 Amber banner + enabled buttons |
| Normal | Both false/null | ✅ Clean UI, all buttons enabled |

### TypeScript Types (`src/types/api.ts`)

```typescript
// Deployment blocking flags
deploy_blocked?: boolean;
deploy_blocked_reason?: string | null;
backend_env_missing?: boolean;
deploy_warning?: string | null;   // non-blocking warning
```

### SSE Streaming (Deploy Page)

The frontend connects to `/api/projects/{id}/docker-stream` via `EventSource` and renders tokens in real time as the LLM generates Docker files.

---

## 15. AWS Terraform Deployment

**File:** `app/LLM/terraform_deploy_agent.py` + `aws_deploy_controller.py`

The system can also generate Terraform configurations for AWS ECS + ECR deployment:

1. User triggers AWS deploy from UI
2. `aws_deploy_controller.py` calls the Terraform LLM agent
3. LLM generates:
   - `main.tf` — ECS cluster, task definition, service, ALB
   - `ecr.tf` — ECR repository per service
   - `variables.tf`
   - `outputs.tf`
4. System runs:
   ```bash
   terraform init
   terraform plan
   terraform apply -auto-approve
   ```
5. Streams Terraform output back to UI

> **Note:** Requires `AWS_PROFILE` set in `.env` with appropriate IAM permissions (ECS, ECR, VPC, IAM roles).

---

## Appendix A: File Storage Layout

```
devops-autopilot/
├── backend-python/
│   ├── .env                          ← backend config (gitignored)
│   ├── app/
│   │   └── utils/
│   │       ├── detector.py            ← orchestrator + re-export hub (~620 LOC)
│   │       ├── detection_constants.py ← shared constants & helpers
│   │       ├── detection_language.py  ← language/framework detection
│   │       ├── detection_ports.py     ← port detection (env, pkg, Docker)
│   │       ├── detection_database.py  ← database detection & scoring
│   │       ├── detection_services.py  ← service inference
│   │       ├── command_extractor.py   ← Node.js/Python command extraction
│   │       └── ml_analyzer.py         ← ML-based classification
│   ├── uploads/
│   │   └── user_{username}/
│   │       └── {timestamp}-{file}    ← uploaded archives
│   └── extracted/
│       └── user_{username}/
│           └── {project_id}/         ← unzipped project files
│               ├── backend/
│               │   ├── package.json
│               │   ├── .env          ← user's app secrets (NOT gitignored)
│               │   └── server.js
│               ├── frontend/
│               │   └── package.json
│               ├── Dockerfile         ← generated by LLM
│               └── docker-compose.yml ← generated by LLM
└── devops-autopilot-frontend/
    └── src/
        ├── pages/DeployPage.tsx
        └── types/api.ts
```

---

## Appendix B: Testing

**Test file locations:**

| File | Tests | Coverage |
|---|---|---|
| `backend-python/tests/test_docker_pipeline.py` | 49 tests (unittest) | Docker pipeline, Layer 1–4 |
| `backend-python/tests/test_detector_exhaustive.py` | 133 tests (pytest) | Full detector.py coverage |
| `backend-python/tests/test_detection_comprehensive.py` | 77 tests (pytest) | Real-world MERN scenarios |
| `backend-python/tests/test_database_detection.py` | Database detection | DB scoring & port inference |
| `backend-python/tests/test_port_detection.py` | Port detection | Multi-source port resolution |
| `backend-python/tests/test_command_extractor.py` | Command extraction | Node.js/Python entry points |

**Total: 359 tests** (all passing after modular refactoring)

**Run tests:**
```bash
# Full suite (recommended)
python -m pytest tests/ -v

# Individual test files
python -m pytest tests/test_detector_exhaustive.py -v
python -m pytest tests/test_detection_comprehensive.py -v
python -m pytest tests/test_database_detection.py -v
```

> **Note:** All tests import from `app.utils.detector` — the re-export pattern ensures no test imports needed changing after the modular refactoring.

---

*Document updated: 2026-03-06 | DevOps AutoPilot v1.1 — Modular detection architecture*
