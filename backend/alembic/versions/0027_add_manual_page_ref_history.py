"""Add manual_page_ref_history and extraction tracking tables

Revision ID: 0027_add_manual_page_ref_history
Revises: 0026_clean_spares_part_num
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0027_add_manual_page_ref_history'
down_revision = '0026_clean_spares_part_num'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        uuid_default = "gen_random_uuid()"
    else:
        uuid_default = "(lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-a' || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6))))"

    if is_postgres:
        # 1. manual_page_ref_history table
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS manual_page_ref_history (
                id UUID PRIMARY KEY DEFAULT {uuid_default},
                tenant_id UUID NOT NULL,
                vessel_id UUID NOT NULL REFERENCES vessel_projects(id) ON DELETE CASCADE,
                manual_id UUID NOT NULL REFERENCES manuals(id) ON DELETE CASCADE,
                changed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                changed_by_name VARCHAR(255),
                change_source VARCHAR(100) NOT NULL DEFAULT 'user_edit',
                pages_with_components TEXT,
                pages_with_jobs TEXT,
                pages_with_spares TEXT,
                pages_with_components_physical TEXT,
                pages_with_jobs_physical TEXT,
                pages_with_spares_physical TEXT,
                previous_pages_with_components TEXT,
                previous_pages_with_jobs TEXT,
                previous_pages_with_spares TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        op.execute("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_manual ON manual_page_ref_history(manual_id);")
        op.execute("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_vessel ON manual_page_ref_history(vessel_id);")
        op.execute("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_created ON manual_page_ref_history(created_at DESC);")

        # 2. manual_extraction_runs table (align with extraction_counter.py schema)
        op.execute("""
            CREATE TABLE IF NOT EXISTS manual_extraction_runs (
                manual_id UUID PRIMARY KEY,
                run_count INTEGER NOT NULL DEFAULT 1,
                last_run_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # 3. manual_page_extractions table (align with extraction_counter.py schema)
        op.execute("""
            CREATE TABLE IF NOT EXISTS manual_page_extractions (
                manual_id UUID NOT NULL,
                page_number INTEGER NOT NULL,
                run_count INTEGER NOT NULL DEFAULT 1,
                last_extracted_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (manual_id, page_number)
            );
        """)
        op.execute("CREATE INDEX IF NOT EXISTS idx_manual_page_extractions_manual ON manual_page_extractions(manual_id);")

        # 4. Seed baseline snapshots for manuals with page references if missing
        op.execute(f"""
            INSERT INTO manual_page_ref_history (
                id, tenant_id, vessel_id, manual_id, change_source, changed_by_name,
                pages_with_components, pages_with_jobs, pages_with_spares,
                pages_with_components_physical, pages_with_jobs_physical, pages_with_spares_physical,
                notes, created_at, updated_at
            )
            SELECT 
                {uuid_default}, m.tenant_id, m.vessel_id, m.id, 'baseline', 'Initial Saved Reference',
                m.pages_with_components, m.pages_with_jobs, m.pages_with_spares,
                m.pages_with_components_physical, m.pages_with_jobs_physical, m.pages_with_spares_physical,
                'Baseline page references snapshot', m.updated_at, m.updated_at
            FROM manuals m
            WHERE (
                (m.pages_with_components IS NOT NULL AND m.pages_with_components != '') OR
                (m.pages_with_jobs IS NOT NULL AND m.pages_with_jobs != '') OR
                (m.pages_with_spares IS NOT NULL AND m.pages_with_spares != '') OR
                (m.pages_with_components_physical IS NOT NULL AND m.pages_with_components_physical != '') OR
                (m.pages_with_jobs_physical IS NOT NULL AND m.pages_with_jobs_physical != '') OR
                (m.pages_with_spares_physical IS NOT NULL AND m.pages_with_spares_physical != '')
            )
            AND NOT EXISTS (
                SELECT 1 FROM manual_page_ref_history h WHERE h.manual_id = m.id
            );
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS manual_page_ref_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS manual_page_extractions CASCADE;")
    op.execute("DROP TABLE IF EXISTS manual_extraction_runs CASCADE;")
