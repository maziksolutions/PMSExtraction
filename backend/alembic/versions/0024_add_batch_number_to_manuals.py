"""Add batch_number to manuals

Revision ID: 0024_add_batch_number_to_manuals
Revises: 0023_spare_extraction_varchar
Create Date: 2026-07-31 16:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_add_batch_number_to_manuals"
down_revision = "0023_spare_extraction_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuals", sa.Column("batch_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("manuals", "batch_number")
