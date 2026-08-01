"""Integration tests for FEAT-014 shadow news deduplication.

Spec source: specs/011-news-deduplication/spec.md
Covers FR-007 through FR-011, SC-002, SC-003, and shadow failure isolation.
"""
from __future__ import annotations

import datetime
import json
import logging
from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from app.agents.news_analysis_agent import NewsAnalysisAgent
from app.config import settings
from app.models import AnalysisHistory, ArticleDedupLog, WatchedStock
from app.schemas.analysis import ArticleItem
from app.services import shadow_executor as shadow_executor_module
from app.services.shadow_executor import ShadowThreadPool, execute_shadow_news_dedup


def _create_article(
    title: str,
    published_at: datetime.datetime,
    source: str = "Unknown",
    url: str = "http://example.com/art",
) -> ArticleItem:
    return ArticleItem(
        title=title,
        published_at=published_at,
        source=source,
        url=url,
        description="test description",
        sentiment_score=0.5,
    )


def _duplicate_article_set() -> list[ArticleItem]:
    base_time = datetime.datetime(2023, 6, 1, 10, 0, 0)
    return [
        _create_article("AAPL Earnings Beat", base_time, source="CNBC", url="http://example.com/1"),
        _create_article(
            "AAPL Earnings Beat",
            base_time + datetime.timedelta(minutes=5),
            source="MarketWatch",
            url="http://example.com/2",
        ),
        _create_article("TSLA Product Launch", base_time, source="Reuters", url="http://example.com/3"),
    ]


@pytest.fixture
def enable_shadow_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "shadow_mode_enabled", True)
    monkeypatch.setattr(settings, "shadow_mode_stage", "SHADOW")


@pytest.fixture
def disable_shadow_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "shadow_mode_enabled", False)
    monkeypatch.setattr(settings, "shadow_mode_stage", "OFF")


@pytest.fixture
def mock_news_and_sentiment(monkeypatch) -> list[ArticleItem]:
    articles = _duplicate_article_set()
    monkeypatch.setattr(
        "app.services.news_service.NewsService.fetch_recent_news",
        MagicMock(return_value=articles),
    )
    monkeypatch.setattr(
        "app.services.sentiment_service.SentimentService.summarize",
        MagicMock(return_value=(0.5, "positive", "mocked summary")),
    )
    return articles


@pytest.fixture
def shadow_db(db_session, test_engine, monkeypatch):
    """Route SessionLocal through the SQLite test engine and seed baseline rows."""
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(shadow_executor_module, "SessionLocal", TestingSessionLocal)
    # Avoid multi-second history retries in unit-speed integration tests when history exists.
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_DELAY_SECONDS", 0.01)

    stock = WatchedStock(symbol="RELIANCE-EQ", display_name="Reliance Industries")
    db_session.add(stock)
    db_session.flush()

    history = AnalysisHistory(
        stock_id=stock.id,
        mode="swing",
        technical_score=50.0,
        sentiment_score=0.5,
        backtest_score=50.0,
        recommendation="BUY",
        confidence=0.8,
        reasoning="test baseline",
        shadow_outputs=None,
    )
    db_session.add(history)
    db_session.commit()

    return {
        "stock": stock,
        "history": history,
        "session_factory": TestingSessionLocal,
    }


# ---------------------------------------------------------------------------
# Shadow runner: audit log + telemetry (FR-009, FR-010, SC-003)
# ---------------------------------------------------------------------------


def test_execute_shadow_writes_audit_log_and_telemetry(shadow_db) -> None:
    """FR-009 / FR-010: removed duplicates logged; shadow_outputs telemetry updated via ORM."""
    articles = _duplicate_article_set()

    execute_shadow_news_dedup("RELIANCE-EQ", articles)

    session = shadow_db["session_factory"]()
    try:
        logs = (
            session.query(ArticleDedupLog)
            .filter(ArticleDedupLog.symbol == "RELIANCE-EQ")
            .all()
        )
        assert len(logs) == 1
        entry = logs[0]
        assert entry.kept_id == "http://example.com/1"
        assert entry.deduplicated_id == "http://example.com/2"
        assert entry.kept_title == "AAPL Earnings Beat"
        assert entry.deduplicated_title == "AAPL Earnings Beat"
        assert entry.similarity >= 3.0
        assert "Duplicate" in entry.reason
        assert "window" in entry.reason.lower() or "4h" in entry.reason.lower()

        # Model maps to FR-009 table name
        assert ArticleDedupLog.__tablename__ == "news_deduplication_audit"

        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        assert hist is not None
        outputs = hist.shadow_outputs
        if isinstance(outputs, str):
            outputs = json.loads(outputs)
        assert outputs is not None
        assert "news_dedup" in outputs
        stats = outputs["news_dedup"]
        assert stats["original_news_count"] == 3
        assert stats["kept_news_count"] == 2
        assert stats["removed_news_count"] == 1
        assert stats["original_news_count"] - stats["kept_news_count"] == stats["removed_news_count"]
        assert "executed_at" in stats
        # Flat FR-010 mirrors
        assert outputs["original_news_count"] == 3
        assert outputs["kept_news_count"] == 2
    finally:
        session.close()


def test_execute_shadow_empty_articles_is_noop(shadow_db) -> None:
    """Edge: empty article list returns without DB writes or exceptions."""
    execute_shadow_news_dedup("RELIANCE-EQ", [])

    session = shadow_db["session_factory"]()
    try:
        assert session.query(ArticleDedupLog).count() == 0
        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        assert hist.shadow_outputs is None
    finally:
        session.close()


def test_execute_shadow_no_duplicates_still_writes_telemetry(shadow_db) -> None:
    """FR-010: telemetry is written even when no articles are removed."""
    base = datetime.datetime(2023, 6, 1, 10, 0, 0)
    articles = [
        _create_article("Oil Prices Surge Globally", base, url="http://example.com/a"),
        _create_article("Bank Rate Decision Tomorrow", base, url="http://example.com/b"),
    ]

    execute_shadow_news_dedup("RELIANCE-EQ", articles)

    session = shadow_db["session_factory"]()
    try:
        assert session.query(ArticleDedupLog).count() == 0
        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        outputs = hist.shadow_outputs
        if isinstance(outputs, str):
            outputs = json.loads(outputs)
        assert outputs["news_dedup"]["original_news_count"] == 2
        assert outputs["news_dedup"]["kept_news_count"] == 2
        assert outputs["news_dedup"]["removed_news_count"] == 0
    finally:
        session.close()


def test_execute_shadow_merges_into_existing_shadow_outputs(shadow_db) -> None:
    """Telemetry merges under news_dedup without dropping prior shadow keys."""
    session = shadow_db["session_factory"]()
    try:
        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        hist.shadow_outputs = {"other_feature": {"status": "ok"}}
        session.commit()
    finally:
        session.close()

    execute_shadow_news_dedup("RELIANCE-EQ", _duplicate_article_set())

    session = shadow_db["session_factory"]()
    try:
        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        outputs = hist.shadow_outputs
        if isinstance(outputs, str):
            outputs = json.loads(outputs)
        assert outputs["other_feature"]["status"] == "ok"
        assert "news_dedup" in outputs
    finally:
        session.close()


def test_execute_shadow_does_not_mutate_caller_articles(shadow_db) -> None:
    """FR-007 / FR-008: shadow deep-copies input; caller list remains intact."""
    articles = _duplicate_article_set()
    original_urls = [a.url for a in articles]
    original_len = len(articles)

    execute_shadow_news_dedup("RELIANCE-EQ", articles)

    assert len(articles) == original_len
    assert [a.url for a in articles] == original_urls


def test_execute_shadow_audit_survives_when_stock_missing(db_session, test_engine, monkeypatch) -> None:
    """When watched stock is missing, audit logs still commit; telemetry is skipped."""
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(shadow_executor_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_DELAY_SECONDS", 0)

    execute_shadow_news_dedup("MISSING-EQ", _duplicate_article_set())

    session = TestingSessionLocal()
    try:
        logs = session.query(ArticleDedupLog).filter_by(symbol="MISSING-EQ").all()
        assert len(logs) == 1
    finally:
        session.close()


def test_execute_shadow_retries_until_history_appears(
    db_session, test_engine, monkeypatch
) -> None:
    """C2: telemetry attaches after AnalysisHistory is created (orchestrator lag)."""
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(shadow_executor_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_ATTEMPTS", 5)
    monkeypatch.setattr(shadow_executor_module, "_HISTORY_RETRY_DELAY_SECONDS", 0.05)

    stock = WatchedStock(symbol="RELIANCE-EQ", display_name="Reliance")
    db_session.add(stock)
    db_session.commit()
    stock_id = stock.id

    attempts = {"n": 0}
    real_load = shadow_executor_module._load_latest_history

    def load_then_create(session, sid, not_before=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            # First attempt: no history yet (simulate race)
            return None
        if attempts["n"] == 2:
            # Create history as orchestrator would, then return it
            hist = AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=50.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="late persist",
            )
            session.add(hist)
            session.commit()
            session.refresh(hist)
            return hist
        return real_load(session, sid, not_before=not_before)

    monkeypatch.setattr(shadow_executor_module, "_load_latest_history", load_then_create)

    execute_shadow_news_dedup("RELIANCE-EQ", _duplicate_article_set())

    session = TestingSessionLocal()
    try:
        assert session.query(ArticleDedupLog).count() == 1
        hist = (
            session.query(AnalysisHistory)
            .filter_by(stock_id=stock_id)
            .order_by(AnalysisHistory.created_at.desc())
            .first()
        )
        assert hist is not None
        assert hist.shadow_outputs is not None
        assert hist.shadow_outputs["news_dedup"]["removed_news_count"] == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Failure isolation (FR-011)
# ---------------------------------------------------------------------------


def test_shadow_db_failure_logs_warning_and_does_not_raise(monkeypatch, caplog) -> None:
    """FR-011: database failures during shadow writes are caught and logged as warnings."""

    def boom_session():
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(shadow_executor_module, "SessionLocal", boom_session)

    with caplog.at_level(logging.WARNING, logger="app.shadow_executor"):
        execute_shadow_news_dedup("RELIANCE-EQ", _duplicate_article_set())

    assert any("failed" in r.message.lower() or "Shadow" in r.message for r in caplog.records)


def test_shadow_dedup_exception_logs_warning_and_does_not_raise(monkeypatch, caplog) -> None:
    """FR-011: exceptions inside pure dedup path are swallowed with a warning."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("Mock shadow database explosion")

    monkeypatch.setattr(shadow_executor_module, "deduplicate_articles", boom)

    with caplog.at_level(logging.WARNING, logger="app.shadow_executor"):
        execute_shadow_news_dedup("RELIANCE-EQ", _duplicate_article_set())

    assert any("failed" in r.message.lower() for r in caplog.records)


def test_audit_commit_independent_of_telemetry_failure(
    shadow_db, monkeypatch, caplog
) -> None:
    """H3: audit rows remain when telemetry path fails."""

    def exploding_telemetry(*_args, **_kwargs):
        raise RuntimeError("telemetry boom")

    monkeypatch.setattr(
        shadow_executor_module, "_persist_shadow_telemetry", exploding_telemetry
    )

    with caplog.at_level(logging.WARNING, logger="app.shadow_executor"):
        execute_shadow_news_dedup("RELIANCE-EQ", _duplicate_article_set())

    session = shadow_db["session_factory"]()
    try:
        assert session.query(ArticleDedupLog).count() == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Agent integration: production path isolation (FR-007, FR-008, SC-002)
# ---------------------------------------------------------------------------


def test_news_agent_production_path_uses_full_unfiltered_list(
    enable_shadow_mode, mock_news_and_sentiment, monkeypatch
) -> None:
    """FR-008 / US2 SC1: production sentiment uses full unfiltered article list."""
    submitted: list[tuple] = []

    def capture_submit(fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))
        fut: Future = Future()
        fut.set_result(None)
        return fut

    monkeypatch.setattr(
        ShadowThreadPool,
        "submit_task",
        classmethod(lambda cls, fn, *a, **k: capture_submit(fn, *a, **k)),
    )

    agent = NewsAnalysisAgent()
    articles, score, label, summary = agent.run("RELIANCE-EQ")

    assert len(articles) == 3
    assert score == 0.5
    assert label == "positive"
    assert summary == "mocked summary"
    assert len(submitted) >= 1
    fn, args, _kwargs = submitted[0]
    assert fn is execute_shadow_news_dedup
    assert args[0] == "RELIANCE-EQ"
    assert len(args[1]) == 3


def test_news_agent_shadow_disabled_does_not_submit(
    disable_shadow_mode, mock_news_and_sentiment, monkeypatch
) -> None:
    """When shadow hook is disabled, no shadow task is submitted."""
    submit_mock = MagicMock()
    monkeypatch.setattr(ShadowThreadPool, "submit_task", submit_mock)

    agent = NewsAnalysisAgent()
    articles, score, _label, _summary = agent.run("RELIANCE-EQ")

    assert len(articles) == 3
    assert score == 0.5
    submit_mock.assert_not_called()


def test_news_agent_stage_off_does_not_submit(
    mock_news_and_sentiment, monkeypatch
) -> None:
    """H2: shadow_mode_enabled=True but stage=OFF must not submit news dedup."""
    monkeypatch.setattr(settings, "shadow_mode_enabled", True)
    monkeypatch.setattr(settings, "shadow_mode_stage", "OFF")
    submit_mock = MagicMock()
    monkeypatch.setattr(ShadowThreadPool, "submit_task", submit_mock)

    agent = NewsAnalysisAgent()
    agent.run("RELIANCE-EQ")

    submit_mock.assert_not_called()


def test_news_agent_shadow_crash_does_not_affect_production(
    enable_shadow_mode, mock_news_and_sentiment, monkeypatch
) -> None:
    """FR-011 / SC-002: shadow runner exception must not alter production results."""

    def exploding_runner(*_args, **_kwargs):
        raise RuntimeError("shadow boom")

    def fail_on_submit(cls, fn, *args, **kwargs):
        try:
            exploding_runner(*args, **kwargs)
        except Exception as exc:
            logging.getLogger("app.shadow_executor").warning("Failed to submit: %s", exc)
            return None
        fut: Future = Future()
        fut.set_result(None)
        return fut

    monkeypatch.setattr(ShadowThreadPool, "submit_task", classmethod(fail_on_submit))

    agent = NewsAnalysisAgent()
    try:
        articles, score, label, summary = agent.run("RELIANCE-EQ")
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"Shadow crash leaked to production: {exc}")

    assert len(articles) == 3
    assert score == 0.5
    assert label == "positive"


def test_news_agent_empty_news_skips_shadow(enable_shadow_mode, monkeypatch) -> None:
    """No articles → production short-circuits before shadow submission."""
    monkeypatch.setattr(
        "app.services.news_service.NewsService.fetch_recent_news",
        MagicMock(return_value=[]),
    )
    submit_mock = MagicMock()
    monkeypatch.setattr(ShadowThreadPool, "submit_task", submit_mock)

    agent = NewsAnalysisAgent()
    articles, score, label, summary = agent.run("RELIANCE-EQ")

    assert articles == []
    assert score == 0.5
    assert label == "Neutral"
    submit_mock.assert_not_called()


def test_shadow_thread_pool_submit_failure_is_swallowed(monkeypatch, caplog) -> None:
    """ShadowThreadPool.submit_task logs a warning and returns None on executor failure."""

    class BoomExecutor:
        def submit(self, *_args, **_kwargs):
            raise RuntimeError("pool full")

    monkeypatch.setattr(ShadowThreadPool, "_executor", BoomExecutor())

    with caplog.at_level(logging.WARNING, logger="app.shadow_executor"):
        result = ShadowThreadPool.submit_task(lambda: None)

    assert result is None
    assert any("Failed to submit" in r.message for r in caplog.records)


def test_end_to_end_agent_shadow_persists_logs(
    enable_shadow_mode,
    mock_news_and_sentiment,
    shadow_db,
    monkeypatch,
) -> None:
    """US2 independent test: agent run with shadow enabled persists audit + telemetry."""

    def sync_submit(cls, fn, *args, **kwargs):
        fn(*args, **kwargs)
        fut: Future = Future()
        fut.set_result(None)
        return fut

    monkeypatch.setattr(ShadowThreadPool, "submit_task", classmethod(sync_submit))

    agent = NewsAnalysisAgent()
    articles, score, _label, _summary = agent.run("RELIANCE-EQ")

    assert len(articles) == 3
    assert score == 0.5

    session = shadow_db["session_factory"]()
    try:
        logs = session.query(ArticleDedupLog).filter_by(symbol="RELIANCE-EQ").all()
        assert len(logs) == 1
        assert logs[0].kept_id == "http://example.com/1"
        assert logs[0].deduplicated_id == "http://example.com/2"

        hist = session.get(AnalysisHistory, shadow_db["history"].id)
        outputs = hist.shadow_outputs
        if isinstance(outputs, str):
            outputs = json.loads(outputs)
        assert outputs["news_dedup"]["original_news_count"] == 3
        assert outputs["news_dedup"]["kept_news_count"] == 2
    finally:
        session.close()
