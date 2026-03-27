from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.vessel import VesselProject


class AmbiguityQueue(TenantBase):
    __tablename__ = "ambiguity_queue"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)

    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_page: Mapped[Optional[int]] = mapped_column(nullable=True)
    context_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    resolution_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_pipeline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    vessel: Mapped["VesselProject"] = relationship(
        "VesselProject", foreign_keys=[vessel_id], lazy="select"
    )

    def __repr__(self) -> str:
        return f"<AmbiguityQueue id={self.id} entity={self.entity_type} resolved={self.resolved_at is not None}>"
