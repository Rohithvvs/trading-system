from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db.base import Base

class WalkForwardSummary(Base):
    __tablename__ = "walk_forward_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    window_label: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    
    champ_net_return: Mapped[float] = mapped_column(Float)
    chal_net_return: Mapped[float] = mapped_column(Float)
    champ_trade_count: Mapped[int] = mapped_column(Integer)
    chal_trade_count: Mapped[int] = mapped_column(Integer)
    veto_count: Mapped[int] = mapped_column(Integer)
    veto_rate: Mapped[float] = mapped_column(Float)
    champ_expectancy: Mapped[float] = mapped_column(Float)
    chal_expectancy: Mapped[float] = mapped_column(Float)
    champ_profit_factor: Mapped[float] = mapped_column(Float)
    chal_profit_factor: Mapped[float] = mapped_column(Float)
    champ_drawdown: Mapped[float] = mapped_column(Float)
    chal_drawdown: Mapped[float] = mapped_column(Float)
    champ_win_rate: Mapped[float] = mapped_column(Float)
    chal_win_rate: Mapped[float] = mapped_column(Float)
    
    # Optimized parameter values used in Challenger for the out-of-sample window
    opt_vix_caution: Mapped[float | None] = mapped_column(Float, nullable=True)
    opt_vix_highrisk: Mapped[float | None] = mapped_column(Float, nullable=True)
    opt_breadth_caution: Mapped[float | None] = mapped_column(Float, nullable=True)
    opt_breadth_weak: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    verdict: Mapped[str] = mapped_column(String(20))  # PASS, FAIL, INCONCLUSIVE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class VetoHistory(Base):
    __tablename__ = "veto_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    window_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scan_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    gate_name: Mapped[str] = mapped_column(String(50))
    original_signal: Mapped[str] = mapped_column(String(20))
    challenger_signal: Mapped[str] = mapped_column(String(20))
    veto_triggered: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str] = mapped_column(String(10), default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
