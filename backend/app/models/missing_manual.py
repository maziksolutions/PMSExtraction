from __future__ import annotations

import enum
import uuid
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase


class GapStatus(str, enum.Enum):
    identified = "identified"
    accepted = "accepted"
    pending_upload = "pending_upload"
    override = "override"


class MissingManualGap(TenantBase):
    __tablename__ = "missing_manual_gaps"

    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    machinery_group: Mapped[str] = mapped_column(String(200), nullable=False)
    machinery_name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(nullable=False, default=True)

    gap_status: Mapped[GapStatus] = mapped_column(
        Enum(GapStatus, name="gap_status"),
        nullable=False,
        default=GapStatus.identified,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MissingManualGap vessel={self.vessel_id} "
            f"machinery={self.machinery_name} status={self.gap_status}>"
        )
