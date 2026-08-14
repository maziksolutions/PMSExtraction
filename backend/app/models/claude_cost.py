from __future__ import annotations

import datetime
from sqlalchemy import Date, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class ClaudeDailyCost(Base):
    __tablename__ = "claude_daily_costs"

    date: Mapped[datetime.date] = mapped_column(
        Date,
        primary_key=True,
        nullable=False,
    )

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    def __repr__(self) -> str:
        return f"<ClaudeDailyCost {self.date}: Spend=${self.cost}>"
