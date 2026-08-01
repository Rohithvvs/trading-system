from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecayedArticleDetail(BaseModel):
    article_id: str
    title: str
    published_at: str | None = None
    age_hours: float
    raw_sentiment: float
    decay_multiplier: float
    decayed_sentiment: float


class SentimentDecayTelemetry(BaseModel):
    aggregate_raw_score: float
    aggregate_decayed_score: float
    article_count: int
    decayed_article_count: int
    zeroed_article_count: int
    articles: list[DecayedArticleDetail] = Field(default_factory=list)
    executed_at: str


class MarketBreadthTelemetry(BaseModel):
    universe_size: int
    valid_stock_count: int
    above_200ma_count: int
    breadth_percentage: float
    regime_label: Literal["strong", "favorable", "neutral", "weak", "very_weak", "unreliable"]
    soft_score_contribution: float
    is_valid: bool
    executed_at: str


class ShadowOutputsPayload(BaseModel):
    news_dedup: dict | None = None
    sentiment_decay: SentimentDecayTelemetry | None = None
    market_breadth: MarketBreadthTelemetry | None = None


class AblationMetrics(BaseModel):
    sample_size: int
    false_positive_rate: float
    win_rate: float
    precision: float
    signal_accuracy: float
    alpha_attribution_pct: float


class AttributionReport(BaseModel):
    evaluation_window_days: int
    total_samples: int
    baseline_metrics: AblationMetrics
    decay_only_metrics: AblationMetrics
    breadth_only_metrics: AblationMetrics
    combined_metrics: AblationMetrics
    situation_tag_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=_utc_now)
    status: Literal["VALID", "INSUFFICIENT_DATA"]


class InteractionAnalysis(BaseModel):
    decay_feature_key: str = "sentiment_decay"
    breadth_feature_key: str = "market_breadth"
    pearson_correlation: float
    spearman_correlation: float
    redundancy_classification: Literal["COMPLEMENTARY", "MODERATE_OVERLAP", "REDUNDANT"]
    decay_promotion_recommendation: Literal["GO", "NO_GO"]
    breadth_promotion_recommendation: Literal["GO", "NO_GO"]
    rationale: str
    evaluated_at: datetime = Field(default_factory=_utc_now)


class PromotionStateRecord(BaseModel):
    rule_id: str
    stage: Literal["STAGE_1_DECAY", "STAGE_2_BREADTH"]
    previous_state: str
    new_state: str
    promoted_at: datetime = Field(default_factory=_utc_now)
    promoted_by: str
    attribution_report_approved: bool
    kill_switch_active: bool

