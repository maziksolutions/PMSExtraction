"""add vessel_types table and link to component_structure_library

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

DEFAULT_VESSEL_TYPES = [
    "Oil Tanker",
    "Oil/Chemical Tanker",
    "Chemical Tanker",
    "Gas Carrier",
    "LPG Carrier",
    "Bulk Carrier",
    "Offshore Vessel",
]


def upgrade() -> None:
    op.create_table(
        "vessel_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_unique_constraint(
        "uq_vessel_types_tenant_name",
        "vessel_types",
        ["tenant_id", "name"],
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.add_column(
        "component_structure_library",
        sa.Column("vessel_type_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_csl_vessel_type",
        "component_structure_library",
        "vessel_types",
        ["vessel_type_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_csl_vessel_type", "component_structure_library", type_="foreignkey")
    op.drop_column("component_structure_library", "vessel_type_id")
    op.drop_table("vessel_types")
