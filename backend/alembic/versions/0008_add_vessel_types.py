"""add vessel_types table and link to component_structure_library

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-29

NOTE: Uses raw idempotent SQL (IF NOT EXISTS) because op.create_unique_constraint
with postgresql_where generates ALTER TABLE ADD CONSTRAINT UNIQUE which PostgreSQL
does not support with a WHERE clause — only CREATE UNIQUE INDEX supports that.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create vessel_types table (idempotent)
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

    # Partial unique index — only CREATE UNIQUE INDEX supports WHERE clause in PG
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vessel_types_tenant_name
        ON vessel_types (tenant_id, name)
        WHERE is_deleted = false
    """)

    # Add vessel_type_id to component_structure_library (idempotent)
    op.execute("""
        ALTER TABLE component_structure_library
        ADD COLUMN IF NOT EXISTS vessel_type_id UUID
    """)

    # Add FK only if it doesn't already exist
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


def downgrade() -> None:
    op.execute("ALTER TABLE component_structure_library DROP CONSTRAINT IF EXISTS fk_csl_vessel_type")
    op.execute("ALTER TABLE component_structure_library DROP COLUMN IF EXISTS vessel_type_id")
    op.execute("DROP TABLE IF EXISTS vessel_types")
