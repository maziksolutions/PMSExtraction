"""Add supply_type column to manuals table

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manuals",
        sa.Column("supply_type", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("manuals", "supply_type")
