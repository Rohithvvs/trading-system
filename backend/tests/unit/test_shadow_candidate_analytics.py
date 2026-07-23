"""Unit tests for shadow candidate analytics correlation (FR-011 / SC-005)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.analytics_service import AnalyticsService


@pytest.mark.asyncio
async def test_query_shadow_candidates_by_situation_tags_projects_keys(monkeypatch):
    service = AnalyticsService()

    history = SimpleNamespace(
        id=11,
        recommendation="BUY",
        situation_tags=["GOOD_NEWS_CATALYST", "MARKET_REGIME"],
        shadow_outputs={
            "sentiment_decay": {"article_count": 2, "aggregate_decayed_score": 40.0},
            "market_breadth": {"regime_label": "strong", "is_valid": True},
            "news_dedup": {"kept_news_count": 3},
        },
        created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        technical_score=75.0,
        sentiment_score=0.8,
        stock=SimpleNamespace(symbol="RELIANCE-EQ"),
    )

    async def fake_query(db, tags, **kwargs):
        return [history]

    monkeypatch.setattr(service, "query_by_situation_tags", fake_query)

    rows = await service.query_shadow_candidates_by_situation_tags(
        db=MagicMock(),
        tags=["GOOD_NEWS_CATALYST"],
        limit=10,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["history_id"] == 11
    assert row["symbol"] == "RELIANCE-EQ"
    assert row["sentiment_decay"]["article_count"] == 2
    assert row["market_breadth"]["regime_label"] == "strong"
    assert row["news_dedup"]["kept_news_count"] == 3
    assert "GOOD_NEWS_CATALYST" in row["situation_tags"]


@pytest.mark.asyncio
async def test_query_shadow_candidates_filters_incomplete_payloads(monkeypatch):
    service = AnalyticsService()

    complete = SimpleNamespace(
        id=1,
        recommendation="BUY",
        situation_tags=["MARKET_REGIME"],
        shadow_outputs={
            "sentiment_decay": {"article_count": 1},
            "market_breadth": {"regime_label": "neutral"},
        },
        created_at=None,
        technical_score=50.0,
        sentiment_score=0.5,
        stock=SimpleNamespace(symbol="TCS-EQ"),
    )
    incomplete = SimpleNamespace(
        id=2,
        recommendation="HOLD",
        situation_tags=["MARKET_REGIME"],
        shadow_outputs={"sentiment_decay": {"article_count": 1}},  # missing breadth
        created_at=None,
        technical_score=40.0,
        sentiment_score=0.4,
        stock=SimpleNamespace(symbol="INFY-EQ"),
    )

    async def fake_query(db, tags, **kwargs):
        return [complete, incomplete]

    monkeypatch.setattr(service, "query_by_situation_tags", fake_query)

    rows = await service.query_shadow_candidates_by_situation_tags(
        db=MagicMock(),
        tags=["MARKET_REGIME"],
        require_shadow_keys=True,
    )
    assert len(rows) == 1
    assert rows[0]["history_id"] == 1

    rows_all = await service.query_shadow_candidates_by_situation_tags(
        db=MagicMock(),
        tags=["MARKET_REGIME"],
        require_shadow_keys=False,
    )
    assert len(rows_all) == 2
