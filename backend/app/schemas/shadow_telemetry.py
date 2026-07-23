from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


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
