"""Regression tests for 014-shadow-sentiment-breadth candidate features.

Ensures:
  - Existing shadow infrastructure still loads
  - New pure functions remain side-effect free
  - Production scoring fields are never written by shadow workers
  - Prior news_dedup shadow key remains usable alongside new keys
  - FR-010 / SC-001: production recommendation path stays free of soft contributions
"""
from __future__ import annotations

import datetime
import inspect

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.analysis import AnalysisHistory
from app.models.stock import WatchedStock
from app.schemas.analysis import ArticleItem
from app.services import shadow_executor as shadow_mod
from app.services.market_breadth import StockBreadthItem, calculate_market_breadth
from app.services.sentiment_decay import calculate_sentiment_time_decay
from app.services.shadow_executor import (
    execute_shadow_market_breadth,
    execute_shadow_sentiment_decay,
)


def test_shadow_executor_exports_new_workers():
    """Regression: new shadow workers are importable from shadow_executor."""
    assert callable(execute_shadow_sentiment_decay)
    assert callable(execute_shadow_market_breadth)
    assert callable(calculate_sentiment_time_decay)
    assert callable(calculate_market_breadth)


def test_pure_functions_have_no_db_side_effects_in_signature():
    """Library-first: pure functions accept data only (no Session/engine params)."""
    decay_params = set(inspect.signature(calculate_sentiment_time_decay).parameters)
    breadth_params = set(inspect.signature(calculate_market_breadth).parameters)

    forbidden = {"session", "db", "engine", "conn", "connection"}
    assert decay_params.isdisjoint(forbidden)
    assert breadth_params.isdisjoint(forbidden)


def test_soft_score_contribution_not_used_in_production_scoring_modules():
    """FR-010: soft_score_contribution must not appear in live scoring services."""
    # Guard against accidental production wiring of soft breadth contribution.
    from app.services import recommendation_service
    from app.agents import recommendation_agent

    rec_src = inspect.getsource(recommendation_service)
    agent_src = inspect.getsource(recommendation_agent)

    assert "soft_score_contribution" not in rec_src
    assert "calculate_market_breadth" not in rec_src
    assert "calculate_sentiment_time_decay" not in rec_src
    assert "soft_score_contribution" not in agent_src
    assert "calculate_market_breadth" not in agent_src


def test_news_dedup_key_preserved_when_new_features_write(
    test_engine, monkeypatch
):
    """Regression: writing new shadow keys must not drop news_dedup telemetry."""
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(shadow_mod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(shadow_mod, "_HISTORY_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(shadow_mod, "_HISTORY_RETRY_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(
        shadow_mod, "_HISTORY_NOT_BEFORE_SLACK", datetime.timedelta(hours=24)
    )

    session = TestingSessionLocal()
    stock = WatchedStock(symbol="REG014", display_name="Regression 014")
    session.add(stock)
    session.commit()
    session.refresh(stock)

    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=60.0,
        sentiment_score=55.0,
        backtest_score=50.0,
        recommendation="HOLD",
        confidence=0.5,
        reasoning="baseline",
        shadow_outputs={
            "news_dedup": {
                "original_news_count": 5,
                "kept_news_count": 3,
                "removed_news_count": 2,
            }
        },
    )
    session.add(history)
    session.commit()
    history_id = history.id
    session.close()

    now = datetime.datetime.now(datetime.timezone.utc)
    articles = [
        ArticleItem(title="Reg News", sentiment_score=40.0, published_at=now),
    ]
    universe = [
        StockBreadthItem(symbol=f"R{i}", current_price=110.0, sma_200=100.0)
        for i in range(10)
    ]

    execute_shadow_sentiment_decay(
        symbol=stock.symbol, articles=articles, scan_time=now, stock_id=stock.id
    )
    execute_shadow_market_breadth(
        symbol=stock.symbol, universe_prices=universe, scan_time=now, stock_id=stock.id
    )

    session = TestingSessionLocal()
    updated = session.query(AnalysisHistory).filter_by(id=history_id).one()
    outputs = updated.shadow_outputs
    assert outputs["news_dedup"]["original_news_count"] == 5
    assert outputs["news_dedup"]["kept_news_count"] == 3
    assert "sentiment_decay" in outputs
    assert "market_breadth" in outputs
    # Production fields unchanged
    assert updated.recommendation == "HOLD"
    assert updated.sentiment_score == 55.0
    assert updated.technical_score == 60.0
    session.close()


def test_sentiment_decay_half_life_constants_stable():
    """Regression: default half-life 24h and max age 72h remain the contract."""
    sig = inspect.signature(calculate_sentiment_time_decay)
    assert sig.parameters["half_life_hours"].default == 24.0
    assert sig.parameters["max_age_hours"].default == 72.0


def test_market_breadth_min_universe_default_stable():
    """Regression: default min universe size remains 10."""
    sig = inspect.signature(calculate_market_breadth)
    assert sig.parameters["min_universe_size"].default == 10


def test_orchestrator_exposes_universe_breadth_builder():
    """Regression: orchestrator can derive full-universe breadth inputs (C1)."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.schemas.analysis import AnalysisMode, TechnicalAnalysisResult

    bulk = {
        AnalysisMode.swing: {
            "A-EQ": TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="BUY",
                score=80.0,
                indicators={"close": 150.0, "sma_200": 100.0},
                summary="ok",
            ),
            "B-EQ": TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="SELL",
                score=20.0,
                indicators={"close": 90.0, "sma_200": 100.0},
                summary="ok",
            ),
        }
    }
    items = OrchestratorAgent._universe_breadth_items_from_bulk(bulk)
    assert {i["symbol"] for i in items} == {"A-EQ", "B-EQ"}
    assert items[0]["sma_200"] == 100.0


def test_merge_shadow_outputs_preserves_sibling_keys(test_engine, monkeypatch):
    """Regression H2: sequential merges of different keys never drop siblings."""
    from app.services.shadow_executor import (
        _merge_shadow_outputs_locked,
        _shadow_outputs_write_lock,
    )

    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = TestingSessionLocal()
    stock = WatchedStock(symbol="MERGE014", display_name="Merge 014")
    session.add(stock)
    session.commit()
    session.refresh(stock)
    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=50.0,
        sentiment_score=50.0,
        backtest_score=50.0,
        recommendation="HOLD",
        confidence=0.5,
        reasoning="merge",
        shadow_outputs={"news_dedup": {"status": "seed"}},
    )
    session.add(history)
    session.commit()
    history_id = history.id
    session.close()

    session = TestingSessionLocal()
    with _shadow_outputs_write_lock:
        row = session.query(AnalysisHistory).filter_by(id=history_id).one()
        _merge_shadow_outputs_locked(
            session, row, {"sentiment_decay": {"article_count": 1}}
        )
    session.close()

    session = TestingSessionLocal()
    with _shadow_outputs_write_lock:
        row = session.query(AnalysisHistory).filter_by(id=history_id).one()
        _merge_shadow_outputs_locked(
            session, row, {"market_breadth": {"regime_label": "strong"}}
        )
    session.close()

    session = TestingSessionLocal()
    final = session.query(AnalysisHistory).filter_by(id=history_id).one()
    assert final.shadow_outputs["news_dedup"]["status"] == "seed"
    assert final.shadow_outputs["sentiment_decay"]["article_count"] == 1
    assert final.shadow_outputs["market_breadth"]["regime_label"] == "strong"
    session.close()
