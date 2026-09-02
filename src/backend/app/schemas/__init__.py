"""Schemas package."""
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse
from app.schemas.course import (
    CourseCreate,
    CourseResponse,
    CourseListItem,
    CourseListResponse,
    CourseStatusResponse,
    DocumentRetryResponse,
    JobResponse,
    UploadResponse,
)
from app.schemas.generation import (
    GenerateRequest,
    GenerateResponse,
    StudyPackResponse,
    StudyPackData,
    StudyPackStats,
)

__all__ = [
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "TokenResponse",
    "CourseCreate",
    "CourseResponse",
    "CourseListItem",
    "CourseListResponse",
    "CourseStatusResponse",
    "DocumentRetryResponse",
    "JobResponse",
    "UploadResponse",
    "GenerateRequest",
    "GenerateResponse",
    "StudyPackResponse",
    "StudyPackData",
    "StudyPackStats",
]
