"""add private source plan history

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_revision", sa.String(length=100), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "revision", name="uq_source_plan_revision"),
        sa.UniqueConstraint(
            "course_id", "source_digest", "model", "prompt_revision",
            name="uq_source_plan_provenance",
        ),
    )
    op.create_index("ix_source_plans_course_id", "source_plans", ["course_id"])
    op.create_index("ix_source_plans_owner_id", "source_plans", ["owner_id"])


def downgrade():
    op.drop_index("ix_source_plans_owner_id", table_name="source_plans")
    op.drop_index("ix_source_plans_course_id", table_name="source_plans")
    op.drop_table("source_plans")

