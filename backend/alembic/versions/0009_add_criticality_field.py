"""add criticality field to components and component_structure_library

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-29
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add criticality to components (idempotent)
    op.execute("""
        ALTER TABLE components
        ADD COLUMN IF NOT EXISTS criticality VARCHAR(20) NOT NULL DEFAULT 'non_critical'
    """)
    op.execute("""
        UPDATE components SET criticality = 'critical'
        WHERE is_critical = true AND criticality = 'non_critical'
    """)

    # Add criticality to component_structure_library (idempotent)
    op.execute("""
        ALTER TABLE component_structure_library
        ADD COLUMN IF NOT EXISTS criticality VARCHAR(20) NOT NULL DEFAULT 'non_critical'
    """)
    op.execute("""
        UPDATE component_structure_library SET criticality = 'critical'
        WHERE is_critical = true AND criticality = 'non_critical'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE component_structure_library DROP COLUMN IF EXISTS criticality")
    op.execute("ALTER TABLE components DROP COLUMN IF EXISTS criticality")
