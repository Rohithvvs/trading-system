"""Immutable lab execution context for RE-001."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LabExecutionContext:
    symbol: str
    mode: str
    scan_run_id: str
    candles: list[Any] = field(default_factory=list)
    technical_results: list[Any] = field(default_factory=list)
    sentiment_score: float = 0.0
    fundamental_result: Any | None = None
    backtests: list[Any] = field(default_factory=list)
    production_recommendation: Any | None = None
    market_regime: Any | None = None
    sector_overlay: Any | None = None
    market_breadth_soft_score: float | None = None
    user_portfolio: dict[str, Any] | None = None
    risk_settings: dict[str, Any] | None = None
    scan_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    analysis_history_id: int | None = None


def build_lab_context(
    *,
    symbol: str,
    mode: str = "swing",
    scan_run_id: str | None = None,
    candles: list[Any] | None = None,
    technical_results: list[Any] | None = None,
    sentiment_score: float = 0.0,
    fundamental_result: Any | None = None,
    backtests: list[Any] | None = None,
    production_recommendation: Any | None = None,
    market_regime: Any | None = None,
    sector_overlay: Any | None = None,
    market_breadth_soft_score: float | None = None,
    user_portfolio: dict[str, Any] | None = None,
    risk_settings: dict[str, Any] | None = None,
    scan_date: datetime | None = None,
    analysis_history_id: int | None = None,
) -> LabExecutionContext:
    ts = scan_date or datetime.now(timezone.utc)
    run_id = scan_run_id or f"scan-{ts.strftime('%Y%m%dT%H%M%SZ')}"
    return LabExecutionContext(
        symbol=symbol,
        mode=mode,
        scan_run_id=run_id,
        candles=list(candles or []),
        technical_results=list(technical_results or []),
        sentiment_score=float(sentiment_score or 0.0),
        fundamental_result=fundamental_result,
        backtests=list(backtests or []),
        production_recommendation=production_recommendation,
        market_regime=market_regime,
        sector_overlay=sector_overlay,
        market_breadth_soft_score=market_breadth_soft_score,
        user_portfolio=user_portfolio,
        risk_settings=risk_settings,
        scan_date=ts,
        analysis_history_id=analysis_history_id,
    )
