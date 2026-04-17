from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("watched_stocks.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    technical_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float)
    backtest_score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(12), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    stock = relationship("WatchedStock", back_populates="analyses")


class BacktestHistory(Base):
    __tablename__ = "backtest_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("watched_stocks.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    strategy_name: Mapped[str] = mapped_column(String(80))
    total_return: Mapped[float] = mapped_column(Float)
    cagr: Mapped[float] = mapped_column(Float)
    max_drawdown: Mapped[float] = mapped_column(Float)
    win_rate: Mapped[float] = mapped_column(Float)
    profit_factor: Mapped[float] = mapped_column(Float)
    trade_count: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    stock = relationship("WatchedStock", back_populates="backtests")
