"""Initial schema — all tables for Sprints 1-12

Revision ID: 0001
Revises:
Create Date: 2026-03-27
"""

from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "super_admin", "vessel_admin", "qc_reviewer", "viewer", "api_integration",
                name="user_role",
            ),
            nullable=False,
            server_default="qc_reviewer",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )

    # --------------------------------------------------------------- vessels
    op.create_table(
        "vessel_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("imo_number", sa.String(20), nullable=False, index=True),
        sa.Column("vessel_type", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "ingesting", "classifying", "reviewing", "exporting", "complete",
                name="vessel_status",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("sharepoint_folder_url", sa.String(2048), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("export_schema_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "vessel_project_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False),
    )

    # --------------------------------------------------------------- manuals
    op.create_table(
        "manuals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("file_extension", sa.String(20), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sharepoint_path", sa.String(2048), nullable=True),
        sa.Column("blob_storage_key", sa.String(1024), nullable=True),
        sa.Column(
            "status",
            sa.Enum("queued", "downloading", "converting", "translating", "scanning", "classified", "failed", name="manual_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detected_language", sa.String(10), nullable=True),
        sa.Column("translated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "virus_scan_status",
            sa.Enum("pending", "clean", "infected", "error", name="virus_scan_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("classification_confidence", sa.Integer(), nullable=True),
        sa.Column("useful_for_extraction", sa.String(20), nullable=True),
        sa.Column("pages_with_components", sa.Text(), nullable=True),
        sa.Column("pages_with_jobs", sa.Text(), nullable=True),
        sa.Column("pages_with_spares", sa.Text(), nullable=True),
        sa.Column("reviewer_comments", sa.Text(), nullable=True),
    )

    op.create_table(
        "ingestion_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sharepoint_folder_url", sa.String(2048), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("downloaded_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "failed", "cancelled", name="ingestion_session_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --------------------------------------------------------------- feedback
    op.create_table(
        "feedback_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("original_value", postgresql.JSON(), nullable=True),
        sa.Column("corrected_value", postgresql.JSON(), nullable=True),
        sa.Column(
            "correction_type",
            sa.Enum("false_positive", "false_negative", "wrong_value", "wrong_mapping", name="correction_type"),
            nullable=False,
        ),
        sa.Column("vessel_type", sa.String(100), nullable=True),
        sa.Column("source_manual_category", sa.String(100), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("context_span", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    )

    # ------------------------------------------------------------ components
    op.create_table(
        "components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("group1", sa.String(200), nullable=False),
        sa.Column("group2", sa.String(200), nullable=False),
        sa.Column("main_machinery", sa.String(300), nullable=False),
        sa.Column("component_name", sa.String(500), nullable=False),
        sa.Column("maker", sa.String(200), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("source_manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_reference", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "qc_status",
            sa.Enum("pending", "accepted", "rejected", "modified", name="qc_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("is_unmapped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("extraction_notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "component_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("template_data", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )

    # --------------------------------------------------------------- jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_name", sa.String(500), nullable=False),
        sa.Column("job_code", sa.String(100), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("safety_precaution", sa.Text(), nullable=True),
        sa.Column("tools_required", sa.String(500), nullable=True),
        sa.Column("performing_rank", sa.String(100), nullable=True),
        sa.Column("verifying_rank", sa.String(100), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column(
            "frequency_type",
            sa.Enum("daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly", "running_hours", name="frequency_type"),
            nullable=True,
        ),
        sa.Column("initial_due", sa.Integer(), nullable=True),
        sa.Column(
            "initial_frequency_type",
            sa.Enum("daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly", "running_hours", name="initial_frequency_type"),
            nullable=True,
        ),
        sa.Column("cms_id", sa.String(100), nullable=True),
        sa.Column("page_reference", sa.Integer(), nullable=True),
        sa.Column("pdf_reference", sa.String(512), nullable=True),
        sa.Column("source_reference", sa.String(200), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("qc_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("is_unmapped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
    )

    # --------------------------------------------------------------- spares
    op.create_table(
        "spares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id", ondelete="SET NULL"), nullable=True),
        sa.Column("part_name", sa.String(500), nullable=False),
        sa.Column("part_number", sa.String(200), nullable=True),
        sa.Column("drawing_number", sa.String(200), nullable=True),
        sa.Column("drawing_position", sa.String(100), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("spare_maker", sa.String(200), nullable=True),
        sa.Column("spare_model", sa.String(200), nullable=True),
        sa.Column("machinery_maker", sa.String(200), nullable=True),
        sa.Column("machinery_model", sa.String(200), nullable=True),
        sa.Column("source_manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_reference", sa.Integer(), nullable=True),
        sa.Column(
            "extraction_method",
            sa.Enum("table", "drawing", "text", name="extraction_method"),
            nullable=False,
            server_default="table",
        ),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("qc_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # --------------------------------------------------------- standard jobs
    op.create_table(
        "vessel_type_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_type", sa.String(100), nullable=False),
        sa.Column("machinery_group", sa.String(200), nullable=False),
        sa.Column("machinery_name", sa.String(300), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("extraction_types", postgresql.JSON(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "standard_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "class_society",
            sa.Enum("DNV GL", "Lloyd's Register", "Bureau Veritas", "ABS", "ClassNK", name="class_society"),
            nullable=False,
        ),
        sa.Column("machinery_type", sa.String(200), nullable=False),
        sa.Column("job_name", sa.String(500), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column("frequency_type", sa.String(30), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("library_reference", sa.String(200), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "standard_job_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("standard_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("standard_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "match_status",
            sa.Enum("matched", "partial", "not_found", "not_applicable", name="match_status"),
            nullable=False,
            server_default="not_found",
        ),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("not_applicable_reason", sa.String(500), nullable=True),
    )

    # ---------------------------------------------------- missing manual gaps
    op.create_table(
        "missing_manual_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("machinery_group", sa.String(200), nullable=False),
        sa.Column("machinery_name", sa.String(300), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "gap_status",
            sa.Enum("identified", "accepted", "pending_upload", "override", name="gap_status"),
            nullable=False,
            server_default="identified",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ----------------------------------------------------------- activity
    op.create_table(
        "activity_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
    )

    # ----------------------------------------------------------- export
    op.create_table(
        "export_schemas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sheet_mappings", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    )

    op.create_table(
        "export_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("export_schema_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("export_schemas.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("blob_storage_key", sa.String(1024), nullable=False),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("row_counts", postgresql.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("generating", "ready", "failed", name="export_status"),
            nullable=False,
            server_default="generating",
        ),
    )

    # ---------------------------------------------------------- AI assistant
    op.create_table(
        "ambiguity_queues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vessel_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("context_page", sa.Integer(), nullable=True),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_text", sa.Text(), nullable=True),
        sa.Column("created_by_pipeline", sa.Boolean(), nullable=False, server_default="true"),
    )

    # ---------------------------------------------------------- learning
    op.create_table(
        "rule_update_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("correction_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("count_trigger", sa.Integer(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
    )

    op.create_table(
        "few_shot_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("examples_json", postgresql.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "fine_tune_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("trigger_reason", sa.String(200), nullable=False),
        sa.Column("total_corrections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="fine_tune_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(100), nullable=True),
    )

    # ------------------------------------------------------------ audit
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_summary", postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("fine_tune_requests")
    op.drop_table("few_shot_stores")
    op.drop_table("rule_update_logs")
    op.drop_table("ambiguity_queues")
    op.drop_table("export_versions")
    op.drop_table("export_schemas")
    op.drop_table("activity_entries")
    op.drop_table("missing_manual_gaps")
    op.drop_table("standard_job_matches")
    op.drop_table("standard_jobs")
    op.drop_table("vessel_type_templates")
    op.drop_table("spares")
    op.drop_table("jobs")
    op.drop_table("component_templates")
    op.drop_table("components")
    op.drop_table("feedback_entries")
    op.drop_table("ingestion_sessions")
    op.drop_table("manuals")
    op.drop_table("vessel_project_users")
    op.drop_table("vessel_projects")
    op.drop_table("users")

    # Drop enums
    for enum_name in [
        "user_role", "vessel_status", "manual_status", "virus_scan_status",
        "ingestion_session_status", "correction_type", "qc_status",
        "frequency_type", "initial_frequency_type", "extraction_method",
        "class_society", "match_status", "gap_status", "export_status",
        "fine_tune_status",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
