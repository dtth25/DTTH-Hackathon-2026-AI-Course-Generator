"""add shared provider ledger and Book budget

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("processing_jobs", sa.Column("product_stage", sa.String(32), nullable=True))
    op.create_table(
        "book_budgets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id")),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id")),
        sa.Column("version_id", sa.String()),
        sa.Column("ceiling", sa.BigInteger(), nullable=False),
        sa.Column("spent", sa.BigInteger(), nullable=False),
        sa.Column("reserved", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("incident_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("course_id", "version_id"),
        sa.CheckConstraint("ceiling >= 0 AND spent >= 0 AND reserved >= 0"),
    )
    op.create_table(
        "provider_calls",
        sa.Column("call_id", sa.String(), primary_key=True),
        sa.Column("budget_id", sa.String(), sa.ForeignKey("book_budgets.id")),
        sa.Column("job_id", sa.String(), sa.ForeignKey("processing_jobs.id")),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id")),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id")),
        sa.Column("job_attempt", sa.Integer()),
        sa.Column("provider_attempt", sa.Integer(), nullable=False),
        sa.Column("feature", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("model", sa.String(160)),
        sa.Column("bound_metadata", sa.JSON()),
        sa.Column("response_id", sa.String(200), unique=True),
        sa.Column("reserved", sa.BigInteger(), nullable=False),
        sa.Column("cost", sa.BigInteger()),
        sa.Column("original_cost", sa.String(100)),
        sa.Column("input_tokens", sa.BigInteger()),
        sa.Column("output_tokens", sa.BigInteger()),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32)),
        sa.Column("elapsed_ms", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.CheckConstraint("reserved >= 0 AND (cost IS NULL OR cost >= 0)"),
    )
    op.create_table(
        "provider_test_budgets",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("ceiling", sa.BigInteger(), nullable=False),
        sa.Column("spent", sa.BigInteger(), nullable=False),
        sa.Column("reserved", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.CheckConstraint("ceiling >= 0 AND spent >= 0 AND reserved >= 0"),
    )
    op.create_table(
        "provider_stages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("processing_jobs.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("chapter", sa.Integer()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("elapsed_ms", sa.BigInteger()),
    )
    for table, columns in {
        "book_budgets": ["course_id", "user_id"],
        "provider_calls": ["budget_id", "job_id", "user_id", "course_id"],
        "provider_stages": ["job_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("provider_stages", "provider_test_budgets", "provider_calls", "book_budgets"):
        op.drop_table(table)
    op.drop_column("processing_jobs", "product_stage")
