from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

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
    yearly = "yearly"
    hourly = "hourly"


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
        Enum(
            FrequencyType,
            name="frequency_type",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )

    initial_due: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initial_frequency_type: Mapped[Optional[FrequencyType]] = mapped_column(
        Enum(
            FrequencyType,
            name="initial_frequency_type",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )

    cms_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    page_reference: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

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

    @validates("job_description")
    def validate_job_description(self, key: str, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
            
        import re
        # Matches space followed by list markers (e.g. " a. ", " 1) ", " a) ", " 1. ")
        item_pattern = re.compile(r'\s+([a-zA-Z0-9]{1,2}[\.\)])\s+')
        formatted = item_pattern.sub(r'\n\1 ', value)
        
        lines = formatted.splitlines()
        new_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                new_lines.append("")
                continue
                
            if line_str.startswith("/*-"):
                line_str = line_str[3:].strip()
                
            if line_str:
                new_lines.append(f"/*- {line_str}")
                
        return "\n".join(new_lines)
