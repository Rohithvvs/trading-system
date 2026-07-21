"""Unit/service tests for BackfillService batching, resumption, and reporting.

Spec: specs/013-situation-taxonomy-backfill/spec.md
  FR-004 Controlled Batch Backfill
  FR-005 Resumability
  FR-006 Distribution Reporting
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.analysis import AnalysisHistory, BackfillProgress
from backend.app.models.stock import WatchedStock
from backend.app.services.backfill_service import BackfillService


async def _ensure_stock(db, symbol: str, display: str) -> int:
    stock = (await db.scalars(select(WatchedStock).where(WatchedStock.symbol == symbol))).first()
    if not stock:
        stock = WatchedStock(symbol=symbol, display_name=display)
        db.add(stock)
        await db.commit()
        await db.refresh(stock)
    return stock.id


@pytest.mark.asyncio
async def test_backfill_empty_dataset_completes(test_engine):
    """FR-004: empty history processes zero records and marks job COMPLETED."""
    service = BackfillService()
    processed = await service.run_backfill(
        job_id="empty-job",
        batch_size=10,
        delay_seconds=0.0,
        resume=False,
    )
    assert processed == 0

    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        progress = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == "empty-job")
            )
        ).first()
        assert progress is not None
        assert progress.processed_count == 0
        assert progress.total_count == 0
        assert progress.status == "COMPLETED"


@pytest.mark.asyncio
async def test_backfill_completed_job_is_idempotent_on_resume(test_engine):
    """FR-005: resuming an already COMPLETED job is a no-op (returns 0)."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "HDFC-EQ", "HDFC")
        for _ in range(3):
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
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    first = await service.run_backfill(
        job_id="done-job", batch_size=50, delay_seconds=0.0, resume=False
    )
    assert first == 3

    second = await service.run_backfill(
        job_id="done-job", batch_size=50, delay_seconds=0.0, resume=True
    )
    assert second == 0


@pytest.mark.asyncio
async def test_backfill_assigns_unknown_when_recommendation_missing(test_engine):
    """Edge case: incomplete historical record → UNKNOWN, batch continues."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "SBIN-EQ", "SBI")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=10.0,
                recommendation="",  # incomplete
                confidence=0.8,
                reasoning="incomplete",
                situation_tags=[],
            )
        )
        await db.commit()

    service = BackfillService()
    processed = await service.run_backfill(
        job_id="unknown-job",
        batch_size=10,
        delay_seconds=0.0,
        resume=False,
    )
    assert processed == 1

    async with AsyncSessionLocal() as db:
        rec = (await db.scalars(select(AnalysisHistory))).first()
        assert rec is not None
        assert rec.situation_tags == ["UNKNOWN"]


@pytest.mark.asyncio
async def test_backfill_uses_market_state_for_regime_tag(test_engine):
    """Backfill reuses persisted market_state for MARKET_REGIME (FR-003 uniformity)."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "ITC-EQ", "ITC")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="regime",
                market_state="BULLISH",
                situation_tags=[],
            )
        )
        await db.commit()

    service = BackfillService()
    await service.run_backfill(
        job_id="regime-job", batch_size=10, delay_seconds=0.0, resume=False
    )

    async with AsyncSessionLocal() as db:
        rec = (await db.scalars(select(AnalysisHistory))).first()
        assert "MARKET_REGIME" in rec.situation_tags
        assert "RANGE_BOUND" not in rec.situation_tags


@pytest.mark.asyncio
async def test_backfill_throttles_between_batches(test_engine):
    """FR-004: delay is applied between batches to release locks."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "WIPRO-EQ", "Wipro")
        for _ in range(5):
            db.add(
                AnalysisHistory(
                    stock_id=stock_id,
                    mode="swing",
                    technical_score=50.0,
                    sentiment_score=0.5,
                    backtest_score=10.0,
                    recommendation="BUY",
                    confidence=0.8,
                    reasoning="throttle",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    with patch(
        "backend.app.services.backfill_service.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        processed = await service.run_backfill(
            job_id="throttle-job",
            batch_size=2,
            delay_seconds=0.25,
            resume=False,
        )
        assert processed == 5
        # 5 records / batch 2 → batches, sleep between non-final batches
        assert mock_sleep.await_count >= 1
        mock_sleep.assert_awaited_with(0.25)


@pytest.mark.asyncio
async def test_distribution_report_empty_dataset(test_engine, tmp_path):
    """FR-006: empty dataset report still produces valid markdown structure."""
    service = BackfillService()
    path = await service.write_distribution_report(output_dir=str(tmp_path))
    assert Path(path).name.startswith("taxonomy_distribution_")
    assert Path(path).name.endswith(".md")
    assert Path(path).name != "taxonomy_distribution_report.md"
    # Latest stable pointer is also written
    assert (tmp_path / "taxonomy_distribution_report.md").exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "Total Recommendations Analysed: 0" in content
    assert "SC-004 Health Status: N/A" in content
    for tag in (
        "GOOD_NEWS_CATALYST",
        "BAD_NEWS_CATALYST",
        "EARNINGS_PLAY",
        "MARKET_REGIME",
        "RANGE_BOUND",
        "UNKNOWN",
    ):
        assert tag in content


@pytest.mark.asyncio
async def test_distribution_report_counts_and_percentages(test_engine, tmp_path):
    """FR-006: counts and percentage share are correct for multi-tag records."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "AXIS-EQ", "Axis")
        # Two tags on one record → each tag counted once for that occurrence
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.8,
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
        # Empty tags counted as UNKNOWN
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="r3",
                situation_tags=[],
            )
        )
        await db.commit()

    service = BackfillService()
    path = await service.write_distribution_report(output_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")

    assert "Total Recommendations Analysed: 3" in content
    assert "| GOOD_NEWS_CATALYST | 1 |" in content
    assert "| EARNINGS_PLAY | 1 |" in content
    assert "| BAD_NEWS_CATALYST | 1 |" in content
    assert "| UNKNOWN | 1 |" in content
    # 1/3 ≈ 33.33%
    assert "33.33%" in content
    # UNKNOWN 33% > 15% → SC-004 should flag attention
    assert "SC-004 Health Status: NEEDS_ATTENTION" in content
    assert "UNKNOWN" in content and "15%" in content


@pytest.mark.asyncio
async def test_fresh_restart_resets_progress(test_engine):
    """resume=False deletes prior progress and starts from the beginning."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "MARUTI-EQ", "Maruti")
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
                    reasoning="restart",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    partial = await service.run_backfill(
        job_id="restart-job",
        batch_size=2,
        delay_seconds=0.0,
        resume=False,
        limit=2,
    )
    assert partial == 2

    # Full restart (not resume) re-processes from id cursor 0
    full = await service.run_backfill(
        job_id="restart-job",
        batch_size=10,
        delay_seconds=0.0,
        resume=False,
    )
    assert full == 4

    async with AsyncSessionLocal() as db:
        progress = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.job_id == "restart-job")
            )
        ).first()
        assert progress.status == "COMPLETED"
        assert progress.processed_count == 4


@pytest.mark.asyncio
async def test_progress_updated_at_is_set_on_completion(test_engine):
    """L5: updated_at is written explicitly on progress mutations."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "UPD-EQ", "Updated")
        db.add(
            AnalysisHistory(
                stock_id=stock_id,
                mode="swing",
                technical_score=50.0,
                sentiment_score=0.5,
                backtest_score=10.0,
                recommendation="BUY",
                confidence=0.8,
                reasoning="upd",
                situation_tags=[],
            )
        )
        await db.commit()

    service = BackfillService()
    await service.run_backfill(
        job_id="updated-at-job",
        batch_size=10,
        delay_seconds=0.0,
        resume=False,
    )
    progress = await service.get_job_progress("updated-at-job")
    assert progress is not None
    assert progress.status == "COMPLETED"
    assert progress.updated_at is not None
    assert progress.started_at is not None


@pytest.mark.asyncio
async def test_pause_backfill_sets_paused_status(test_engine):
    """M3: pause_backfill flips RUNNING job to PAUSED."""
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stock_id = await _ensure_stock(db, "PAUSE-EQ", "Pause")
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
                    reasoning="pause",
                    situation_tags=[],
                )
            )
        await db.commit()

    service = BackfillService()
    await service.run_backfill(
        job_id="pause-job",
        batch_size=2,
        delay_seconds=0.0,
        resume=False,
        limit=2,
    )
    progress = await service.pause_backfill("pause-job")
    assert progress.status == "PAUSED"
    assert progress.processed_count == 2

    # Resume continues from cursor
    more = await service.run_backfill(
        job_id="pause-job",
        batch_size=10,
        delay_seconds=0.0,
        resume=True,
    )
    assert more == 4
    final = await service.get_job_progress("pause-job")
    assert final.status == "COMPLETED"
    assert final.processed_count == 6
