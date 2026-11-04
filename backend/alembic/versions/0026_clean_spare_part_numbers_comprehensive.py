"""comprehensive cleanup of leaked pdf filenames and document titles from spare part_number (Bug-002 Item 3)

Revision ID: 0026_clean_spare_part_numbers_comprehensive
Revises: 0025_clean_spare_part_numbers
Create Date: 2026-11-04
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0026_clean_spare_part_numbers_comprehensive'
down_revision = '0025_clean_spare_part_numbers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Clean up spares where part_number contains .pdf, page references, or placeholder terms
    op.execute("""
        UPDATE spares
        SET part_number = NULL
        WHERE part_number ILIKE '%.pdf%'
           OR part_number ILIKE '% (p.%'
           OR part_number ILIKE '%page %'
           OR LOWER(TRIM(part_number)) IN ('none', 'n/a', 'null', 'unknown', 'nil', '-', '--', 'na', 'not available', '/');
    """)

    # 2. Clean up spares where part_number matches the source manual filename or base name
    op.execute("""
        UPDATE spares s
        SET part_number = NULL
        FROM manuals m
        WHERE s.source_manual_id = m.id
          AND s.part_number IS NOT NULL
          AND (
            LOWER(TRIM(s.part_number)) = LOWER(TRIM(m.original_filename))
            OR LOWER(TRIM(s.part_number)) = LOWER(TRIM(REPLACE(m.original_filename, '.pdf', '')))
            OR LOWER(TRIM(s.part_number)) = LOWER(TRIM(REPLACE(m.original_filename, '.PDF', '')))
          );
    """)

    # 3. Clean up drawing_number if it leaked a .pdf filename or source reference
    op.execute("""
        UPDATE spares
        SET drawing_number = NULL
        WHERE drawing_number ILIKE '%.pdf%'
           OR drawing_number ILIKE '% (p.%';
    """)


def downgrade() -> None:
    pass
