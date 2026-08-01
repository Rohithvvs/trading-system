"""Rollback + failure-path tests for SCAN_RESULT_MINIMAL_WRITES (User Story 3).

Acceptance coverage:
- US3-AS1: Toggling flag OFF restores legacy multi-table writes without restart.
- SC-005: subsequent scan under OFF writes snapshots again.
- Edge: feature-flag evaluation error defaults to legacy mode.
- Regression: ON → OFF → ON transitions leave DB consistent.
"""
from __future__ import annotations

import os

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.market_data import LatestScanResult, ScanSnapshot, ScanSnapshotRecord
from app.schemas import (
    FinalRecommendation,
    FullAnalysisResponse,
    RankingsResponse,
    RecommendationReasoning,
    ScreenerResponse,
    StockAnalysisResult,
)
from app.services.latest_scan_service import LatestScanService


def _response(symbol: str = "TCS") -> ScreenerResponse:
    dummy_item = StockAnalysisResult(
        symbol=symbol,
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        fundamental=None,
        backtests=[],
        recommendation=FinalRecommendation(
            action="BUY",
            confidence=0.98,
            score=92.0,
            reasoning=RecommendationReasoning(
                bullets=["ok"], risk_factors=[], invalidation_signals=[]
            ),
            trade_plans=[],
            summary="Strong setup",
        ),
        disclaimer="x",
    )
    analysis_payload = FullAnalysisResponse(
        items=[dummy_item],
        rankings=RankingsResponse(
            rankings=[],
            buy_rankings=[],
            watch_rankings=[],
            best_intraday_candidate=None,
            best_swing_candidate=symbol,
            disclaimer="x",
        ),
        disclaimer="x",
        generated_at=datetime.now(timezone.utc),
    )
    return ScreenerResponse(
        status="COMPLETED",
        screener_name="test",
        scanned_symbols=1,
        data_valid_symbols=[symbol],
        eligible_symbols=[symbol],
        matched_symbols=[symbol],
        matches=[],
        shortlisted_symbols=[symbol],
        buy_candidate_symbols=[symbol],
        watch_candidate_symbols=[],
        disclaimer="x",
        analysis=analysis_payload,
    )


@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(LatestScanResult.__table__.create)
        await conn.run_sync(ScanSnapshot.__table__.create)
        await conn.run_sync(ScanSnapshotRecord.__table__.create)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_feature_flag_rollback_transition(test_db):
    """US3-AS1: OFF → ON switches from multi-write to minimal without restart."""
    response = _response("TCS")

    # 1. Flag OFF -> Legacy multi-write mode
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        service = LatestScanService(test_db)
        await service.persist_successful_scan(response, duration_ms=200, scan_id="legacy-scan-id")
        await test_db.commit()

        latest_count = await test_db.scalar(select(func.count(LatestScanResult.id)))
        snapshot_count = await test_db.scalar(select(func.count(ScanSnapshot.id)))
        assert latest_count == 1
        assert snapshot_count == 1

    # 2. Flag ON -> Minimal write mode (no new snapshot rows)
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        service = LatestScanService(test_db)
        await service.persist_successful_scan(response, duration_ms=100, scan_id="minimal-scan-id")
        await test_db.commit()

        snapshot_count_after = await test_db.scalar(select(func.count(ScanSnapshot.id)))
        assert snapshot_count_after == 1  # unchanged from legacy run
        record_count = await test_db.scalar(select(func.count(ScanSnapshotRecord.id)))
        # Records only from the legacy scan
        assert record_count >= 1


@pytest.mark.asyncio
async def test_rollback_off_restores_snapshot_writes(test_db):
    """SC-005: After operating in minimal mode, toggling OFF restores snapshot writes."""
    response = _response("INFY")

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=50, scan_id="min-a"
        )
        await test_db.commit()
        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=75, scan_id="legacy-b"
        )
        await test_db.commit()
        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) >= 1
        assert await test_db.scalar(select(func.count(LatestScanResult.id))) == 1


@pytest.mark.asyncio
async def test_toggle_cycle_on_off_on(test_db):
    """Regression: multi-cycle toggle leaves latest state correct and no duplicate parents."""
    response = _response("RELIANCE")

    # ON
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=10, scan_id="cycle-1"
        )
        await test_db.commit()
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0

    # OFF
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=20, scan_id="cycle-2"
        )
        await test_db.commit()
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1

    # ON again
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=30, scan_id="cycle-3"
        )
        await test_db.commit()
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1  # no new snapshots
    latest = (
        await test_db.execute(
            select(LatestScanResult).where(LatestScanResult.symbol == "RELIANCE")
        )
    ).scalar_one()
    assert latest.signal_type == "BUY"


@pytest.mark.asyncio
async def test_flag_evaluation_error_defaults_to_legacy_writes(test_db):
    """Edge: settings attribute access failure defaults to legacy multi-write (fail-safe)."""
    response = _response("HDFC")

    # Simulate live reader failure → service catches and defaults to legacy writes
    with patch.object(__import__("app.config.settings", fromlist=["Settings"]).Settings, "is_scan_result_minimal_writes", side_effect=RuntimeError("config store unavailable")):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=40, scan_id="ff-fallback"
        )
        await test_db.commit()

    # Fail-safe OFF → snapshots should be written
    assert await test_db.scalar(select(func.count(LatestScanResult.id))) == 1
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1


@pytest.mark.asyncio
async def test_per_scan_flag_reevaluation_without_process_restart(test_db):
    """FR-010: flag is read per persist call; mid-session toggle takes effect immediately."""
    service = LatestScanService(test_db)

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await service.persist_successful_scan(_response("A"), duration_ms=1, scan_id="re-1")
        await test_db.commit()
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0

    # Same service instance, flag flipped — no process restart
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        await service.persist_successful_scan(_response("B"), duration_ms=2, scan_id="re-2")
        await test_db.commit()
    assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1
    symbols = {
        r.symbol
        for r in (await test_db.execute(select(LatestScanResult))).scalars().all()
    }
    assert "A" in symbols and "B" in symbols
