"""SQLAlchemy Course model."""

import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from app.services.database import Base


def generate_uuid_12() -> str:
    """Generate a 12-character hex string ID."""
    return uuid.uuid4().hex[:12]


class Course(Base):
    __tablename__ = "courses"

    id = Column(String, primary_key=True, default=generate_uuid_12, index=True)
    # ondelete="CASCADE" is metadata only — SQLite doesn't enforce it without
    # PRAGMA foreign_keys=ON (not set anywhere in database.py), so deleting a User
    # does NOT delete their courses at the DB level. Cascade cleanup for this table
    # is done by hand in app/routers/auth.py::delete_account. If you add a new table
    # with a FK to courses.id/users.id, you must add its own manual cleanup too.
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filenames = Column(JSON, nullable=True)  # List of uploaded filenames
    name = Column(String, nullable=True)  # AI-generated (or user-renamed) short course title
    status = Column(String, default="processing", nullable=False)
    stage = Column(String, default="extracting", nullable=False)
    progress = Column(Integer, default=30, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON encoded metadata
    extraction_coverage_json = Column(Text, nullable=True)  # Versioned safe aggregate; NULL means legacy/unknown
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    chunk_count = Column(Integer, default=0, nullable=False)
    embedding_status = Column(String, default="pending", nullable=False)
    quality_score = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)  # Real reason processing failed, shown to the user
    failure_stage = Column(String(50), nullable=True)
    error_code = Column(String(80), nullable=True)
    can_retry = Column(Boolean, default=False, nullable=False)
    recommended_action = Column(String(80), nullable=True)
    # Server-only diagnostic detail. It must never be included in a public response schema.
    technical_error = Column(Text, nullable=True)
    # "gemini" remains only as a legacy marker. New and migrated courses use OpenRouter.
    embedding_provider = Column(String, default="openrouter", nullable=False)
