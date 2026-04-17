"""Add KR and IRS to class_society enum

Revision ID: 0020_add_kr_irs_class_society
Revises: 0019_add_job_ranks_and_standard_job_ranks
Create Date: 2026-04-17 18:10:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0020_add_kr_irs_class_society"
down_revision = "0019_add_job_ranks_and_standard_job_ranks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE class_society ADD VALUE IF NOT EXISTS 'KR'")
    op.execute("ALTER TYPE class_society ADD VALUE IF NOT EXISTS 'IRS'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # This migration is intentionally irreversible.
    pass
