"""Add hourly enum value to frequency types

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-07

NOTE: PostgreSQL requires ALTER TYPE ADD VALUE to be committed before the new
value can be used in DML. The actual UPDATE normalization is in migration 0018.
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These ALTER TYPE statements must be committed on their own before
    # 'hourly' can appear in any UPDATE (handled in migration 0018).
    bind = op.get_bind()
    bind.execution_options(isolation_level="AUTOCOMMIT").execute(
        sa.text("ALTER TYPE frequency_type ADD VALUE IF NOT EXISTS 'hourly'")
    )
    bind.execution_options(isolation_level="AUTOCOMMIT").execute(
        sa.text("ALTER TYPE initial_frequency_type ADD VALUE IF NOT EXISTS 'hourly'")
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — no-op
    pass
