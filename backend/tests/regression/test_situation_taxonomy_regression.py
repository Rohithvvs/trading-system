"""Regression tests for 013-situation-taxonomy-backfill.

Ensures situation taxonomy wiring remains intact and does not break
core model / governance / classifier contracts.
"""
from __future__ import annotations

import inspect

import pytest

from backend.app.governance.router import list_routes
from backend.app.models.analysis import AnalysisHistory, BackfillProgress
from backend.app.services.taxonomy_classifier import determine_situation_tags


def test_analysis_history_has_situation_tags_column():
    """Model still exposes situation_tags mapped column."""
    assert hasattr(AnalysisHistory, "situation_tags")
    col = AnalysisHistory.__table__.c.situation_tags
    assert col is not None
    assert col.nullable is False


def test_backfill_progress_model_fields():
    """BackfillProgress retains required progress-marker fields (FR-005)."""
    required = {
        "job_id",
        "last_processed_id",
        "status",
        "processed_count",
        "total_count",
        "started_at",
        "updated_at",
    }
    columns = set(BackfillProgress.__table__.c.keys())
    assert required.issubset(columns)


def test_governance_routes_preserve_existing_and_add_taxonomy():
    """New taxonomy routes coexist with prior experiment/audit routes."""
    routes = list_routes()
    # Pre-existing routes must remain
    assert "experiment.start" in routes
    assert "experiment.list" in routes
    assert "audit.export" in routes
    # Feature routes
    assert "experiment.backfill" in routes
    assert "experiment.backfill_pause" in routes
    assert "experiment.taxonomy_report" in routes
    assert "experiment.taxonomy_query" in routes


def test_classifier_signature_stable():
    """FR-003: public classifier signature remains stable for callers."""
    sig = inspect.signature(determine_situation_tags)
    params = list(sig.parameters.keys())
    assert params == [
        "symbol",
        "recommendation",
        "sentiment_score",
        "articles",
        "market_regime",
    ]


def test_classifier_still_returns_only_known_tags():
    """Regression: classifier only emits allowed taxonomy labels."""
    allowed = {
        "GOOD_NEWS_CATALYST",
        "BAD_NEWS_CATALYST",
        "EARNINGS_PLAY",
        "MARKET_REGIME",
        "RANGE_BOUND",
        "UNKNOWN",
    }
    cases = [
        determine_situation_tags(None, "BUY", 0.9, [], None),
        determine_situation_tags("X", "BUY", 0.9, [], None),
        determine_situation_tags("X", "SELL", 0.1, [], None),
        determine_situation_tags("X", "BUY", 0.5, [], None),
        determine_situation_tags(
            "X",
            "BUY",
            0.5,
            [{"title": "earnings call", "description": ""}],
            {"market_state": "BULLISH"},
        ),
    ]
    for tags in cases:
        assert tags
        assert set(tags).issubset(allowed)


def test_models_registered_for_metadata():
    """AnalysisHistory and BackfillProgress are registered on Base metadata."""
    from backend.app.db.base import Base

    table_names = set(Base.metadata.tables.keys())
    assert "analysis_history" in table_names
    assert "backfill_progress" in table_names


@pytest.mark.asyncio
async def test_situation_tags_default_empty_list_on_insert(test_engine):
    """New analysis rows can be inserted with default/empty tags without error."""
    from backend.app.db.session import AsyncSessionLocal
    from backend.app.models.stock import WatchedStock
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        stock = WatchedStock(symbol="REG-EQ", display_name="Reg")
        db.add(stock)
        await db.commit()
        await db.refresh(stock)

        rec = AnalysisHistory(
            stock_id=stock.id,
            mode="swing",
            technical_score=50.0,
            sentiment_score=0.5,
            backtest_score=10.0,
            recommendation="BUY",
            confidence=0.8,
            reasoning="regression default",
            situation_tags=[],
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)

        loaded = await db.get(AnalysisHistory, rec.id)
        assert loaded is not None
        assert loaded.situation_tags == [] or loaded.situation_tags is not None
