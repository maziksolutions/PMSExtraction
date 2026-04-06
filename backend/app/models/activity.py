from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vessel import VesselProject


class ActivityEntry(TenantBase):
    __tablename__ = "activity_entries"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g. component.accepted, job.corrected",
    )

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(String(500), nullable=False)

    metadata_json: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    # Relationships
    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject", foreign_keys=[vessel_id], lazy="select"
    )
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ActivityEntry id={self.id} action={self.action_type}>"
