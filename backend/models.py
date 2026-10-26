from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator


class StudentCreate(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=64, description="Unique stable student ID (e.g. STU001 or roll number)")
    name: str = Field(..., min_length=1, max_length=128, description="Student full name")
    roll_number: Optional[str] = Field(None, max_length=64, description="Student college roll number")
    email: Optional[str] = Field(None, max_length=128, description="Student email address")
    department: Optional[str] = Field(None, max_length=128, description="Student department or branch")

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("student_id cannot be blank")
        # Allow alphanumeric, dashes, underscores
        if not all(c.isalnum() or c in "-_" for c in clean):
            raise ValueError("student_id can only contain alphanumeric characters, underscores, and hyphens")
        return clean

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("name cannot be blank")
        return clean


class StudentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    roll_number: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=128)
    department: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None


class StudentResponse(BaseModel):
    student_id: str
    name: str
    roll_number: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    is_active: bool = True
    created_at: str
    embedding_count: int = 0


class EmbeddingCreate(BaseModel):
    student_id: str = Field(..., description="Student ID associated with this embedding")
    embedding: List[float] = Field(..., description="512-dimensional ArcFace embedding vector")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional quality scores or capture metadata")

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, v: List[float]) -> List[float]:
        if len(v) != 512:
            raise ValueError(f"ArcFace embedding must have exactly 512 dimensions, got {len(v)}")
        return v


class EmbeddingResponse(BaseModel):
    embedding_id: str
    student_id: str
    student_name: str
    dimension: int = 512
    created_at: str
    metadata: Optional[Dict[str, Any]] = None
    # Embedding vector is included when explicitly requested or during startup cache sync
    embedding: Optional[List[float]] = None


class AttendanceMarkRequest(BaseModel):
    student_id: str = Field(..., description="Recognized student ID")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score produced by ArcFace")
    session_id: Optional[str] = Field(None, description="Class or lecture session identifier")
    date: Optional[str] = Field(None, description="Optional explicit date in YYYY-MM-DD format (defaults to current UTC date)")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("date must be in YYYY-MM-DD format")
        return v


class AttendanceResponse(BaseModel):
    record_id: str
    student_id: str
    student_name: str
    date: str
    timestamp: str
    session_id: str
    similarity_score: float
    status: str
    already_recorded: bool = False
    message: str


class AttendanceQueryItem(BaseModel):
    record_id: str
    student_id: str
    student_name: str
    date: str
    timestamp: str
    session_id: str
    similarity_score: float
    status: str


class HealthResponse(BaseModel):
    status: str
    database_type: str
    database_connected: bool
    version: str = "1.0.0"
    enrolled_students: int = 0
    enrolled_embeddings: int = 0
