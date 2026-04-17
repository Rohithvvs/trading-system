from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class WatchedStock(Base):
    __tablename__ = "watched_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    analyses = relationship("AnalysisHistory", back_populates="stock", cascade="all, delete-orphan")
    backtests = relationship("BacktestHistory", back_populates="stock", cascade="all, delete-orphan")
