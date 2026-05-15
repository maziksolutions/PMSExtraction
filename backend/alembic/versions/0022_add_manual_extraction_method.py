"""Add 'manual' value to extraction_method enum

Revision ID: 0022_manual_extraction_method
Revises: 0021_class_society_varchar
Create Date: 2026-05-08 00:00:00
"""

from alembic import op

revision = "0022_manual_extraction_method"
down_revision = "0021_class_society_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute("ALTER TYPE extraction_method ADD VALUE IF NOT EXISTS 'manual'")


def downgrade() -> None:
    pass
