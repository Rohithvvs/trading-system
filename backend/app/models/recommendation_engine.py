"""First-class storage for RE-001 (and future RE-00x) Decision Objects."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationEngineDecision(Base):
    __tablename__ = "recommendation_engine_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    engine_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="RE-001")
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="swing")
    scan_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    analysis_history_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    market_regime: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    trading_objective: Mapped[str] = mapped_column(String(64), nullable=False, default="trend_continuation")
    trading_style: Mapped[str] = mapped_column(String(64), nullable=False, default="long_only_swing")
    strategy_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recommendation_state: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    risk_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    portfolio_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    trade_guidance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    production_action: Mapped[str | None] = mapped_column(String(12), nullable=True)
    production_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mismatch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
