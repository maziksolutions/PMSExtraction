from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase
from app.models.component import QCStatus

if TYPE_CHECKING:
    from app.models.component import Component
    from app.models.ingestion import Manual
    from app.models.vessel import VesselProject


class ExtractionMethod(str, enum.Enum):
    table = "table"
    drawing = "drawing"
    text = "text"


class Spare(TenantBase):
    __tablename__ = "spares"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    component_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    part_name: Mapped[str] = mapped_column(String(500), nullable=False)
    part_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    drawing_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    drawing_position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spare_assembly: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    assembly_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spare_maker: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    spare_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Resolved from component
    machinery_maker: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    machinery_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    source_manual_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manuals.id", ondelete="SET NULL"),
        nullable=True,
    )

    page_reference: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(
            ExtractionMethod,
            name="extraction_method",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ExtractionMethod.table,
    )

    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qc_status: Mapped[QCStatus] = mapped_column(
        Enum(
            QCStatus,
            name="qc_status",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=QCStatus.pending,
    )

    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    merged_into_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spares.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject", foreign_keys=[vessel_id], lazy="select"
    )
    component: Mapped[Optional["Component"]] = relationship(
        "Component", foreign_keys=[component_id], lazy="select"
    )
    source_manual: Mapped[Optional["Manual"]] = relationship(
        "Manual", foreign_keys=[source_manual_id], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Spare id={self.id} part={self.part_name} qc={self.qc_status}>"
