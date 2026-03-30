from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.user import User


class VesselStatus(str, enum.Enum):
    draft = "draft"
    ingesting = "ingesting"
    classifying = "classifying"
    reviewing = "reviewing"
    exporting = "exporting"
    complete = "complete"


class VesselProject(TenantBase):
    __tablename__ = "vessel_projects"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    imo_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    vessel_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[VesselStatus] = mapped_column(
        Enum(VesselStatus, name="vessel_status"),
        nullable=False,
        default=VesselStatus.draft,
    )

    sharepoint_folder_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )

    shipyard: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    export_schema_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Relationships
    user_assignments: Mapped[List["VesselProjectUser"]] = relationship(
        "VesselProjectUser",
        back_populates="vessel",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<VesselProject id={self.id} name={self.name} imo={self.imo_number}>"


class VesselProjectUser(TenantBase):
    __tablename__ = "vessel_project_users"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject",
        back_populates="user_assignments",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="vessel_assignments",
    )

    def __repr__(self) -> str:
        return f"<VesselProjectUser vessel={self.vessel_id} user={self.user_id} role={self.role}>"
