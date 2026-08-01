from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# Spec vocabulary (FR-003) ↔ implementation codes used in plan/research.
HEALTH_STATUS_TO_LABEL = {
    "GREEN": "healthy",
    "YELLOW": "caution",
    "RED": "degraded",
    "INSUFFICIENT_DATA": "insufficient data",
}


def health_status_to_label(health_status: str) -> str:
    """Map GREEN/YELLOW/RED/INSUFFICIENT_DATA → healthy/caution/degraded/insufficient data."""
    key = (health_status or "").strip().upper().replace(" ", "_")
    if key in HEALTH_STATUS_TO_LABEL:
        return HEALTH_STATUS_TO_LABEL[key]
    # Already a spec label or unknown — pass through normalized lower form.
    return (health_status or "").strip().lower() or "insufficient data"


class RuleGovernanceRecord(BaseModel):
    """30-day performance evaluation snapshot of a promoted production rule."""

    rule_id: str = Field(..., description="Unique identifier of promoted rule")
    evaluated_at: str = Field(
        ..., description="ISO format UTC timestamp of this rule evaluation"
    )
    health_status: str = Field(
        ...,
        description=(
            "Machine health code: GREEN, YELLOW, RED, or INSUFFICIENT_DATA "
            "(plan/research vocabulary)"
        ),
    )
    health_label: str = Field(
        default="",
        description=(
            "Spec FR-003 vocabulary: healthy, caution, degraded, or insufficient data "
            "(derived from health_status when omitted)"
        ),
    )
    false_positive_rate_30d: Optional[float] = Field(
        None, description="Rolling 30-day false-positive rate (None if sample count < 15)"
    )
    baseline_false_positive_rate: float = Field(
        ..., description="Original baseline false-positive rate from baseline_v1.0.json"
    )
    sample_count_30d: int = Field(
        ..., description="Number of BUY recommendations evaluated in 30d window"
    )
    status_reason: str = Field(
        ..., description="Explanatory text for assigned health status"
    )

    @model_validator(mode="after")
    def _fill_health_label(self) -> "RuleGovernanceRecord":
        if not self.health_label:
            self.health_label = health_status_to_label(self.health_status)
        return self


class RuleGovernanceResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/rule-governance."""

    evaluated_at: str = Field(..., description="ISO format UTC timestamp of evaluation run")
    promoted_rules_count: int = Field(..., description="Number of promoted rules evaluated")
    rules: List[RuleGovernanceRecord] = Field(..., description="List of rule evaluation records")


class SectorStrengthItem(BaseModel):
    """Sector relative strength metric item."""

    sector: str = Field(..., description="Sector name")
    sector_return_pct: float = Field(..., description="Average sector return percentage")
    relative_strength: Optional[float] = Field(
        None, description="Sector return minus benchmark return (None if low confidence)"
    )
    label: str = Field(
        ..., description="Outperforming, Neutral, or Underperforming"
    )
    constituent_count: int = Field(..., description="Number of constituent stocks in sector")
    confidence: str = Field(..., description="Confidence level: high or low")


class SectorStrengthTelemetry(BaseModel):
    """Shadow output schema for sector strength feature."""

    executed_at: str = Field(..., description="ISO timestamp of execution")
    status: str = Field(..., description="Execution status e.g. success or partial")
    benchmark_symbol: str = Field("NIFTY50", description="Benchmark index symbol")
    benchmark_return_pct: float = Field(0.0, description="Benchmark return percentage")
    sectors: List[SectorStrengthItem] = Field(default_factory=list)


class EngineHealthResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/engine-health."""

    window_days: int = Field(7, description="Aggregation window in days")
    total_scans: int = Field(
        0, description="Distinct stocks analyzed in window (scan coverage proxy)"
    )
    total_recommendations: int = Field(0, description="Total recommendations generated")
    signal_distribution: Dict[str, int] = Field(
        default_factory=lambda: {"BUY": 0, "SELL": 0, "HOLD": 0},
        description="Count of signals by recommendation type",
    )
    positive_outcome_rate: Optional[float] = Field(
        None, description="Rate of BUY recommendations with positive backtest outcome"
    )
    average_confidence_score: float = Field(
        0.0, description="Average confidence score across recommendations"
    )
    generated_at: str = Field(..., description="ISO timestamp when response was generated")


class ShadowStatusRuleItem(BaseModel):
    """Telemetry item for an active shadow rule."""

    status: str = Field("active", description="Status of shadow rule e.g. active")
    total_executions_7d: int = Field(0, description="Total shadow executions in last 7 days")
    last_executed_at: Optional[str] = Field(
        None, description="ISO timestamp of last execution"
    )
    last_status: Optional[str] = Field(
        None, description="Status field from most recent telemetry payload"
    )
    last_output_summary: Optional[Dict[str, Any]] = Field(
        None, description="Compact summary of latest shadow output metrics"
    )


class ShadowStatusResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/shadow-status."""

    active_shadow_rules: List[str] = Field(
        default_factory=lambda: [
            "news_dedup",
            "sentiment_decay",
            "market_breadth",
            "sector_strength",
        ],
        description="List of active shadow rules",
    )
    rules_telemetry: Dict[str, ShadowStatusRuleItem] = Field(
        default_factory=dict, description="Telemetry details per shadow rule"
    )
    generated_at: str = Field(..., description="ISO timestamp when response was generated")
