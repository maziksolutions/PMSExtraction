from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.ingestion import Manual
    from app.models.vessel import VesselProject


class QCStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    modified = "modified"


class Component(TenantBase):
    __tablename__ = "components"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    group1: Mapped[str] = mapped_column(String(200), nullable=False)
    group2: Mapped[str] = mapped_column(String(200), nullable=False)
    main_machinery: Mapped[str] = mapped_column(String(300), nullable=False)
    component_name: Mapped[str] = mapped_column(String(500), nullable=False)

    maker: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    machinery_particulars: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_manual_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manuals.id", ondelete="SET NULL"),
        nullable=True,
    )

    page_reference: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="non_critical")

    qc_status: Mapped[QCStatus] = mapped_column(
        Enum(QCStatus, name="qc_status"),
        nullable=False,
        default=QCStatus.pending,
    )

    is_unmapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extraction_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Page reference fields — auto-populated from manual classification or manual entry
    job_pages: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spare_pages: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_reference: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject",
        foreign_keys=[vessel_id],
        lazy="select",
    )

    source_manual: Mapped[Optional["Manual"]] = relationship(
        "Manual",
        foreign_keys=[source_manual_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Component id={self.id} name={self.component_name} qc={self.qc_status}>"


class ComponentTemplate(TenantBase):
    __tablename__ = "component_templates"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    template_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="[{group1, group2, main_machinery, component_name}]",
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<ComponentTemplate id={self.id} name={self.name}>"
