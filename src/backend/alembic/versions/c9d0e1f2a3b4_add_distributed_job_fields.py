"""add distributed processing job fields

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch_op:
        batch_op.add_column(sa.Column("payload_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("active_key", sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column("queue_name", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
        )
        batch_op.add_column(sa.Column("worker_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "cancel_requested",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    jobs = sa.table(
        "processing_jobs",
        sa.column("id", sa.String()),
        sa.column("status", sa.String(length=32)),
        sa.column("payload_json", sa.JSON()),
        sa.column("active_key", sa.String(length=180)),
        sa.column("queue_name", sa.String(length=32)),
    )
    # A SQL literal keeps the backfill portable in online migrations and in
    # Alembic's ``--sql`` mode, where JSON bind values cannot be rendered.
    op.execute(
        jobs.update().values(
            payload_json=sa.literal_column("'{}'"), queue_name="ingestion"
        )
    )
    op.execute(
        jobs.update()
        .where(jobs.c.status.in_(["queued", "retry_scheduled", "running"]))
        .values(active_key=sa.literal("legacy:") + jobs.c.id)
    )

    with op.batch_alter_table("processing_jobs") as batch_op:
        batch_op.alter_column(
            "payload_json", existing_type=sa.JSON(), nullable=False
        )
        batch_op.alter_column(
            "queue_name", existing_type=sa.String(length=32), nullable=False
        )

    op.create_index(
        "ix_processing_jobs_active_key",
        "processing_jobs",
        ["active_key"],
        unique=True,
    )
    op.create_index(
        "ix_processing_jobs_lease_expires_at",
        "processing_jobs",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_processing_jobs_next_attempt_at",
        "processing_jobs",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_next_attempt_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_lease_expires_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_active_key", table_name="processing_jobs")
    with op.batch_alter_table("processing_jobs") as batch_op:
        batch_op.drop_column("cancel_requested")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("worker_id")
        batch_op.drop_column("max_attempts")
        batch_op.drop_column("attempts")
        batch_op.drop_column("queue_name")
        batch_op.drop_column("active_key")
        batch_op.drop_column("payload_json")
