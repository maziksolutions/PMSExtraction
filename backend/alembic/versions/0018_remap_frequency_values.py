"""Remap legacy frequency values to the 5 allowed types

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-07

Depends on 0017 having committed 'hourly' into the enum before this runs.
Mapping:
  biweekly    -> weekly   (every 2 weeks, frequency value unchanged)
  quarterly   -> monthly  (every 3 months, frequency value unchanged)
  half_yearly -> monthly  (every 6 months, frequency value unchanged)
  biannual    -> yearly   (every 2 years,  frequency value unchanged)
  running_hours -> hourly
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

REMAP = {
    "biweekly": "weekly",
    "quarterly": "monthly",
    "half_yearly": "monthly",
    "biannual": "yearly",
    "running_hours": "hourly",
}


def upgrade() -> None:
    for old, new in REMAP.items():
        op.execute(sa.text(f"UPDATE jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"))
        op.execute(sa.text(f"UPDATE jobs SET initial_frequency_type = '{new}' WHERE initial_frequency_type = '{old}'"))
        op.execute(sa.text(f"UPDATE standard_jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"))


def downgrade() -> None:
    # Reverse the data updates (enum values can't be removed from PostgreSQL)
    for old, new in REMAP.items():
        op.execute(sa.text(f"UPDATE jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"))
        op.execute(sa.text(f"UPDATE jobs SET initial_frequency_type = '{old}' WHERE initial_frequency_type = '{new}'"))
        op.execute(sa.text(f"UPDATE standard_jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"))
