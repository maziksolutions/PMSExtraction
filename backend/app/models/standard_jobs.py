from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase
from app.models.job import FrequencyType

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.vessel import VesselProject


class ClassSociety(str, enum.Enum):
    general = "General"
    dnv_gl = "DNV GL"
    lr = "Lloyd's Register"
    bv = "Bureau Veritas"
    abs = "ABS"
    classnk = "ClassNK"
    kr = "KR"
    irs = "IRS"


class MatchStatus(str, enum.Enum):
    matched = "matched"
    partial = "partial"
    not_found = "not_found"
    not_applicable = "not_applicable"


class VesselTypeTemplate(TenantBase):
    __tablename__ = "vessel_type_templates"

    vessel_type: Mapped[str] = mapped_column(String(100), nullable=False)
    machinery_group: Mapped[str] = mapped_column(String(200), nullable=False)
    machinery_name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extraction_types: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment='["components", "jobs", "spares"]',
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<VesselTypeTemplate vessel_type={self.vessel_type} machinery={self.machinery_name}>"


class StandardJob(TenantBase):
    __tablename__ = "standard_jobs"

    class_society: Mapped[ClassSociety] = mapped_column(
        Enum(
            ClassSociety,
            name="class_society",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    machinery_type: Mapped[str] = mapped_column(String(200), nullable=False)
    job_name: Mapped[str] = mapped_column(String(500), nullable=False)
    job_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performing_rank: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    verifying_rank: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    frequency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency_type: Mapped[Optional[FrequencyType]] = mapped_column(
        Enum(
            FrequencyType,
            name="std_frequency_type",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    library_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<StandardJob id={self.id} job={self.job_name}>"


class StandardJobMatch(TenantBase):
    __tablename__ = "standard_job_matches"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    standard_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("standard_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    matched_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    match_status: Mapped[MatchStatus] = mapped_column(
        Enum(
            MatchStatus,
            name="match_status",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=MatchStatus.not_found,
    )

    match_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    not_applicable_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    standard_job: Mapped["StandardJob"] = relationship(
        "StandardJob", foreign_keys=[standard_job_id], lazy="select"
    )
    matched_job: Mapped[Optional["Job"]] = relationship(
        "Job", foreign_keys=[matched_job_id], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<StandardJobMatch id={self.id} status={self.match_status}>"


