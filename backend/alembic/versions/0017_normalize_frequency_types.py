"""Convert frequency enum columns to VARCHAR and remap to 5 allowed types

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-07

Root cause of previous attempts: env.py wraps ALL pending migrations in a
single context.begin_transaction(), so ALTER TYPE ADD VALUE and the UPDATE
that uses the new value always ended up in the same transaction — PostgreSQL
forbids that (UnsafeNewEnumValueUsageError).

Fix: convert jobs.frequency_type and jobs.initial_frequency_type from the
native PostgreSQL enum type to VARCHAR(30). This is already what the
SQLAlchemy model expects (native_enum=False, create_constraint=False), so no
application-layer changes are needed. The conversion and all remapping UPDATEs
run cleanly in a single transaction — no ALTER TYPE ADD VALUE required.

Remapping:
  biweekly    -> weekly   (every N weeks,  frequency value unchanged)
  quarterly   -> monthly  (every 3 months, frequency value unchanged)
  half_yearly -> monthly  (every 6 months, frequency value unchanged)
  biannual    -> yearly   (every 2 years,  frequency value unchanged)
  running_hours -> hourly
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

REMAP = [
    ("biweekly", "weekly"),
    ("quarterly", "monthly"),
    ("half_yearly", "monthly"),
    ("biannual", "yearly"),
    ("running_hours", "hourly"),
]


def upgrade() -> None:
    # Convert the two native-enum columns on jobs to plain VARCHAR.
    # The SQLAlchemy model already declares them with native_enum=False, so
    # this brings the DB schema into alignment with the ORM definition.
    op.execute(sa.text(
        "ALTER TABLE jobs "
        "ALTER COLUMN frequency_type TYPE VARCHAR(30) USING frequency_type::text"
    ))
    op.execute(sa.text(
        "ALTER TABLE jobs "
        "ALTER COLUMN initial_frequency_type TYPE VARCHAR(30) USING initial_frequency_type::text"
    ))

    # Remap legacy values to the 5 allowed types.
    # standard_jobs.frequency_type is already VARCHAR(30) — no ALTER needed.
    for old, new in REMAP:
        op.execute(sa.text(
            f"UPDATE jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"
        ))
        op.execute(sa.text(
            f"UPDATE jobs SET initial_frequency_type = '{new}' WHERE initial_frequency_type = '{old}'"
        ))
        op.execute(sa.text(
            f"UPDATE standard_jobs SET frequency_type = '{new}' WHERE frequency_type = '{old}'"
        ))


def downgrade() -> None:
    # Reverse the value remapping (restoring the native enum type is not
    # implemented as PostgreSQL makes that highly non-trivial).
    for old, new in REMAP:
        op.execute(sa.text(
            f"UPDATE jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"
        ))
        op.execute(sa.text(
            f"UPDATE jobs SET initial_frequency_type = '{old}' WHERE initial_frequency_type = '{new}'"
        ))
        op.execute(sa.text(
            f"UPDATE standard_jobs SET frequency_type = '{old}' WHERE frequency_type = '{new}'"
        ))
