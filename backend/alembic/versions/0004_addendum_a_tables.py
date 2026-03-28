"""Addendum A tables: sha256, extraction_prompts, precheck, structure_library, global_libs, manual_matches

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-28
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # F-09: sha256 hash on manuals for duplicate detection
    op.add_column("manuals", sa.Column("sha256_hash", sa.String(64), nullable=True))
    op.add_column("manuals", sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("manuals", sa.Column("duplicate_of_id", UUID(as_uuid=True), nullable=True))

    # F-01: source page fields on components, jobs, spares
    op.add_column("components", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("components", sa.Column("source_sheet_name", sa.String(200), nullable=True))
    op.add_column("jobs", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("spares", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("spares", sa.Column("source_sheet_name", sa.String(200), nullable=True))

    # F-02: extraction prompts
    op.create_table(
        "extraction_prompts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("prompt_key", sa.String(100), nullable=False),
        sa.Column("extraction_type", sa.String(20), nullable=False),  # component/job/spare
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("few_shot_example", sa.Text(), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True, server_default="4096"),
        sa.Column("temperature", sa.Float(), nullable=True, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    # F-10: instruction manual precheck
    op.create_table(
        "instruction_manual_precheck",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("vessel_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("machinery_name", sa.String(500), nullable=False),
        sa.Column("machinery_maker", sa.String(200), nullable=True),
        sa.Column("machinery_model", sa.String(200), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="missing"),
        sa.Column("matched_manual_id", UUID(as_uuid=True), nullable=True),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("user_acknowledgement", sa.String(50), nullable=True),
        sa.Column("acknowledgement_reason", sa.Text(), nullable=True),
        sa.Column("acknowledged_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    # F-03: component structure library
    op.create_table(
        "component_structure_library",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("group1_code", sa.String(50), nullable=False),
        sa.Column("group1_name", sa.String(200), nullable=False),
        sa.Column("group2_code", sa.String(50), nullable=False),
        sa.Column("group2_name", sa.String(200), nullable=False),
        sa.Column("machinery_code", sa.String(50), nullable=False),
        sa.Column("machinery_name", sa.String(300), nullable=False),
        sa.Column("component_code", sa.String(50), nullable=True),
        sa.Column("component_name", sa.String(500), nullable=True),
        sa.Column("component_type", sa.String(100), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("library_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "component_structure_library_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "library_node_approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("node_data", JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("submitted_by", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    # F-04: global libraries
    op.create_table(
        "global_component_library",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("canonical_data", JSONB(), nullable=False),
        sa.Column("source_vessels", JSONB(), nullable=False, server_default="[]"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "global_job_library",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("canonical_data", JSONB(), nullable=False),
        sa.Column("source_vessels", JSONB(), nullable=False, server_default="[]"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "global_spare_library",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("canonical_data", JSONB(), nullable=False),
        sa.Column("source_vessels", JSONB(), nullable=False, server_default="[]"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )

    # F-08: cross-project manual matches
    op.create_table(
        "manual_matches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("source_manual_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("matched_manual_id", UUID(as_uuid=True), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("match_confidence", sa.String(20), nullable=False),
        sa.Column("match_signals", JSONB(), nullable=True),
        sa.Column("copy_action_taken", sa.String(30), nullable=False, server_default="NONE"),
        sa.Column("copied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("copied_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("manual_matches")
    op.drop_table("global_spare_library")
    op.drop_table("global_job_library")
    op.drop_table("global_component_library")
    op.drop_table("library_node_approval_requests")
    op.drop_table("component_structure_library_versions")
    op.drop_table("component_structure_library")
    op.drop_table("instruction_manual_precheck")
    op.drop_table("extraction_prompts")
    op.drop_column("spares", "source_sheet_name")
    op.drop_column("spares", "source_page_number")
    op.drop_column("jobs", "source_page_number")
    op.drop_column("components", "source_sheet_name")
    op.drop_column("components", "source_page_number")
    op.drop_column("manuals", "duplicate_of_id")
    op.drop_column("manuals", "is_duplicate")
    op.drop_column("manuals", "sha256_hash")
