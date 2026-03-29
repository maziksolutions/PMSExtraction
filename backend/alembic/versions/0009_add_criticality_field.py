"""add criticality field to components and component_structure_library

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add criticality to components (non_critical | essential | critical)
    op.add_column(
        "components",
        sa.Column("criticality", sa.String(20), nullable=False, server_default="non_critical"),
    )
    # Migrate existing is_critical=true → 'critical'
    op.execute(
        "UPDATE components SET criticality = 'critical' WHERE is_critical = true"
    )

    # Add criticality to component_structure_library
    op.add_column(
        "component_structure_library",
        sa.Column("criticality", sa.String(20), nullable=False, server_default="non_critical"),
    )
    # Migrate existing is_critical=true → 'critical'
    op.execute(
        "UPDATE component_structure_library SET criticality = 'critical' WHERE is_critical = true"
    )


def downgrade() -> None:
    op.drop_column("component_structure_library", "criticality")
    op.drop_column("components", "criticality")
