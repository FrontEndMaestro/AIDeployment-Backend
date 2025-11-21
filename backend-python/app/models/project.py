from datetime import datetime
from typing import Optional, List
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
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }