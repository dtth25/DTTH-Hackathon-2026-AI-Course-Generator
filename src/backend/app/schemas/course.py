"""Pydantic schemas for Course models and Upload service."""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_serializer


class CourseCreate(BaseModel):
    filenames: Optional[List[str]] = None
    metadata_json: Optional[str] = None


class CourseResponse(BaseModel):
    id: str
    user_id: str
    name: Optional[str] = None
    filenames: Optional[List[str]] = None
    status: str
    stage: str
    progress: int
    chunk_count: int = 0
    embedding_status: str = "pending"
    quality_score: int = 0
    quality_score_label: str = "structural/coverage checks compatibility"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CourseListItem(BaseModel):
    course_id: str
    name: Optional[str] = None
    status: str
    filenames: List[str] = []
    file_count: int = 0
    created_at: Optional[datetime] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class CourseListResponse(BaseModel):
    courses: List[CourseListItem]
    total: int


class CourseStatusResponse(BaseModel):
    course_id: str
    name: Optional[str] = None
    status: str
    stage: str = "completed"
    progress: int = 100
    chunk_count: int = 0
    embedding_status: str = "pending"
    quality_score: int = 0
    quality_score_label: str = "structural/coverage checks compatibility"
    message: str = "Tài liệu đã sẵn sàng."
    filenames: List[str] = []
    file_count: int = 0
    error: Optional[str] = None
    error_code: Optional[str] = None
    failure_stage: Optional[str] = None
    can_retry: bool = False
    recommended_action: Optional[str] = None
    job_id: Optional[str] = None
    document_quality_report: Optional[Dict[str, Any]] = None


class CourseRenameRequest(BaseModel):
    name: str


class UploadResponse(BaseModel):
    course_id: str
    document_id: str
    filenames: List[str] = []
    file_count: int = 0
    status: str
    message: str
    job_id: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    document_id: str
    user_id: Optional[str] = None
    job_type: str
    status: str
    queue_position: Optional[int] = None
    progress: int
    message: str
    error: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    stage: str

    @field_serializer("next_attempt_at", "created_at", "updated_at", "completed_at")
    def serialize_utc_datetime(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class DocumentRetryResponse(BaseModel):
    document_id: str
    status: str
    stage: str
    progress: int
    message: str
    job_id: str
