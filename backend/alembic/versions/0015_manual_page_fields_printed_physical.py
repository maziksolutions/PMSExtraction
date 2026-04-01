"""add printed and physical page fields to manuals

Revision ID: 0015
Revises: 0014_add_supply_type_to_manuals.py
Create Date: 2026-04-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuals", sa.Column("pages_with_components_printed", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("pages_with_jobs_printed", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("pages_with_spares_printed", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("pages_with_components_physical", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("pages_with_jobs_physical", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("pages_with_spares_physical", sa.Text(), nullable=True))
    op.add_column("manuals", sa.Column("page_explanations", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("manuals", "page_explanations")
    op.drop_column("manuals", "pages_with_spares_physical")
    op.drop_column("manuals", "pages_with_jobs_physical")
    op.drop_column("manuals", "pages_with_components_physical")
    op.drop_column("manuals", "pages_with_spares_printed")
    op.drop_column("manuals", "pages_with_jobs_printed")
    op.drop_column("manuals", "pages_with_components_printed")
