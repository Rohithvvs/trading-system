"""Unit tests for situation-tag querying and CLI argument surface.

Spec: specs/013-situation-taxonomy-backfill/spec.md
  FR-006 Distribution CLI
  FR-007 Situation Filtering
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.governance.experiment_cli import _parse_args
from backend.app.governance.router import get_route, list_routes
from backend.app.models.analysis import AnalysisHistory
from backend.app.models.stock import WatchedStock
from backend.app.services.analytics_service import AnalyticsService


# ---------------------------------------------------------------------------
# CLI surface (FR-004, FR-006)
# ---------------------------------------------------------------------------

def test_backfill_cli_parses_required_and_optional_args():
    args = _parse_args(
        [
            "backfill",
            "--job-id",
            "job-42",
            "--batch-size",
            "50",
            "--delay",
            "0.1",
            "--resume",
        ]
    )
    assert args.command == "backfill"
    assert args.job_id == "job-42"
    assert args.batch_size == 50
    assert args.delay == 0.1
    assert args.resume is True


def test_backfill_cli_defaults():
    args = _parse_args(["backfill", "--job-id", "j1"])
    assert args.batch_size == 100
    assert args.delay == 0.5
    assert args.resume is False


def test_taxonomy_report_cli_parses_output_dir():
    args = _parse_args(["taxonomy-report", "--output-dir", "/tmp/reports"])
    assert args.command == "taxonomy-report"
    assert args.output_dir == "/tmp/reports"


def test_taxonomy_report_cli_output_dir_optional():
    args = _parse_args(["taxonomy-report"])
    assert args.command == "taxonomy-report"
    assert args.output_dir is None


def test_governance_routes_include_backfill_and_taxonomy_report():
    routes = list_routes()
    assert "experiment.backfill" in routes
    assert "experiment.backfill_pause" in routes
    assert "experiment.taxonomy_report" in routes
    assert "experiment.taxonomy_query" in routes
    assert get_route("experiment.backfill") == (
        "app.governance.experiment_cli:experiment_cli backfill"
    )
    assert get_route("experiment.backfill_pause") == (
        "app.governance.experiment_cli:experiment_cli backfill-pause"
    )
    assert get_route("experiment.taxonomy_report") == (
        "app.governance.experiment_cli:experiment_cli taxonomy-report"
    )
    assert get_route("experiment.taxonomy_query") == (
        "app.governance.experiment_cli:experiment_cli taxonomy-query"
    )


def test_backfill_pause_cli_parses():
    args = _parse_args(["backfill-pause", "--job-id", "job-9"])
    assert args.command == "backfill-pause"
    assert args.job_id == "job-9"


def test_taxonomy_query_cli_parses_filters():
    args = _parse_args(
        [
            "taxonomy-query",
            "--tags",
            "GOOD_NEWS_CATALYST,EARNINGS_PLAY",
            "--recommendation",
            "BUY",
            "--start",
            "2024-01-01T00:00:00",
            "--end",
            "2024-06-30T23:59:59",
            "--limit",
            "25",
        ]
    )
    assert args.command == "taxonomy-query"
    assert args.tags == "GOOD_NEWS_CATALYST,EARNINGS_PLAY"
    assert args.recommendation == "BUY"
    assert args.start == "2024-01-01T00:00:00"
    assert args.end == "2024-06-30T23:59:59"
    assert args.limit == 25


def test_require_taxonomy_admin_blocks_when_token_mismatch(monkeypatch):
    from backend.app.governance.experiment_cli import _require_taxonomy_admin

    monkeypatch.setenv("API_KEY", "secret-admin")
    monkeypatch.delenv("GOVERNANCE_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("GOVERNANCE_CLI_TOKEN", raising=False)
    args = _parse_args(["backfill", "--job-id", "j1", "--admin-token", "wrong"])
    with pytest.raises(SystemExit) as exc:
        _require_taxonomy_admin(args)
    assert exc.value.code == 1


def test_require_taxonomy_admin_allows_matching_token(monkeypatch):
    from backend.app.governance.experiment_cli import _require_taxonomy_admin

    monkeypatch.setenv("API_KEY", "secret-admin")
    args = _parse_args(["taxonomy-report", "--admin-token", "secret-admin"])
    _require_taxonomy_admin(args)  # does not raise


# ---------------------------------------------------------------------------
# FR-007: filtering by tags + recommendation
# ---------------------------------------------------------------------------

async def _seed_stock(db, symbol: str) -> int:
    stock = WatchedStock(symbol=symbol, display_name=symbol)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock.id


@pytest.mark.asyncio
async def test_query_filters_by_tag_and_recommendation(test_engine):
    """FR-007: compound filter by situation tag and action."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _seed_stock(db, "FILTER-EQ")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="buy-good",
                situation_tags=["GOOD_NEWS_CATALYST"],
            )
        )
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.2,
                backtest_score=10.0,
                recommendation="SELL",
                confidence=0.8,
                reasoning="sell-bad",
                situation_tags=["GOOD_NEWS_CATALYST"],  # unlikely but tests filter
            )
        )
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="buy-earn",
                situation_tags=["EARNINGS_PLAY"],
            )
        )
        await db.commit()

        service = AnalyticsService()
        results = await service.query_by_situation_tags(
            db, tags=["GOOD_NEWS_CATALYST"], recommendation="BUY"
        )
        assert len(results) == 1
        assert results[0].recommendation == "BUY"
        assert "GOOD_NEWS_CATALYST" in results[0].situation_tags


@pytest.mark.asyncio
async def test_query_limit_is_respected(test_engine):
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _seed_stock(db, "LIMIT-EQ")
        for i in range(5):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=50.0,
                    sentiment_score=0.8,
                    backtest_score=10.0,
                    recommendation="BUY",
                    confidence=0.8,
                    reasoning=f"r{i}",
                    situation_tags=["RANGE_BOUND"],
                )
            )
        await db.commit()

        service = AnalyticsService()
        results = await service.query_by_situation_tags(
            db, tags=["RANGE_BOUND"], limit=2
        )
        assert len(results) == 2


@pytest.mark.asyncio
async def test_query_empty_tags_list_does_not_crash(test_engine):
    """Failure path: empty tag filter should not raise."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _seed_stock(db, "EMPTYTAG-EQ")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="r",
                situation_tags=["RANGE_BOUND"],
            )
        )
        await db.commit()

        service = AnalyticsService()
        # Empty tag list: LIKE conditions none on sqlite; may return all or none
        # depending on dialect handling — must not raise.
        results = await service.query_by_situation_tags(db, tags=[])
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_filters_by_date_range(test_engine):
    """FR-007: filter by situation tag + created_at date range."""
    from backend.app.db.session import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=200)
    recent = now - timedelta(days=10)

    async with AsyncSessionLocal() as db:
        stock_id = await _seed_stock(db, "DATE-EQ")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="old-good",
                situation_tags=["GOOD_NEWS_CATALYST"],
                created_at=old,
            )
        )
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="recent-good",
                situation_tags=["GOOD_NEWS_CATALYST"],
                created_at=recent,
            )
        )
        await db.commit()

        service = AnalyticsService()
        # Last 6 months only
        start = now - timedelta(days=180)
        results = await service.query_by_situation_tags(
            db,
            tags=["GOOD_NEWS_CATALYST"],
            recommendation="BUY",
            start_date=start,
            end_date=now,
        )
        assert len(results) == 1
        assert results[0].reasoning == "recent-good"

        # Explicit window covering both
        all_results = await service.query_by_situation_tags(
            db,
            tags=["GOOD_NEWS_CATALYST"],
            start_date=old - timedelta(days=1),
            end_date=now,
        )
        assert len(all_results) == 2


@pytest.mark.asyncio
async def test_query_does_not_false_match_tag_substrings(test_engine):
    """L4: SQLite filter must not match substring-overlapping tag names."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _seed_stock(db, "SUBSTR-EQ")
        # Store a tag that would false-match a naive LIKE %NEWS% style filter
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="good-only",
                situation_tags=["GOOD_NEWS_CATALYST"],
            )
        )
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.2,
                backtest_score=10.0,
                recommendation="SELL",
                confidence=0.8,
                reasoning="bad-only",
                situation_tags=["BAD_NEWS_CATALYST"],
            )
        )
        await db.commit()

        service = AnalyticsService()
        good = await service.query_by_situation_tags(db, tags=["GOOD_NEWS_CATALYST"])
        assert len(good) == 1
        assert good[0].reasoning == "good-only"

        bad = await service.query_by_situation_tags(db, tags=["BAD_NEWS_CATALYST"])
        assert len(bad) == 1
        assert bad[0].reasoning == "bad-only"

        # Querying a non-existent exact tag must not match either row
        none = await service.query_by_situation_tags(db, tags=["NEWS_CATALYST"])
        assert none == []
