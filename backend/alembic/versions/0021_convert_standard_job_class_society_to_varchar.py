"""Convert standard_jobs.class_society from enum to VARCHAR

Revision ID: 0021_convert_standard_job_class_society_to_varchar
Revises: 0020_add_kr_irs_class_society
Create Date: 2026-04-17 18:40:00
"""

import sqlalchemy as sa
from alembic import op


revision = "0021_convert_standard_job_class_society_to_varchar"
down_revision = "0020_add_kr_irs_class_society"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE standard_jobs "
            "ALTER COLUMN class_society TYPE VARCHAR(50) USING class_society::text"
        )
    )


def downgrade() -> None:
    # Recreating the native enum and casting back is intentionally omitted.
    pass
