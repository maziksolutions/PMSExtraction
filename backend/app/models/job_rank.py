from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase


class JobRank(TenantBase):
    __tablename__ = "job_ranks"

    rank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("ix_job_ranks_tenant_norm", "tenant_id", "normalized_name", unique=True),
    )

    def __repr__(self) -> str:
        return f"<JobRank rank={self.rank_name}>"
