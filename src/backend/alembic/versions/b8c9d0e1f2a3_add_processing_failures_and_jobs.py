"""add durable processing failures and jobs

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch_op:
        batch_op.add_column(sa.Column("failure_stage", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("error_code", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("can_retry", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("recommended_action", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(sa.Column("technical_error", sa.Text(), nullable=True))

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("external_task_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_jobs_course_id", "processing_jobs", ["course_id"])
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index(
        "ix_processing_jobs_external_task_id", "processing_jobs", ["external_task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_external_task_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_user_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_course_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")

    with op.batch_alter_table("courses") as batch_op:
        batch_op.drop_column("technical_error")
        batch_op.drop_column("recommended_action")
        batch_op.drop_column("can_retry")
        batch_op.drop_column("error_code")
        batch_op.drop_column("failure_stage")
