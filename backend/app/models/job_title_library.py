from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBase

class JobTitleLibrary(TenantBase):
    __tablename__ = "job_title_library"

    ship_component_job_link_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    vessel_name: Mapped[str] = mapped_column(String(200), nullable=False)
    component_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    component_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    frequency_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    frequency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alternate_frequency_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    alternate_frequency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    responsibility: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"<JobTitleLibrary id={self.id} component={self.component_name} job={self.job_name}>"
