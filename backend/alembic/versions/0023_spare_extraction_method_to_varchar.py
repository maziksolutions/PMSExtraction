"""Convert spares.extraction_method from native PG enum to VARCHAR

The SQLAlchemy model uses native_enum=False (VARCHAR storage) but the initial
migration created the column as a native PostgreSQL enum type. This mismatch
meant adding new enum values (e.g. 'manual') required ALTER TYPE ... ADD VALUE
which cannot run inside a transaction and is prone to deployment race conditions.

Converting to VARCHAR aligns the DB column with the ORM model and allows any
string value from the Python enum without further DDL changes.

Revision ID: 0023_spare_extraction_method_to_varchar
Revises: 0022_add_manual_extraction_method
Create Date: 2026-05-08 12:00:00
"""

from alembic import op

revision = "0023_spare_extraction_method_to_varchar"
down_revision = "0022_add_manual_extraction_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE spares "
        "ALTER COLUMN extraction_method TYPE VARCHAR(50) "
        "USING extraction_method::text"
    )


def downgrade() -> None:
    pass
