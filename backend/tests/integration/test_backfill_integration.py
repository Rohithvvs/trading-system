"""Integration tests for taxonomy auto-tagging, backfill, reporting, and queries.

Spec: specs/013-situation-taxonomy-backfill/spec.md
  US1 Automatic Ongoing Tagging
  US2 Controlled Historical Backfill
  US3 Tag Distribution and Analytical Querying
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.analysis import AnalysisHistory, BackfillProgress
from backend.app.models.stock import WatchedStock
from backend.app.schemas.analysis import ArticleItem
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.backfill_service import BackfillService


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------

class MockBacktest:
    def __init__(self):
        self.total_return = 15.5
        self.cagr = 10.2
        self.max_drawdown = 5.0
        self.win_rate = 0.65
        self.profit_factor = 2.1
        self.trade_count = 20
        self.verdict = "PASS"
        self.strategy_name = "EMA50"


class MockRecommendation:
    def __init__(self, action="BUY"):
        self.action = action
        self.confidence = 0.85
        self.summary = "Test BUY signal summary"


class MockSectorOverlay:
    def __init__(self):
        self.mapped_sector = "Energy"
        self.sector_rs_20 = 5.2
        self.sector_close = 100.0
        self.sector_ema20 = 95.0
        self.downgrade_triggered = False
        self.original_action = "BUY"
        self.challenger_action = "BUY"
        self.downgrade_reason = ""


class MockMarketRegime:
    def __init__(self, market_state="BULLISH"):
        self.market_state = market_state
        self.trend_state = "UP"
        self.breadth_state = "STRONG"
        self.volatility_state = "LOW"
        self.new_entry_allowed = True
        self.risk_multiplier = 1.0


async def _get_or_create_stock(db, symbol: str, display: str) -> int:
    stock = (
        await db.scalars(select(WatchedStock).where(WatchedStock.symbol == symbol))
    ).first()
    if not stock:
        stock = WatchedStock(symbol=symbol, display_name=display)
        db.add(stock)
        await db.commit()
        await db.refresh(stock)
    return stock.id


# ===========================================================================
# US1 — Automatic Ongoing Tagging
# ===========================================================================

@pytest.mark.asyncio
async def test_persist_analysis_saves_tags(test_engine):
    """US1 AS1: live persist applies situation tags automatically (FR-001)."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "RELIANCE-EQ", "Reliance")
        agent = OrchestratorAgent(db=db)
        articles = [
            ArticleItem(
                title="Reliance Q1 earnings reports high revenue growth",
                description="earnings and profit",
                source="news",
                url="http://test",
                published_at=datetime.now(timezone.utc),
                sentiment_score=0.8,
            )
        ]

        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=85.0,
            sentiment_score=0.8,
            backtest=MockBacktest(),
            recommendation=MockRecommendation("BUY"),
            sector_overlay=MockSectorOverlay(),
            market_regime=MockMarketRegime(),
            symbol="RELIANCE-EQ",
            articles=articles,
        )

    async with AsyncSessionLocal() as db:
        res = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        assert res is not None
        assert res.situation_tags is not None
        assert "GOOD_NEWS_CATALYST" in res.situation_tags
        assert "EARNINGS_PLAY" in res.situation_tags
        assert "MARKET_REGIME" in res.situation_tags


@pytest.mark.asyncio
async def test_persist_analysis_assigns_unknown_when_symbol_missing(test_engine):
    """US1 AS2 / FR-008: unmatched/missing context → UNKNOWN."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "UNKNOWN-SYM", "Unknown")
        agent = OrchestratorAgent(db=db)
        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=50.0,
            sentiment_score=0.5,
            backtest=MockBacktest(),
            recommendation=MockRecommendation("BUY"),
            sector_overlay=MockSectorOverlay(),
            market_regime=None,
            symbol=None,  # critical field missing
            articles=[],
        )

    async with AsyncSessionLocal() as db:
        res = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        assert res is not None
        assert res.situation_tags == ["UNKNOWN"]


@pytest.mark.asyncio
async def test_persist_analysis_assigns_unknown_when_no_rules_match(test_engine):
    """US1 AS2 / FR-008: BUY with no matching taxonomy rule → UNKNOWN."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "RANGE-EQ", "Range")
        agent = OrchestratorAgent(db=db)
        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=50.0,
            sentiment_score=0.5,
            backtest=MockBacktest(),
            recommendation=MockRecommendation("BUY"),
            sector_overlay=None,
            market_regime=None,
            symbol="RANGE-EQ",
            articles=[],
        )

    async with AsyncSessionLocal() as db:
        res = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        assert res.situation_tags == ["UNKNOWN"]


@pytest.mark.asyncio
async def test_persist_analysis_assigns_range_bound_for_non_buy_no_catalyst(test_engine):
    """RANGE_BOUND applies for non-BUY without catalyst tags."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "RANGE2-EQ", "Range2")
        agent = OrchestratorAgent(db=db)
        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=50.0,
            sentiment_score=0.5,
            backtest=MockBacktest(),
            recommendation=MockRecommendation("SELL"),
            sector_overlay=None,
            market_regime=None,
            symbol="RANGE2-EQ",
            articles=[],
        )

    async with AsyncSessionLocal() as db:
        res = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        assert res.situation_tags == ["RANGE_BOUND"]


@pytest.mark.asyncio
async def test_persist_analysis_bad_news_catalyst(test_engine):
    """US1: SELL + low sentiment tags BAD_NEWS_CATALYST at persist time."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "BAD-EQ", "Bad")
        agent = OrchestratorAgent(db=db)
        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=30.0,
            sentiment_score=0.2,
            backtest=MockBacktest(),
            recommendation=MockRecommendation("SELL"),
            sector_overlay=None,
            market_regime=None,
            symbol="BAD-EQ",
            articles=[],
        )

    async with AsyncSessionLocal() as db:
        res = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        assert res.situation_tags == ["BAD_NEWS_CATALYST"]


# ===========================================================================
# US2 — Controlled Historical Backfill
# ===========================================================================

@pytest.mark.asyncio
async def test_backfill_runs_successfully(test_engine):
    """US2 AS1: backfill tags historical records in controlled batches (FR-004)."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "INFY-EQ", "Infosys")
        for i in range(5):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=50.0,
                    sentiment_score=0.2 if i % 2 == 0 else 0.7,
                    backtest_score=10.0,
                    recommendation="BUY" if i % 2 != 0 else "SELL",
                    confidence=0.8,
                    reasoning="some reasoning",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    job_id = "test-job-1"
    processed_count = await service.run_backfill(
        job_id=job_id,
        batch_size=2,
        delay_seconds=0.01,
        resume=False,
    )
    assert processed_count == 5

    async with AsyncSessionLocal() as db:
        progress = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == job_id)
            )
        ).first()
        assert progress is not None
        assert progress.status == "COMPLETED"
        assert progress.processed_count == 5

        tagged_records = (
            await db.scalars(
                select(AnalysisHistory).where(AnalysisHistory.stock_id == stock_id)
            )
        ).all()
        for rec in tagged_records:
            assert len(rec.situation_tags) > 0
            if rec.recommendation == "BUY" and rec.sentiment_score == 0.7:
                assert "GOOD_NEWS_CATALYST" in rec.situation_tags
            elif rec.recommendation == "SELL" and rec.sentiment_score == 0.2:
                assert "BAD_NEWS_CATALYST" in rec.situation_tags


@pytest.mark.asyncio
async def test_backfill_resumption(test_engine):
    """US2 AS2/AS3: interruption mid-run then resume from progress marker (FR-005)."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "TCS-EQ", "TCS")
        for _ in range(4):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=50.0,
                    sentiment_score=0.5,
                    backtest_score=10.0,
                    recommendation="BUY",
                    confidence=0.8,
                    reasoning="some reasoning",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    job_id = "resume-job"

    count_1 = await service.run_backfill(
        job_id=job_id,
        batch_size=2,
        delay_seconds=0.01,
        resume=False,
        limit=2,
    )
    assert count_1 == 2

    async with AsyncSessionLocal() as db:
        progress = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == job_id)
            )
        ).first()
        assert progress is not None
        assert progress.status == "RUNNING"
        assert progress.processed_count == 2
        cursor_after_partial = progress.last_processed_id
        assert cursor_after_partial > 0

    count_2 = await service.run_backfill(
        job_id=job_id,
        batch_size=2,
        delay_seconds=0.01,
        resume=True,
    )
    assert count_2 == 2

    async with AsyncSessionLocal() as db:
        progress = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == job_id)
            )
        ).first()
        assert progress.status == "COMPLETED"
        assert progress.processed_count == 4
        assert progress.last_processed_id >= cursor_after_partial


@pytest.mark.asyncio
async def test_backfill_keyset_paging_updates_cursor_monotonically(test_engine):
    """FR-005: last_processed_id advances with keyset order and never decreases."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "CURSOR-EQ", "Cursor")
        for _ in range(6):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=50.0,
                    sentiment_score=0.5,
                    backtest_score=10.0,
                    recommendation="BUY",
                    confidence=0.8,
                    reasoning="cursor",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    await service.run_backfill(
        job_id="cursor-job",
        batch_size=2,
        delay_seconds=0.0,
        resume=False,
        limit=2,
    )
    async with AsyncSessionLocal() as db:
        p1 = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == "cursor-job")
            )
        ).first()
        cursor1 = p1.last_processed_id

    await service.run_backfill(
        job_id="cursor-job",
        batch_size=2,
        delay_seconds=0.0,
        resume=True,
        limit=4,  # relative limit is local counter; resume continues from cursor
    )
    async with AsyncSessionLocal() as db:
        p2 = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == "cursor-job")
            )
        ).first()
        assert p2.last_processed_id >= cursor1


@pytest.mark.asyncio
async def test_backfill_does_not_leave_untagged_records(test_engine):
    """SC-001: after full backfill every record has at least one situation tag."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "FULL-EQ", "Full")
        for i in range(8):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=40.0 + i,
                    sentiment_score=0.1 * i,
                    backtest_score=5.0,
                    recommendation="BUY" if i % 3 else "SELL",
                    confidence=0.7,
                    reasoning=f"rec-{i}",
                    situation_tags=[],
                )
            )
        await db.commit()

    await BackfillService().run_backfill(
        job_id="full-tag-job",
        batch_size=3,
        delay_seconds=0.0,
        resume=False,
    )

    async with AsyncSessionLocal() as db:
        records = (
            await db.scalars(
                select(AnalysisHistory).where(AnalysisHistory.stock_id == stock_id)
            )
        ).all()
        assert len(records) == 8
        for rec in records:
            assert rec.situation_tags
            assert len(rec.situation_tags) >= 1


# ===========================================================================
# US3 — Tag Distribution and Analytical Querying
# ===========================================================================

@pytest.mark.asyncio
async def test_write_distribution_report(test_engine, tmp_path):
    """US3 AS1 / FR-006: distribution report written with counts for each tag."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "INFY-EQ", "Infosys")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.7,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="r1",
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
                reasoning="r2",
                situation_tags=["BAD_NEWS_CATALYST"],
            )
        )
        await db.commit()

    service = BackfillService()
    output_path = await service.write_distribution_report(output_dir=str(tmp_path))

    assert Path(output_path).exists()
    content = Path(output_path).read_text(encoding="utf-8")
    assert "GOOD_NEWS_CATALYST" in content
    assert "BAD_NEWS_CATALYST" in content
    assert "Total Recommendations Analysed:" in content
    for tag in (
        "EARNINGS_PLAY",
        "MARKET_REGIME",
        "RANGE_BOUND",
        "UNKNOWN",
    ):
        assert tag in content


@pytest.mark.asyncio
async def test_analytics_query_by_situation_tags(test_engine):
    """US3 AS2 / FR-007: filter recommendations by one or more situation tags."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "INFY-EQ", "Infosys")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.7,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="r1",
                situation_tags=["GOOD_NEWS_CATALYST", "EARNINGS_PLAY"],
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
                reasoning="r2",
                situation_tags=["BAD_NEWS_CATALYST"],
            )
        )
        await db.commit()

        service = AnalyticsService()

        res = await service.query_by_situation_tags(db, tags=["GOOD_NEWS_CATALYST"])
        assert len(res) == 1
        assert "GOOD_NEWS_CATALYST" in res[0].situation_tags

        res = await service.query_by_situation_tags(
            db, tags=["GOOD_NEWS_CATALYST", "EARNINGS_PLAY"]
        )
        assert len(res) == 1

        res = await service.query_by_situation_tags(db, tags=["BAD_NEWS_CATALYST"])
        assert len(res) == 1

        res = await service.query_by_situation_tags(db, tags=["MARKET_REGIME"])
        assert len(res) == 0


@pytest.mark.asyncio
async def test_analytics_compound_filter_tag_and_action(test_engine):
    """US3 AS2: compound filter GOOD_NEWS_CATALYST + BUY (FR-007)."""
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "COMPOUND-EQ", "Compound")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.9,
                reasoning="match",
                situation_tags=["GOOD_NEWS_CATALYST"],
            )
        )
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="SELL",
                confidence=0.9,
                reasoning="wrong-action",
                situation_tags=["GOOD_NEWS_CATALYST"],
            )
        )
        await db.commit()

        service = AnalyticsService()
        res = await service.query_by_situation_tags(
            db, tags=["GOOD_NEWS_CATALYST"], recommendation="BUY"
        )
        assert len(res) == 1
        assert res[0].reasoning == "match"


@pytest.mark.asyncio
async def test_analytics_compound_filter_tag_action_and_date_range(test_engine):
    """US3 AS2 / FR-007: GOOD_NEWS_CATALYST BUY in date window."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, "DATEWIN-EQ", "DateWin")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.9,
                reasoning="in-window",
                situation_tags=["GOOD_NEWS_CATALYST"],
                created_at=now - timedelta(days=30),
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
                confidence=0.9,
                reasoning="out-of-window",
                situation_tags=["GOOD_NEWS_CATALYST"],
                created_at=now - timedelta(days=400),
            )
        )
        await db.commit()

        service = AnalyticsService()
        res = await service.query_by_situation_tags(
            db,
            tags=["GOOD_NEWS_CATALYST"],
            recommendation="BUY",
            start_date=now - timedelta(days=180),
            end_date=now,
        )
        assert len(res) == 1
        assert res[0].reasoning == "in-window"


@pytest.mark.asyncio
async def test_live_persist_and_backfill_use_same_classifier_outcomes(test_engine):
    """FR-003: live tagging and backfill produce identical tags for same inputs."""
    symbol = "UNIFORM-EQ"
    sentiment = 0.75
    action = "BUY"

    # Live path
    async with AsyncSessionLocal() as db:
        stock_id = await _get_or_create_stock(db, symbol, "Uniform")
        agent = OrchestratorAgent(db=db)
        await agent._persist_analysis(
            stock_id=stock_id,
            mode="swing",
            technical_score=70.0,
            sentiment_score=sentiment,
            backtest=MockBacktest(),
            recommendation=MockRecommendation(action),
            sector_overlay=None,
            market_regime=None,
            symbol=symbol,
            articles=[],
        )

    async with AsyncSessionLocal() as db:
        live = (
            await db.scalars(
                select(AnalysisHistory)
                .where(AnalysisHistory.stock_id == stock_id)
                .order_by(AnalysisHistory.id.desc())
                .limit(1)
            )
        ).first()
        live_tags = list(live.situation_tags)

        # Historical twin (untagged) for backfill path
        twin = AnalysisHistory(
            stock_id=stock_id,
            mode="swing",
            technical_score=70.0,
            sentiment_score=sentiment,
            backtest_score=15.5,
            recommendation=action,
            confidence=0.85,
            reasoning="twin",
            situation_tags=[],
        )
        db.add(twin)
        await db.commit()
        twin_id = twin.id

    await BackfillService().run_backfill(
        job_id="uniform-job",
        batch_size=50,
        delay_seconds=0.0,
        resume=False,
    )

    async with AsyncSessionLocal() as db:
        twin_rec = await db.get(AnalysisHistory, twin_id)
        assert set(twin_rec.situation_tags) == set(live_tags)
