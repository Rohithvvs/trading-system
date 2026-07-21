from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
import json

from ..db.base import Base


class ChoiceArray(TypeDecorator):
    """Platform-independent ARRAY type.
    Uses PostgreSQL's ARRAY type, or JSON-serialized TEXT on SQLite.
    """
    impl = Text
    cache_ok = True

    def __init__(self, item_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_type = item_type

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(ARRAY(self.item_type))
        else:
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if dialect.name == 'postgresql':
            return value
        if value == '{}':
            return []
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            if value.startswith('{') and value.endswith('}'):
                return [x.strip() for x in value[1:-1].split(',') if x.strip()]
            return []



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

    shadow_outputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    situation_tags: Mapped[list[str]] = mapped_column(ChoiceArray(Text), server_default="{}", nullable=False)

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


class ArticleDedupLog(Base):
    """Audit row for a removed near-duplicate article (FR-009).

    Table name matches the specification clarification: ``news_deduplication_audit``.
    """

    __tablename__ = "news_deduplication_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(25), index=True)
    kept_id: Mapped[str] = mapped_column(String(500), nullable=False)
    deduplicated_id: Mapped[str] = mapped_column(String(500), nullable=False)
    kept_title: Mapped[str] = mapped_column(Text, nullable=False)
    deduplicated_title: Mapped[str] = mapped_column(Text, nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(250), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class BackfillProgress(Base):
    __tablename__ = "backfill_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    last_processed_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)



