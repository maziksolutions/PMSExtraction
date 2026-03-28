from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.vessel import VesselProject
    from app.models.user import User


class ManualStatus(str, enum.Enum):
    queued = "queued"
    downloading = "downloading"
    converting = "converting"
    translating = "translating"
    scanning = "scanning"
    classified = "classified"
    failed = "failed"


class VirusScanStatus(str, enum.Enum):
    pending = "pending"
    clean = "clean"
    infected = "infected"
    error = "error"


class IngestionSessionStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Manual(TenantBase):
    __tablename__ = "manuals"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    file_extension: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    sharepoint_path: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )

    blob_storage_key: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )

    status: Mapped[ManualStatus] = mapped_column(
        Enum(ManualStatus, name="manual_status"),
        nullable=False,
        default=ManualStatus.queued,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    detected_language: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )

    translated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    virus_scan_status: Mapped[VirusScanStatus] = mapped_column(
        Enum(VirusScanStatus, name="virus_scan_status"),
        nullable=False,
        default=VirusScanStatus.pending,
    )

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Classification fields — populated in Sprint 3
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    classification_confidence: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    useful_for_extraction: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    pages_with_components: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    pages_with_jobs: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    pages_with_spares: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    reviewer_comments: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Extracted text — stored at upload time so it survives ephemeral filesystem redeploys
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # F-09: duplicate detection
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject",
        foreign_keys=[vessel_id],
        lazy="select",
    )

    uploader: Mapped["User"] = relationship(
        "User",
        foreign_keys=[uploaded_by],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Manual id={self.id} filename={self.original_filename} status={self.status}>"


class IngestionSession(TenantBase):
    __tablename__ = "ingestion_sessions"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sharepoint_folder_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    total_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    downloaded_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failed_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    status: Mapped[IngestionSessionStatus] = mapped_column(
        Enum(IngestionSessionStatus, name="ingestion_session_status"),
        nullable=False,
        default=IngestionSessionStatus.active,
    )

    started_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject",
        foreign_keys=[vessel_id],
        lazy="select",
    )

    starter: Mapped["User"] = relationship(
        "User",
        foreign_keys=[started_by],
        lazy="select",
    )

    manuals: Mapped[List["Manual"]] = relationship(
        "Manual",
        primaryjoin="and_(IngestionSession.vessel_id == Manual.vessel_id, "
                    "IngestionSession.tenant_id == Manual.tenant_id)",
        foreign_keys="[Manual.vessel_id]",
        lazy="select",
        viewonly=True,
        overlaps="vessel",
    )

    def __repr__(self) -> str:
        return (
            f"<IngestionSession id={self.id} vessel={self.vessel_id} status={self.status}>"
        )
