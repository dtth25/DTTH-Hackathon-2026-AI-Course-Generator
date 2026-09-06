"""persist immutable balanced Book policy and allocation identity

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""

from alembic import op
import sqlalchemy as sa


revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


_DEFAULT_POLICY = {
    "model": "google/gemini-2.5-flash",
    "input_price_ceiling": "0.30",
    "output_price_ceiling": "2.50",
    "reasoning_budget": 512,
    "revision": "balanced-book-v1",
    "require_parameters": True,
    "provider_sort": "throughput",
    "structured_output": "json_schema",
    "output_cap_parameter": "max_tokens",
}


def upgrade():
    op.add_column("book_budgets", sa.Column("model_policy", sa.JSON(), nullable=True))
    op.add_column("book_budgets", sa.Column("allocation_digest", sa.String(64), nullable=True))
    budgets = sa.table("book_budgets", sa.column("model_policy", sa.JSON()))
    op.execute(budgets.update().values(model_policy=_DEFAULT_POLICY))
    op.alter_column("book_budgets", "model_policy", nullable=False)


def downgrade():
    op.drop_column("book_budgets", "allocation_digest")
    op.drop_column("book_budgets", "model_policy")
