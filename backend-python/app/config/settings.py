from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "devops_autopilot"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    UPLOAD_DIR: str = "./uploads"
    EXTRACTED_DIR: str = "./extracted"
    MAX_FILE_SIZE: int = 104857600
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:4321",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4321",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080"
    ]
    ENVIRONMENT: str = "development"
    
    # Docker Hub Credentials - loaded from environment or .env
    # Set `DOCKER_HUB_USERNAME` and `DOCKER_HUB_PASSWORD` in your environment
    DOCKER_HUB_USERNAME: Optional[str] = None
    DOCKER_HUB_PASSWORD: Optional[str] = None
    
    # Kubernetes Config
    K8S_NAMESPACE: str = "default"
    K8S_CLUSTER: str = "docker-desktop"
    
    # Deployment Config
    APP_REGISTRY_PREFIX: str = "devops-autopilot"
    K8S_NODE_PORT_START: int = 30001
    K8S_NODE_PORT_END: int = 32767
    
    # LLM Configuration
    OLLAMA_URL: str = "http://localhost:11434/api/generate"
    LLM_MODEL_NAME: str = "llama3.1:7b"
    LLM_TEMPERATURE: float = 0.1
    LLM_TOP_P: float = 0.9
    LLM_TIMEOUT: int = 600
    
    # AWS Deployment Configuration
    AWS_PROFILE: Optional[str] = None  # AWS CLI profile name (e.g., "my-terraform")
    AWS_DEFAULT_REGION: str = "us-east-1"
    TERRAFORM_PATH: str = "terraform"  # Path to terraform CLI binary
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.EXTRACTED_DIR, exist_ok=True)

print(f"Settings loaded: {settings.ENVIRONMENT} mode")
print(f"Upload directory: {settings.UPLOAD_DIR}")
print(f"Extracted directory: {settings.EXTRACTED_DIR}")

# Inform about Docker Hub credential presence without printing sensitive values
if settings.DOCKER_HUB_USERNAME and settings.DOCKER_HUB_PASSWORD:
    print("Docker Hub credentials loaded from environment")
else:
    print("Warning: Docker Hub credentials not set in environment (.env or OS vars)")
