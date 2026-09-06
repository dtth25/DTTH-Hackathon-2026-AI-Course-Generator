"""Models package."""
from app.models.user import User
from app.models.course import Course
from app.models.email_otp import EmailOtpCode
from app.models.generation_job import (
    ArtifactType,
    GenerationJob,
    JobQueue,
    JobState,
)

__all__ = [
    "User",
    "Course",
    "EmailOtpCode",
    "ArtifactType",
    "GenerationJob",
    "JobQueue",
    "JobState",
]
