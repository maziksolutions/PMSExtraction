"""add job_pages spare_pages pdf_reference to components

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("components", sa.Column("job_pages", sa.Text(), nullable=True))
    op.add_column("components", sa.Column("spare_pages", sa.Text(), nullable=True))
    op.add_column("components", sa.Column("pdf_reference", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("components", "pdf_reference")
    op.drop_column("components", "spare_pages")
    op.drop_column("components", "job_pages")
