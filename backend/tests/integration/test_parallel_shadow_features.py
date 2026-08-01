"""Integration tests for parallel shadow candidates (FEAT-018 + FEAT-016).

Spec source: specs/014-shadow-sentiment-breadth/spec.md
  - US3 acceptance scenarios 1–3
  - FR-007, FR-008, FR-009, FR-010, FR-011
  - SC-002, SC-003, SC-005
  - Edge: concurrent write contention under independent keys
"""
from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.analysis import AnalysisHistory
from app.models.stock import WatchedStock
from app.schemas.analysis import ArticleItem
from app.schemas.shadow_telemetry import MarketBreadthTelemetry, SentimentDecayTelemetry
from app.services.market_breadth import StockBreadthItem
from app.services import shadow_executor as shadow_mod
from app.services.shadow_executor import (
    execute_shadow_market_breadth,
    execute_shadow_sentiment_decay,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shadow_session_factory(test_engine, monkeypatch):
    """Route SessionLocal to the SQLite test engine with fast history retries."""
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(shadow_mod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(shadow_mod, "_HISTORY_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(shadow_mod, "_HISTORY_RETRY_DELAY_SECONDS", 0.01)
    # Fixture history is created before execute; widen not_before slack for stability.
    monkeypatch.setattr(
        shadow_mod, "_HISTORY_NOT_BEFORE_SLACK", datetime.timedelta(hours=24)
    )
    return TestingSessionLocal


@pytest.fixture
def db_stock_and_history(test_engine, shadow_session_factory):
    """Seed a watched stock and AnalysisHistory row for shadow telemetry writes."""
    session = shadow_session_factory()

    stock = WatchedStock(symbol="TESTPB", display_name="Test Parallel Breadth Inc.")
    session.add(stock)
    session.commit()
    session.refresh(stock)

    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=75.0,
        sentiment_score=80.0,
        backtest_score=80.0,
        recommendation="BUY",
        confidence=0.85,
        reasoning="Test reasoning",
        shadow_outputs={"news_dedup": {"status": "ok", "original_news_count": 3}},
        situation_tags=[
            "GOOD_NEWS_CATALYST",
            "MARKET_REGIME",
            "EARNINGS_WINDOW",
            "HIGH_VOLATILITY",
            "TREND_CONTINUATION",
        ],
    )
    session.add(history)
    session.commit()
    session.refresh(history)

    yield stock, history
    session.close()


def _fresh_articles(now: datetime.datetime) -> list[ArticleItem]:
    return [
        ArticleItem(
            title="Fresh Test News",
            sentiment_score=80.0,
            published_at=now,
            url="http://test.com/1",
        ),
        ArticleItem(
            title="Old Test News",
            sentiment_score=60.0,
            published_at=now - datetime.timedelta(hours=24),
            url="http://test.com/2",
        ),
    ]


def _strong_universe() -> list[StockBreadthItem]:
    return [
        StockBreadthItem(symbol=f"S{i}", current_price=120.0, sma_200=100.0)
        for i in range(8)
    ] + [
        StockBreadthItem(symbol=f"S{i}", current_price=80.0, sma_200=100.0)
        for i in range(8, 10)
    ]


def _reload_history(session_factory, history_id: int) -> AnalysisHistory:
    session = session_factory()
    try:
        row = session.query(AnalysisHistory).filter_by(id=history_id).first()
        assert row is not None
        # Detach values we care about before closing
        session.expunge(row)
        return row
    finally:
        session.close()


# ---------------------------------------------------------------------------
# US3-AS1 / FR-007 / FR-008 — parallel independent keys
# ---------------------------------------------------------------------------


def test_parallel_shadow_features_execution(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """T012 / US3-AS1: both features write independent shadow_outputs keys."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)

    execute_shadow_sentiment_decay(
        symbol=stock.symbol,
        articles=_fresh_articles(now),
        scan_time=now,
        stock_id=stock.id,
    )
    execute_shadow_market_breadth(
        symbol=stock.symbol,
        universe_prices=_strong_universe(),
        scan_time=now,
        stock_id=stock.id,
    )

    updated = _reload_history(shadow_session_factory, history.id)
    outputs = updated.shadow_outputs
    assert outputs is not None

    # Independent keys coexist; prior news_dedup is preserved
    assert "news_dedup" in outputs
    assert outputs["news_dedup"]["status"] == "ok"
    assert "sentiment_decay" in outputs
    assert "market_breadth" in outputs

    # Telemetry completeness (SC-002)
    sd = outputs["sentiment_decay"]
    assert sd["article_count"] == 2
    assert "aggregate_raw_score" in sd
    assert "aggregate_decayed_score" in sd
    assert "zeroed_article_count" in sd
    assert "articles" in sd
    assert "executed_at" in sd
    SentimentDecayTelemetry.model_validate(sd)

    mb = outputs["market_breadth"]
    assert mb["regime_label"] == "strong"
    assert mb["soft_score_contribution"] == 15.0
    assert mb["is_valid"] is True
    assert "breadth_percentage" in mb
    assert "universe_size" in mb
    MarketBreadthTelemetry.model_validate(mb)


def test_concurrent_thread_writes_do_not_drop_keys(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """FR-008: concurrent key writes must retain both feature namespaces (no fallback)."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)
    articles = _fresh_articles(now)
    universe = _strong_universe()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(
            execute_shadow_sentiment_decay,
            stock.symbol,
            articles,
            now,
            stock.id,
        )
        f2 = pool.submit(
            execute_shadow_market_breadth,
            stock.symbol,
            universe,
            now,
            stock.id,
        )
        f1.result(timeout=10)
        f2.result(timeout=10)

    updated = _reload_history(shadow_session_factory, history.id)
    outputs = updated.shadow_outputs or {}
    assert "news_dedup" in outputs
    assert outputs["news_dedup"]["status"] == "ok"
    assert "sentiment_decay" in outputs, "concurrent merge dropped sentiment_decay"
    assert "market_breadth" in outputs, "concurrent merge dropped market_breadth"
    assert outputs["sentiment_decay"]["article_count"] == 2
    assert outputs["market_breadth"]["regime_label"] == "strong"


# ---------------------------------------------------------------------------
# US3-AS2 / FR-009 / FR-010 / SC-003 — fault isolation + production identity
# ---------------------------------------------------------------------------


def test_shadow_crash_isolation_and_production_identity(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """T013: market breadth crash leaves sentiment decay + production intact."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)
    articles = [
        ArticleItem(title="Valid Article", sentiment_score=75.0, published_at=now),
    ]

    baseline_recommendation = history.recommendation
    baseline_sentiment = history.sentiment_score
    baseline_technical = history.technical_score
    baseline_confidence = history.confidence

    with patch(
        "app.services.shadow_executor.calculate_market_breadth",
        side_effect=RuntimeError("Simulated Breadth Crash"),
    ):
        execute_shadow_sentiment_decay(
            symbol=stock.symbol, articles=articles, scan_time=now, stock_id=stock.id
        )
        execute_shadow_market_breadth(
            symbol=stock.symbol, universe_prices=[], scan_time=now, stock_id=stock.id
        )

    updated = _reload_history(shadow_session_factory, history.id)

    # Production recommendation path 100% identical (FR-010 / SC-003)
    assert updated.recommendation == baseline_recommendation == "BUY"
    assert updated.sentiment_score == baseline_sentiment
    assert updated.technical_score == baseline_technical
    assert updated.confidence == baseline_confidence

    outputs = updated.shadow_outputs
    assert outputs is not None
    assert "sentiment_decay" in outputs
    assert outputs["sentiment_decay"]["article_count"] == 1
    # Crashed feature must not overwrite surviving keys
    assert "news_dedup" in outputs
    # market_breadth may be absent or not updated after crash — either is OK
    assert outputs.get("market_breadth") is None or "regime_label" in (
        outputs.get("market_breadth") or {}
    )


def test_sentiment_decay_crash_isolation_preserves_market_breadth(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """FR-009 reverse isolation: sentiment crash does not block market breadth."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)

    with patch(
        "app.services.shadow_executor.calculate_sentiment_time_decay",
        side_effect=RuntimeError("Simulated Sentiment Crash"),
    ):
        execute_shadow_sentiment_decay(
            symbol=stock.symbol,
            articles=_fresh_articles(now),
            scan_time=now,
            stock_id=stock.id,
        )
        execute_shadow_market_breadth(
            symbol=stock.symbol,
            universe_prices=_strong_universe(),
            scan_time=now,
            stock_id=stock.id,
        )

    updated = _reload_history(shadow_session_factory, history.id)
    assert updated.recommendation == "BUY"
    assert updated.sentiment_score == 80.0

    outputs = updated.shadow_outputs
    assert outputs is not None
    assert "market_breadth" in outputs
    assert outputs["market_breadth"]["regime_label"] == "strong"
    assert "news_dedup" in outputs
    # sentiment_decay must not have been partially written with corrupt data
    assert "sentiment_decay" not in outputs or outputs["sentiment_decay"] is None


def test_shadow_workers_swallow_exceptions_without_raising(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """Failure path: execute_* never re-raises into the caller (FR-009)."""
    stock, _history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)

    with patch(
        "app.services.shadow_executor.calculate_sentiment_time_decay",
        side_effect=ValueError("boom"),
    ):
        # Must not raise
        execute_shadow_sentiment_decay(
            symbol=stock.symbol,
            articles=_fresh_articles(now),
            scan_time=now,
            stock_id=stock.id,
        )

    with patch(
        "app.services.shadow_executor.calculate_market_breadth",
        side_effect=ValueError("boom"),
    ):
        execute_shadow_market_breadth(
            symbol=stock.symbol,
            universe_prices=_strong_universe(),
            scan_time=now,
            stock_id=stock.id,
        )


def test_shadow_persistence_skips_missing_stock_without_raise(
    shadow_session_factory, monkeypatch
):
    """Failure path: unknown symbol/stock_id skips telemetry without exception."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # stock_id that does not exist and symbol that won't resolve
    execute_shadow_sentiment_decay(
        symbol="DOES-NOT-EXIST-EQ",
        articles=_fresh_articles(now),
        scan_time=now,
        stock_id=999999,
    )
    execute_shadow_market_breadth(
        symbol="DOES-NOT-EXIST-EQ",
        universe_prices=_strong_universe(),
        scan_time=now,
        stock_id=999999,
    )


def test_execute_shadow_does_not_mutate_caller_article_list(
    test_engine, db_stock_and_history
):
    """FR-010: shadow worker deep-copies inputs; caller list remains intact."""
    stock, _history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)
    articles = _fresh_articles(now)
    original_scores = [a.sentiment_score for a in articles]
    original_titles = [a.title for a in articles]

    execute_shadow_sentiment_decay(
        symbol=stock.symbol, articles=articles, scan_time=now, stock_id=stock.id
    )

    assert [a.sentiment_score for a in articles] == original_scores
    assert [a.title for a in articles] == original_titles


# ---------------------------------------------------------------------------
# US3-AS3 / FR-011 / SC-005 — situation tags correlation
# ---------------------------------------------------------------------------


def test_shadow_telemetry_analytics_query(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """T014 / FR-011: situation_tags coexist with shadow telemetry for analysis."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)

    execute_shadow_sentiment_decay(
        symbol=stock.symbol,
        articles=_fresh_articles(now),
        scan_time=now,
        stock_id=stock.id,
    )
    execute_shadow_market_breadth(
        symbol=stock.symbol,
        universe_prices=_strong_universe(),
        scan_time=now,
        stock_id=stock.id,
    )

    updated = _reload_history(shadow_session_factory, history.id)
    tags = updated.situation_tags or []

    # SC-005: at least 5 distinct situation categories available for A/B work
    assert len(set(tags)) >= 5
    assert "GOOD_NEWS_CATALYST" in tags
    assert "MARKET_REGIME" in tags

    outputs = updated.shadow_outputs
    assert outputs is not None
    assert "sentiment_decay" in outputs
    assert "market_breadth" in outputs

    # Analyst can jointly inspect tags + both shadow feature payloads
    correlated = {
        "situation_tags": tags,
        "sentiment_decay": outputs["sentiment_decay"],
        "market_breadth": outputs["market_breadth"],
    }
    assert correlated["sentiment_decay"]["article_count"] == 2
    assert correlated["market_breadth"]["is_valid"] is True


def test_market_breadth_unreliable_persists_neutral_telemetry(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """US2-AS2 via worker: small universe persists unreliable/neutral contribution."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)
    tiny = [
        StockBreadthItem(symbol="ONLY1", current_price=120.0, sma_200=100.0),
        StockBreadthItem(symbol="ONLY2", current_price=110.0, sma_200=100.0),
    ]

    execute_shadow_market_breadth(
        symbol=stock.symbol, universe_prices=tiny, scan_time=now, stock_id=stock.id
    )

    updated = _reload_history(shadow_session_factory, history.id)
    mb = updated.shadow_outputs["market_breadth"]
    assert mb["is_valid"] is False
    assert mb["regime_label"] == "unreliable"
    assert mb["soft_score_contribution"] == 0.0
    # Soft contribution stored for shadow only — production score untouched
    assert updated.technical_score == 75.0
    assert updated.recommendation == "BUY"


# ---------------------------------------------------------------------------
# Agent wiring (submission hooks)
# ---------------------------------------------------------------------------


def test_news_agent_submits_only_news_dedup_when_shadow_enabled(monkeypatch):
    """H1: news_dedup shadow path must NOT own sentiment_decay submission."""
    from app.agents.news_analysis_agent import NewsAnalysisAgent
    from app.config import settings

    monkeypatch.setattr(settings, "shadow_mode_enabled", True)
    monkeypatch.setattr(settings, "shadow_mode_stage", "SHADOW")

    submitted: list[tuple] = []

    def fake_submit(fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task", fake_submit
    )

    agent = NewsAnalysisAgent()
    articles = _fresh_articles(datetime.datetime.now(datetime.timezone.utc))
    agent._submit_shadow_dedup("RELIANCE-EQ", articles)

    fns = {fn.__name__ if hasattr(fn, "__name__") else str(fn) for fn, _, _ in submitted}
    assert "execute_shadow_news_dedup" in fns
    assert "execute_shadow_sentiment_decay" not in fns


def test_news_agent_skips_shadow_when_disabled(monkeypatch):
    """Shadow disabled: no shadow tasks submitted (production isolation)."""
    from app.agents.news_analysis_agent import NewsAnalysisAgent
    from app.config import settings

    monkeypatch.setattr(settings, "shadow_mode_enabled", False)

    submitted: list = []
    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task",
        lambda *a, **k: submitted.append(a),
    )

    agent = NewsAnalysisAgent()
    agent._submit_shadow_dedup(
        "RELIANCE-EQ",
        _fresh_articles(datetime.datetime.now(datetime.timezone.utc)),
    )
    assert submitted == []


def test_orchestrator_builds_full_universe_breadth_items():
    """C1: breadth items are built from bulk technical results (all symbols)."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.schemas.analysis import AnalysisMode, TechnicalAnalysisResult

    bulk = {
        AnalysisMode.swing: {
            f"S{i}-EQ": TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="BUY",
                score=70.0,
                indicators={"close": 120.0 if i < 8 else 80.0, "sma_200": 100.0},
                summary="t",
            )
            for i in range(10)
        }
    }
    items = OrchestratorAgent._universe_breadth_items_from_bulk(bulk)
    assert len(items) == 10
    assert sum(1 for x in items if x["current_price"] > x["sma_200"]) == 8


def test_orchestrator_submits_both_candidates_with_stock_id_and_universe(monkeypatch):
    """H1/H3/C1: orchestrator submits both features post-persist with stock_id + universe."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.schemas.analysis import AnalysisMode, TechnicalAnalysisResult

    submitted: list[tuple] = []

    def fake_submit(fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task", fake_submit
    )

    bulk = {
        AnalysisMode.swing: {
            f"S{i}-EQ": TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="BUY",
                score=70.0,
                indicators={"close": 110.0, "sma_200": 100.0},
                summary="t",
            )
            for i in range(12)
        }
    }
    articles = _fresh_articles(datetime.datetime.now(datetime.timezone.utc))

    # Method does not require a live DB session object for submission path.
    OrchestratorAgent._submit_shadow_candidate_features(
        OrchestratorAgent.__new__(OrchestratorAgent),
        symbol="S0-EQ",
        stock_id=42,
        articles=articles,
        bulk_technical_results=bulk,
    )

    by_name = {
        (fn.__name__ if hasattr(fn, "__name__") else str(fn)): (args, kwargs)
        for fn, args, kwargs in submitted
    }
    assert "execute_shadow_sentiment_decay" in by_name
    assert "execute_shadow_market_breadth" in by_name

    sent_args, _ = by_name["execute_shadow_sentiment_decay"]
    # symbol, articles, scan_time, stock_id
    assert sent_args[0] == "S0-EQ"
    assert len(sent_args[1]) == 2
    assert sent_args[3] == 42

    mb_args, _ = by_name["execute_shadow_market_breadth"]
    assert mb_args[0] == "S0-EQ"
    assert len(mb_args[1]) == 12
    assert mb_args[3] == 42


def test_orchestrator_candidate_submit_isolated_from_each_other(monkeypatch):
    """H4: failure submitting one candidate does not block the other."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.services.shadow_executor import (
        execute_shadow_market_breadth,
        execute_shadow_sentiment_decay,
    )

    submitted: list[str] = []

    def fake_submit(fn, *args, **kwargs):
        name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        if name == "execute_shadow_sentiment_decay":
            raise RuntimeError("simulated submit failure")
        submitted.append(name)
        return MagicMock()

    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task", fake_submit
    )

    OrchestratorAgent._submit_shadow_candidate_features(
        OrchestratorAgent.__new__(OrchestratorAgent),
        symbol="X-EQ",
        stock_id=1,
        articles=[],
        bulk_technical_results=None,
    )
    assert "execute_shadow_market_breadth" in submitted


def test_orchestrator_submits_sentiment_decay_for_empty_news(monkeypatch):
    """Empty news feed still submits FEAT-018 with an empty article list."""
    from app.agents.orchestrator_agent import OrchestratorAgent

    submitted: list[tuple] = []

    def fake_submit(fn, *args, **kwargs):
        submitted.append((fn.__name__ if hasattr(fn, "__name__") else str(fn), args))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task", fake_submit
    )

    OrchestratorAgent._submit_shadow_candidate_features(
        OrchestratorAgent.__new__(OrchestratorAgent),
        symbol="EMPTY-EQ",
        stock_id=7,
        articles=[],
        bulk_technical_results=None,
    )

    sent = [a for name, a in submitted if name == "execute_shadow_sentiment_decay"]
    assert len(sent) == 1
    assert sent[0][1] == []  # empty articles list
    assert sent[0][3] == 7


def test_empty_articles_persist_neutral_sentiment_decay_telemetry(
    test_engine, db_stock_and_history, shadow_session_factory
):
    """Empty article list produces neutral empty sentiment_decay telemetry (edge)."""
    stock, history = db_stock_and_history
    now = datetime.datetime.now(datetime.timezone.utc)

    execute_shadow_sentiment_decay(
        symbol=stock.symbol, articles=[], scan_time=now, stock_id=stock.id
    )

    updated = _reload_history(shadow_session_factory, history.id)
    sd = updated.shadow_outputs["sentiment_decay"]
    assert sd["article_count"] == 0
    assert sd["aggregate_decayed_score"] == 0.0
    assert sd["articles"] == []
