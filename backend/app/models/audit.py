from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class AuditLog(TenantBase):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    ip_address: Mapped[str] = mapped_column(String(50), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    request_summary: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Redacted request body for forensic analysis",
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.method} {self.path} {self.status_code}>"
