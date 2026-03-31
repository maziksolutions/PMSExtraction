"""Add biweekly and biannual frequency types

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-31
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE frequency_type ADD VALUE IF NOT EXISTS 'biweekly'")
    op.execute("ALTER TYPE frequency_type ADD VALUE IF NOT EXISTS 'biannual'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — no-op
    pass
