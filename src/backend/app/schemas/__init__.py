"""Schemas package."""
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse
from app.schemas.course import (
    CourseCreate,
    CourseResponse,
    CourseListItem,
    CourseListResponse,
    CourseStatusResponse,
    UploadResponse,
)
from app.schemas.generation import (
    GenerateRequest,
    GenerateResponse,
    StudyPackResponse,
    StudyPackData,
    StudyPackStats,
)
from app.schemas.job import JobSummary

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
    "UploadResponse",
    "GenerateRequest",
    "GenerateResponse",
    "StudyPackResponse",
    "StudyPackData",
    "StudyPackStats",
    "JobSummary",
]
