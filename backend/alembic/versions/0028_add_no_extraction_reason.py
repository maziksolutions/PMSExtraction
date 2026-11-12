"""Clean up and reconcile 0028 revision

Revision ID: 0028_add_no_extraction_reason
Revises: 0027_add_manual_page_ref_history
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0028_add_no_extraction_reason'
down_revision = '0027_add_manual_page_ref_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("""
            CREATE TABLE IF NOT EXISTS manual_extraction_runs (
                manual_id UUID PRIMARY KEY,
                run_count INTEGER NOT NULL DEFAULT 1,
                last_run_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        op.execute("""
            CREATE TABLE IF NOT EXISTS manual_page_extractions (
                manual_id UUID NOT NULL,
                page_number INTEGER NOT NULL,
                run_count INTEGER NOT NULL DEFAULT 1,
                last_extracted_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (manual_id, page_number)
            );
        """)
        # Safe idempotent column additions if table had older schema
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='manual_page_extractions' AND column_name='last_extracted_at'
                ) THEN
                    ALTER TABLE manual_page_extractions ADD COLUMN last_extracted_at TIMESTAMPTZ DEFAULT NOW();
                END IF;
            END $$;
        """)


def downgrade() -> None:
    pass
