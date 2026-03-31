"""Add location and machinery_particulars to components

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-31
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE components
        ADD COLUMN IF NOT EXISTS location VARCHAR(300),
        ADD COLUMN IF NOT EXISTS machinery_particulars TEXT
    """)


def downgrade() -> None:
    pass
