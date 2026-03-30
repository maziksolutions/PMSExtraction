"""Add shipyard to vessels and maker_models library table

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-30
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE vessel_projects
        ADD COLUMN IF NOT EXISTS shipyard VARCHAR(255)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS maker_models (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL,
            maker            VARCHAR(255) NOT NULL,
            model            VARCHAR(255),
            component_category VARCHAR(100),
            is_deleted       BOOLEAN NOT NULL DEFAULT false,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_maker_models_tenant_maker_model
        ON maker_models (tenant_id, maker, COALESCE(model, ''))
        WHERE is_deleted = false
    """)


def downgrade() -> None:
    pass
