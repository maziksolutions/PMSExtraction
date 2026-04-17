"""Add KR and IRS to class_society enum

Revision ID: 0020_add_kr_irs_class_society
Revises: 0019_job_ranks
Create Date: 2026-04-17 18:10:00
"""

# revision identifiers, used by Alembic.
revision = "0020_add_kr_irs_class_society"
down_revision = "0019_job_ranks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum mutations need to run outside Alembic's surrounding
    # transaction block. autocommit_block() keeps this migration fast and
    # avoids rewriting the standard_jobs table during application startup.
    context = op.get_context()
    with context.autocommit_block():
        op.execute("ALTER TYPE class_society ADD VALUE IF NOT EXISTS 'KR'")
        op.execute("ALTER TYPE class_society ADD VALUE IF NOT EXISTS 'IRS'")


def downgrade() -> None:
    pass
