from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config.database import db
from .config.settings import settings
from .middleware.error_handler import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .routes import analyze, auth, aws_deploy, deploy, docker_ai, extract, monitor, upload

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect_db()
    print("Application started")
    yield
    await db.close_db()
    print("Application shutdown")


app = FastAPI(
    title="DevOps AutoPilot API",
    description="Automated DevOps Pipeline Generator - Module 1",
    version="1.0.0",
    lifespan=lifespan,
)

# In development, allow all localhost origins
if settings.ENVIRONMENT == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://localhost:\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Include Routers
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(extract.router)
app.include_router(analyze.router)
app.include_router(deploy.router)
app.include_router(docker_ai.router)
app.include_router(aws_deploy.router)
app.include_router(monitor.router)

@app.get("/")
async def root():
    return {
        "message": "DevOps AutoPilot API - Module 1",
        "status": "running",
        "version": "1.0.0",
        "modules": {
            "chunk1": "Upload & Storage",
            "chunk2": "ZIP Extraction",
            "chunk3": "Framework Detection",
            "chunk4": "Metadata Storage",
            "chunk5": "Authentication",
        },
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
