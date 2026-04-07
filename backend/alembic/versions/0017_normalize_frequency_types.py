"""Add hourly enum value to frequency types

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-07

NOTE: ALTER TYPE ADD VALUE cannot be used inside the same transaction as DML
that references the new value. We commit Alembic's open transaction first,
run the DDL (which auto-commits as standalone DDL), then start a new transaction
so Alembic can record the revision. The UPDATE remapping is in migration 0018.
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Commit the transaction Alembic opened so ALTER TYPE ADD VALUE can commit
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE frequency_type ADD VALUE IF NOT EXISTS 'hourly'"))
    conn.execute(sa.text("ALTER TYPE initial_frequency_type ADD VALUE IF NOT EXISTS 'hourly'"))
    # Re-open a transaction so Alembic can write the version stamp
    conn.execute(sa.text("BEGIN"))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — no-op
    pass
