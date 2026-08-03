"""RE-001 Decision Object and Lab DTOs (contracts: re001-decision-object, re001-lab-api)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


Re001Stage = Literal["OFF", "LAB_SHADOW", "PAPER_LINKED"]
RecommendationState = Literal["BUY", "WATCH", "REJECT"]
MarketRegimeBucket = Literal["Bull", "Sideways", "Bear", "UNKNOWN"]
EvaluationStatus = Literal["success", "rejected_by_rules", "error", "timeout"]


class TradeGuidance(BaseModel):
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    risk_reward_ratio: float | None = None
    complete: bool = False


class Re001Registration(BaseModel):
    engine_id: str = "RE-001"
    name: str = "Trend Continuation Recommendation Engine"
    engine_version: str = "1.0"
    stage: Re001Stage = "OFF"
    enabled: bool = False


class Re001DecisionObject(BaseModel):
    recommendation_id: str
    engine_id: str = "RE-001"
    engine_version: str = "1.0"
    market_regime: MarketRegimeBucket = "UNKNOWN"
    trading_objective: str = "trend_continuation"
    trading_style: str = "long_only_swing"
    strategy_family: str | None = None
    strategy_name: str | None = None
    recommendation_state: RecommendationState
    confidence_score: float
    risk_profile: dict[str, Any] | str = Field(default_factory=dict)
    portfolio_decision: dict[str, Any] | str = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str | dict[str, Any] = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason_codes: list[str] = Field(default_factory=list)
    trade_guidance: TradeGuidance | None = None
    # Lab comparison
    production_action: str | None = None
    production_score: float | None = None
    is_mismatch: bool | None = None
    # Run linkage
    symbol: str | None = None
    scan_run_id: str | None = None
    analysis_history_id: int | None = None
    evaluation_status: EvaluationStatus = "success"


class Re001ComparisonRow(BaseModel):
    symbol: str
    recommendation_id: str
    production_action: str | None = None
    production_score: float | None = None
    re001_state: RecommendationState
    confidence_score: float
    strategy_name: str | None = None
    strategy_family: str | None = None
    is_mismatch: bool | None = None


class Re001ScanComparisonResponse(BaseModel):
    scan_run_id: str
    items: list[Re001ComparisonRow] = Field(default_factory=list)


class Re001HealthSegment(BaseModel):
    engine_id: str = "RE-001"
    buy_count: int = 0
    watch_count: int = 0
    reject_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    mismatch_count: int = 0
    total: int = 0
    runtime_counters: dict[str, int] | None = None


class Re001ScanRunSummary(BaseModel):
    scan_run_id: str
    decision_count: int = 0
    latest_created_at: str | None = None


class Re001RecentScansResponse(BaseModel):
    items: list[Re001ScanRunSummary] = Field(default_factory=list)
