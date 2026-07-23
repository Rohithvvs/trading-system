"""Unit tests for 014 shadow telemetry Pydantic schemas.

Spec source: specs/014-shadow-sentiment-breadth/
  - contracts/shadow_telemetry_schema.json
  - data-model.md entities SentimentDecayResult / MarketBreadthResult
  - FR-003, FR-005, FR-008
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.shadow_telemetry import (
    DecayedArticleDetail,
    MarketBreadthTelemetry,
    SentimentDecayTelemetry,
    ShadowOutputsPayload,
)


def test_decayed_article_detail_requires_diagnostic_fields():
    """FR-003: article diagnostics require id, title, age, raw, mult, decayed."""
    detail = DecayedArticleDetail(
        article_id="news_101",
        title="Earnings Beat",
        published_at="2026-07-21T10:00:00Z",
        age_hours=24.0,
        raw_sentiment=80.0,
        decay_multiplier=0.5,
        decayed_sentiment=40.0,
    )
    assert detail.article_id == "news_101"
    assert detail.decayed_sentiment == 40.0


def test_sentiment_decay_telemetry_round_trip():
    """SentimentDecayTelemetry accepts contract-shaped payloads."""
    payload = {
        "aggregate_raw_score": 75.0,
        "aggregate_decayed_score": 52.4,
        "article_count": 2,
        "decayed_article_count": 1,
        "zeroed_article_count": 1,
        "articles": [
            {
                "article_id": "news_101",
                "title": "Earnings Beat",
                "published_at": "2026-07-21T10:00:00Z",
                "age_hours": 24.0,
                "raw_sentiment": 80.0,
                "decay_multiplier": 0.5,
                "decayed_sentiment": 40.0,
            }
        ],
        "executed_at": "2026-07-22T10:44:00Z",
    }

    model = SentimentDecayTelemetry.model_validate(payload)
    dumped = model.model_dump()
    assert dumped["article_count"] == 2
    assert dumped["articles"][0]["decay_multiplier"] == 0.5
    assert set(dumped.keys()) >= {
        "aggregate_raw_score",
        "aggregate_decayed_score",
        "article_count",
        "decayed_article_count",
        "zeroed_article_count",
        "articles",
        "executed_at",
    }


def test_sentiment_decay_telemetry_missing_required_field_fails():
    """Failure: incomplete sentiment_decay payload is rejected by schema."""
    with pytest.raises(ValidationError):
        SentimentDecayTelemetry.model_validate(
            {
                "aggregate_raw_score": 1.0,
                # missing remaining required fields
            }
        )


def test_market_breadth_telemetry_accepts_all_regime_labels():
    """FR-005: all five regimes plus unreliable are accepted by schema."""
    for label in ("strong", "favorable", "neutral", "weak", "very_weak", "unreliable"):
        model = MarketBreadthTelemetry(
            universe_size=10,
            valid_stock_count=10 if label != "unreliable" else 2,
            above_200ma_count=5,
            breadth_percentage=50.0 if label != "unreliable" else 0.0,
            regime_label=label,
            soft_score_contribution=0.0,
            is_valid=label != "unreliable",
            executed_at="2026-07-22T10:44:00Z",
        )
        assert model.regime_label == label


def test_market_breadth_telemetry_rejects_unknown_regime():
    """Failure: unknown regime labels are rejected."""
    with pytest.raises(ValidationError):
        MarketBreadthTelemetry(
            universe_size=10,
            valid_stock_count=10,
            above_200ma_count=5,
            breadth_percentage=50.0,
            regime_label="bullish",  # type: ignore[arg-type]
            soft_score_contribution=0.0,
            is_valid=True,
            executed_at="2026-07-22T10:44:00Z",
        )


def test_shadow_outputs_payload_holds_independent_keys():
    """FR-008: ShadowOutputsPayload stores independent feature namespaces."""
    payload = ShadowOutputsPayload(
        news_dedup={"status": "ok"},
        sentiment_decay=SentimentDecayTelemetry(
            aggregate_raw_score=10.0,
            aggregate_decayed_score=5.0,
            article_count=1,
            decayed_article_count=1,
            zeroed_article_count=0,
            articles=[],
            executed_at="2026-07-22T10:44:00Z",
        ),
        market_breadth=MarketBreadthTelemetry(
            universe_size=10,
            valid_stock_count=10,
            above_200ma_count=8,
            breadth_percentage=80.0,
            regime_label="strong",
            soft_score_contribution=15.0,
            is_valid=True,
            executed_at="2026-07-22T10:44:00Z",
        ),
    )

    data = payload.model_dump()
    assert data["news_dedup"]["status"] == "ok"
    assert data["sentiment_decay"]["article_count"] == 1
    assert data["market_breadth"]["regime_label"] == "strong"
    # Independent keys coexist
    assert set(data.keys()) == {"news_dedup", "sentiment_decay", "market_breadth"}
