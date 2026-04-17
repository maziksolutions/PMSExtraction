"""Reserved migration slot after class society enum extension attempt

Revision ID: 0020_add_kr_irs_class_society
Revises: 0019_add_job_ranks_and_standard_job_ranks
Create Date: 2026-04-17 18:10:00
"""

# revision identifiers, used by Alembic.
revision = "0020_add_kr_irs_class_society"
down_revision = "0019_add_job_ranks_and_standard_job_ranks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally a no-op.
    #
    # Root cause:
    # PostgreSQL enum ADD VALUE is brittle under transactional migration flows.
    # The durable fix is implemented in the next migration, which converts
    # standard_jobs.class_society to VARCHAR so new class societies do not
    # require future enum alterations.
    pass


def downgrade() -> None:
    pass
