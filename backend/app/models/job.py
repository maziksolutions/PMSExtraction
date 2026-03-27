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


class FrequencyType(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    half_yearly = "half_yearly"
    yearly = "yearly"
    running_hours = "running_hours"


class Job(TenantBase):
    __tablename__ = "jobs"

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

    job_name: Mapped[str] = mapped_column(String(500), nullable=False)
    job_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    safety_precaution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tools_required: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    performing_rank: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verifying_rank: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    frequency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency_type: Mapped[Optional[FrequencyType]] = mapped_column(
        Enum(FrequencyType, name="frequency_type"),
        nullable=True,
    )

    initial_due: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initial_frequency_type: Mapped[Optional[FrequencyType]] = mapped_column(
        Enum(FrequencyType, name="initial_frequency_type", create_constraint=False),
        nullable=True,
    )

    cms_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    page_reference: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qc_status: Mapped[QCStatus] = mapped_column(
        Enum(QCStatus, name="job_qc_status", create_constraint=False),
        nullable=False,
        default=QCStatus.pending,
    )
    is_unmapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    source_manual_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manuals.id", ondelete="SET NULL"),
        nullable=True,
    )

    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
        return f"<Job id={self.id} name={self.job_name} qc={self.qc_status}>"
