from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    # SR-003 Sector RS Overlay Audit Columns
    mapped_sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sector_rs_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_close_vs_ema20: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sector_filter_triggered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    challenger_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_codes: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # SR-004 Market Permission Engine Audit Columns
    market_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_trend_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_breadth_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_volatility_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_new_entry_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    market_risk_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    gross_total_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_scenario: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_transaction_costs: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_slippage: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_sizing_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    stock = relationship("WatchedStock", back_populates="backtests")


class StrategyPerformanceLog(Base):
    __tablename__ = "strategy_performance_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(25), index=True)
    screened_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    initial_score: Mapped[float] = mapped_column(Float)
    dominant_agent: Mapped[str] = mapped_column(String(50))
    realized_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_return_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class ScannedCandidate(Base):
    __tablename__ = "scanned_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(25), index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    screener_name: Mapped[str] = mapped_column(String(100))
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    screener_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched: Mapped[bool] = mapped_column(default=False)
