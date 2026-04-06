"""add spare assembly fields

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spares", sa.Column("spare_assembly", sa.String(length=300), nullable=True))
    op.add_column("spares", sa.Column("assembly_description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("spares", "assembly_description")
    op.drop_column("spares", "spare_assembly")
