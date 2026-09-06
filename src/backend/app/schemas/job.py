"""Owner-safe API schemas for durable background jobs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobSummary(BaseModel):
    """Lifecycle fields safe to expose to the job owner."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str
    state: str
    stage: str
    progress: int = Field(ge=0, le=100)
    queue_position: int = Field(ge=0)
    attempt: int = Field(ge=0)
    can_cancel: bool
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
