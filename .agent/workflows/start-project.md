---
description: How to start the DevOps Autopilot project (backend + frontend)
---

# Starting DevOps Autopilot

## Prerequisites

- **Python 3.12+** installed
- **Node.js 18+** and npm installed
- **Docker Desktop** running (for MongoDB container)
- **Ollama** running locally with Llama 3.1 model (for AI features)

## 1. Start MongoDB

```powershell
docker start devops-mongo
```

If the container doesn't exist yet, create it:

```powershell
docker run -d --name devops-mongo -p 27017:27017 mongo:latest
```

## 2. Backend Setup (first time only)

> **Already done:** A venv named `venv` already exists at `backend-python/venv` with all dependencies installed (Python 3.13). Skip to Step 3 if it's already set up.

```powershell
cd backend-python
python -m venv venv
.\venv\Scripts\pip.exe install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt
```

> **Note (Python 3.13):** If `pydantic-core` fails to build (requires Rust), install with relaxed versions instead:
> ```powershell
> .\venv\Scripts\pip.exe install "fastapi>=0.100" "uvicorn[standard]>=0.25" python-multipart motor pymongo "pydantic>=2.5" pydantic-settings python-dotenv aiofiles "python-jose[cryptography]" python-dateutil email-validator chardet pathspec "passlib[bcrypt]" bcrypt==4.0.1 "PyYAML>=6.0" requests python-magic-bin torch transformers numpy scikit-learn sentencepiece tokenizers
> ```

## 3. Start Backend

// turbo
```powershell
cd backend-python
$env:PYTHONUTF8=1; .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at: **http://localhost:8000**
API docs at: **http://localhost:8000/docs**

## 4. Frontend Setup (first time only)

```powershell
cd devops-autopilot-frontend
npm install
```

## 5. Start Frontend

// turbo
```powershell
cd devops-autopilot-frontend
npm run dev
```

Frontend will be available at: **http://localhost:5173**

## 6. (Optional) Start Ollama

Make sure Ollama is running with the Llama 3.1 model for AI Docker/Terraform generation:

```powershell
ollama serve
ollama pull llama3.1
```

## URLs Summary

| Service         | URL                        |
|-----------------|----------------------------|
| Frontend        | http://localhost:5173       |
| Backend API     | http://localhost:8000       |
| Swagger Docs    | http://localhost:8000/docs  |
| Health Check    | http://localhost:8000/health|
| MongoDB         | localhost:27017             |
| Ollama          | http://localhost:11434      |
