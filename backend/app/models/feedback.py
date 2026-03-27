from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBase

if TYPE_CHECKING:
    from app.models.ingestion import Manual
    from app.models.user import User


class CorrectionType(str, enum.Enum):
    false_positive = "false_positive"
    false_negative = "false_negative"
    wrong_value = "wrong_value"
    wrong_mapping = "wrong_mapping"


class FeedbackEntry(TenantBase):
    __tablename__ = "feedback_entries"

    manual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manuals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="manual_classification / component / job / spare",
    )

    original_value: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="AI output before correction",
    )

    corrected_value: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Human-corrected value",
    )

    correction_type: Mapped[CorrectionType] = mapped_column(
        Enum(CorrectionType, name="correction_type"),
        nullable=False,
    )

    vessel_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    source_manual_category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    context_span: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationships
    manual: Mapped["Manual"] = relationship(
        "Manual",
        foreign_keys=[manual_id],
        lazy="select",
    )

    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<FeedbackEntry id={self.id} entity_type={self.entity_type} type={self.correction_type}>"


class FeedbackAggregate(TenantBase):
    __tablename__ = "feedback_aggregates"

    period_start: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    period_end: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    correction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vessel_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<FeedbackAggregate entity={self.entity_type} type={self.correction_type} count={self.count}>"
