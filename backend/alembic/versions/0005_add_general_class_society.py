"""add General to class_society enum

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-28
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL allows adding new values to an enum with ADD VALUE
    op.execute("ALTER TYPE class_society ADD VALUE IF NOT EXISTS 'General'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum without recreating it
    pass
