from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class LogEntry(BaseModel):
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)


# Add this to Metadata class:

class Metadata(BaseModel):
    framework: str = "Unknown"
    language: str = "Unknown"
    runtime: Optional[str] = None
    dependencies: List[str] = []
    port: Optional[int] = None
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    env_variables: List[str] = []
    dockerfile: bool = False
    docker_compose: bool = False
    detected_files: List[str] = []
    
    # NEW ML fields
    ml_confidence: Optional[Dict[str, float]] = None  # {"language": 0.95, "framework": 0.87}
    detection_method: Optional[str] = None  # "ML (CodeBERT)", "Config-based", "Signature-based"


class ProjectModel(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_name: str
    file_name: str
    file_path: str
    file_size: int
    upload_date: datetime = Field(default_factory=datetime.now)
    extracted_path: Optional[str] = None
    extraction_date: Optional[datetime] = None
    files_count: int = 0
    folders_count: int = 0
    extraction_logs: List[str] = []
    metadata: Metadata = Field(default_factory=Metadata)
    analysis_date: Optional[datetime] = None
    analysis_logs: List[str] = []
    status: str = "uploaded"
    logs: List[LogEntry] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Deployment fields (K8s)
    deployment_status: Optional[str] = None  # not_deployed, deploying, deployed, failed
    deployment: Optional[Dict] = None  # K8s deployment info
    
    # Docker push status
    docker_push_success: bool = False  # True after successful image push
    
    # AWS Deployment fields
    aws_deployment_status: str = "not_deployed"  # not_deployed, terraform_generated, deploying, deployed, failed, scaled_to_zero
    aws_region: Optional[str] = None
    aws_frontend_url: Optional[str] = None  # ALB URL
    aws_ecs_cluster_id: Optional[str] = None
    aws_last_deployed: Optional[datetime] = None
    aws_terraform_path: Optional[str] = None  # Path to generated main.tf
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }