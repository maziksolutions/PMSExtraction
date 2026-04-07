"""Normalize frequency types to daily/weekly/monthly/yearly/hourly only

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-07
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Mapping: old value -> new value
FREQUENCY_REMAP = {
    "biweekly": "weekly",       # every 2 weeks → weekly
    "quarterly": "monthly",     # every 3 months → monthly (frequency stays as 3)
    "half_yearly": "monthly",   # every 6 months → monthly (frequency stays as 6)
    "biannual": "yearly",       # every 2 years → yearly (frequency stays as 2)
    "running_hours": "hourly",  # running hours → hourly
}


def upgrade() -> None:
    # Add 'hourly' to both native enum types
    op.execute("ALTER TYPE frequency_type ADD VALUE IF NOT EXISTS 'hourly'")
    op.execute("ALTER TYPE initial_frequency_type ADD VALUE IF NOT EXISTS 'hourly'")

    # Normalize jobs.frequency_type
    for old, new in FREQUENCY_REMAP.items():
        op.execute(
            f"UPDATE jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"
        )

    # Normalize jobs.initial_frequency_type
    for old, new in FREQUENCY_REMAP.items():
        op.execute(
            f"UPDATE jobs SET initial_frequency_type = '{new}' WHERE initial_frequency_type = '{old}'"
        )

    # Normalize standard_jobs.frequency_type (stored as VARCHAR)
    for old, new in FREQUENCY_REMAP.items():
        op.execute(
            f"UPDATE standard_jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"
        )


def downgrade() -> None:
    # PostgreSQL cannot remove enum values — no-op for enum changes
    # Reverse the data updates
    REVERSE = {v: k for k, v in FREQUENCY_REMAP.items()}
    for new, old in REVERSE.items():
        op.execute(
            f"UPDATE jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"
        )
        op.execute(
            f"UPDATE jobs SET initial_frequency_type = '{old}' WHERE initial_frequency_type = '{new}'"
        )
        op.execute(
            f"UPDATE standard_jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"
        )
