"""add durable generation jobs

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-03 03:25:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_JOB_SQL = "state IN ('queued', 'running', 'retrying')"


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(length=16), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=True),
        sa.Column("queue_name", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=36), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False),
        sa.Column("last_dispatch_error", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "artifact_type IN ('ingestion', 'book', 'slides', 'quiz', 'vid')",
            name="ck_generation_jobs_artifact_type",
        ),
        sa.CheckConstraint(
            "queue_name IN ('ingestion', 'generation', 'video')",
            name="ck_generation_jobs_queue_name",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled')",
            name="ck_generation_jobs_state",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_generation_jobs_progress",
        ),
        sa.CheckConstraint("attempt >= 0", name="ck_generation_jobs_attempt"),
        sa.CheckConstraint("max_attempts > 0", name="ck_generation_jobs_max_attempts"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generation_jobs_course_id", "generation_jobs", ["course_id"]
    )
    op.create_index(
        "ix_generation_jobs_user_id", "generation_jobs", ["user_id"]
    )
    op.create_index(
        "ix_generation_jobs_artifact_type", "generation_jobs", ["artifact_type"]
    )
    op.create_index(
        "ix_generation_jobs_version_id", "generation_jobs", ["version_id"]
    )
    op.create_index(
        "ix_generation_jobs_queue_name", "generation_jobs", ["queue_name"]
    )
    op.create_index("ix_generation_jobs_state", "generation_jobs", ["state"])
    op.create_index(
        "ix_generation_jobs_celery_task_id",
        "generation_jobs",
        ["celery_task_id"],
        unique=True,
    )
    op.create_index(
        "ix_generation_jobs_queued_at", "generation_jobs", ["queued_at"]
    )
    op.create_index(
        "ix_generation_jobs_heartbeat_at", "generation_jobs", ["heartbeat_at"]
    )
    op.create_index(
        "uq_generation_jobs_active_course_artifact",
        "generation_jobs",
        ["course_id", "artifact_type"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_JOB_SQL),
        sqlite_where=sa.text(_ACTIVE_JOB_SQL),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_generation_jobs_active_course_artifact", table_name="generation_jobs"
    )
    op.drop_index("ix_generation_jobs_heartbeat_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_queued_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_celery_task_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_state", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_queue_name", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_version_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_artifact_type", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_user_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_course_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")
