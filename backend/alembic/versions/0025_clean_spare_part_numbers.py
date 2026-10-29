"""clean leaked pdf filenames from spare part_number (Bug-002)

Revision ID: 0025_clean_spare_part_numbers
Revises: 2c31f19ace76
Create Date: 2026-10-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0025_clean_spare_part_numbers'
down_revision = '2c31f19ace76'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clean up legacy spares where part_number was filled with PDF filename or source reference
    op.execute("""
        UPDATE spares
        SET part_number = NULL
        WHERE part_number ILIKE '%.pdf%' OR part_number ILIKE '% (p.%'
    """)


def downgrade() -> None:
    pass
