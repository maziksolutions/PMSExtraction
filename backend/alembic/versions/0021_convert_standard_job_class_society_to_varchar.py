"""Reserved migration slot after class society enum fix

Revision ID: 0021_convert_standard_job_class_society_to_varchar
Revises: 0020_add_kr_irs_class_society
Create Date: 2026-04-17 18:40:00
"""

revision = "0021_convert_standard_job_class_society_to_varchar"
down_revision = "0020_add_kr_irs_class_society"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally left as a no-op.
    #
    # We now extend the existing PostgreSQL enum in migration 0020 using
    # autocommit_block(), which is much faster and safer for startup-time
    # deploys than altering the column type for the whole table.
    pass


def downgrade() -> None:
    pass
