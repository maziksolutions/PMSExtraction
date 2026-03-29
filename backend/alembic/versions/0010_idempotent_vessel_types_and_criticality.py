"""idempotent fix: vessel_types table + criticality columns

Migration 0008 used op.create_unique_constraint with postgresql_where which
can fail on some Alembic/PG versions, leaving the table never created.
Migration 0009 similarly may have not run if 0008 was stuck.

This migration re-applies both with raw IF NOT EXISTS SQL so it is safe to
run even if the tables/columns already exist.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-29
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # vessel_types table (idempotent — 0008 may have failed)              #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS vessel_types (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL,
            name        VARCHAR(200) NOT NULL,
            is_system   BOOLEAN NOT NULL DEFAULT false,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            is_deleted  BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Partial unique index (CREATE UNIQUE INDEX supports WHERE; ALTER TABLE UNIQUE does not)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vessel_types_tenant_name
        ON vessel_types (tenant_id, name)
        WHERE is_deleted = false
    """)

    # vessel_type_id FK column on component_structure_library
    op.execute("""
        ALTER TABLE component_structure_library
        ADD COLUMN IF NOT EXISTS vessel_type_id UUID
    """)

    # FK constraint (skip if already exists)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_csl_vessel_type'
            ) THEN
                ALTER TABLE component_structure_library
                ADD CONSTRAINT fk_csl_vessel_type
                FOREIGN KEY (vessel_type_id) REFERENCES vessel_types(id)
                ON DELETE SET NULL;
            END IF;
        END $$
    """)

    # ------------------------------------------------------------------ #
    # criticality columns (idempotent — 0009 may have not run)            #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE components
        ADD COLUMN IF NOT EXISTS criticality VARCHAR(20) NOT NULL DEFAULT 'non_critical'
    """)
    op.execute("""
        UPDATE components SET criticality = 'critical'
        WHERE is_critical = true AND criticality = 'non_critical'
    """)

    op.execute("""
        ALTER TABLE component_structure_library
        ADD COLUMN IF NOT EXISTS criticality VARCHAR(20) NOT NULL DEFAULT 'non_critical'
    """)
    op.execute("""
        UPDATE component_structure_library SET criticality = 'critical'
        WHERE is_critical = true AND criticality = 'non_critical'
    """)


def downgrade() -> None:
    # Non-destructive downgrade — leave tables as-is
    pass
