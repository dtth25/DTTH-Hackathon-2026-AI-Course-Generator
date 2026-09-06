"""add extraction coverage aggregate

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courses", sa.Column("extraction_coverage_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("courses", "extraction_coverage_json")
