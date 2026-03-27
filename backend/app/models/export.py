from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vessel import VesselProject


class ExportVersionStatus(str, enum.Enum):
    generating = "generating"
    ready = "ready"
    failed = "failed"


class ExportSchema(TenantBase):
    __tablename__ = "export_schemas"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sheet_mappings: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="{sheet_name: [{field_name, column_header, column_index}]}",
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    uploader: Mapped["User"] = relationship(
        "User", foreign_keys=[uploaded_by], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ExportSchema id={self.id} name={self.name} v={self.version}>"


class ExportVersion(TenantBase):
    __tablename__ = "export_versions"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    export_schema_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_schemas.id", ondelete="SET NULL"),
        nullable=True,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    blob_storage_key: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    row_counts: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="{components: N, jobs: N, spares: N, excluded: N}",
    )

    status: Mapped[ExportVersionStatus] = mapped_column(
        Enum(ExportVersionStatus, name="export_version_status"),
        nullable=False,
        default=ExportVersionStatus.generating,
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject", foreign_keys=[vessel_id], lazy="select"
    )
    generator: Mapped["User"] = relationship(
        "User", foreign_keys=[generated_by], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ExportVersion id={self.id} vessel={self.vessel_id} v={self.version_number}>"
