from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class FineTuneStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RuleUpdateLog(TenantBase):
    __tablename__ = "rule_update_logs"

    correction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    count_trigger: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    def __repr__(self) -> str:
        return f"<RuleUpdateLog entity={self.entity_type} type={self.correction_type}>"


class FewShotStore(TenantBase):
    __tablename__ = "few_shot_stores"

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    examples_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<FewShotStore entity={self.entity_type} v={self.version}>"


class FineTuneRequest(TenantBase):
    __tablename__ = "fine_tune_requests"

    trigger_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    total_corrections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[FineTuneStatus] = mapped_column(
        Enum(FineTuneStatus, name="fine_tune_status"),
        nullable=False,
        default=FineTuneStatus.pending,
    )
    started_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<FineTuneRequest id={self.id} status={self.status}>"
