"""fix component_structure_library schema: rename library_version to version, make cols nullable, add rejection_reason

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename library_version → version (code uses 'version' everywhere)
    op.alter_column(
        "component_structure_library",
        "library_version",
        new_column_name="version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="1",
    )

    # Make hierarchy/name columns nullable — user format may not provide all codes
    for col in ("group1_code", "group1_name", "group2_code", "group2_name",
                "machinery_code", "machinery_name"):
        op.alter_column(
            "component_structure_library",
            col,
            nullable=True,
            existing_type=sa.String(300),
        )

    # Add rejection_reason (used by reject_node endpoint)
    op.add_column(
        "component_structure_library",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("component_structure_library", "rejection_reason")

    for col in ("group1_code", "group1_name", "group2_code", "group2_name",
                "machinery_code", "machinery_name"):
        op.alter_column(
            "component_structure_library",
            col,
            nullable=False,
            existing_type=sa.String(300),
        )

    op.alter_column(
        "component_structure_library",
        "version",
        new_column_name="library_version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="1",
    )
