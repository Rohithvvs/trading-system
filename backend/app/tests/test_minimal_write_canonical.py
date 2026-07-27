"""Unit + integration tests for minimal-write canonical mode (User Story 1).

Acceptance coverage:
- US1-AS1: Flag ON upserts latest_scan_results; zero snapshot table writes.
- US1-AS2: Flag OFF writes latest + snapshot tables (legacy multi-write).
- FR-001/FR-002: latest_scan_results is always the canonical write target.
- FR-006: redundant snapshot tables bypassed when flag ON.
- FR-007: legacy writes retained when flag OFF.
- Edge: empty candidates, BUY/WATCH without analysis items, upsert update.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
from app.services.persistence_service import PersistenceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(action: str, score: float = 80.0, confidence: float = 0.9) -> FinalRecommendation:
    return FinalRecommendation(
        action=action,
        confidence=confidence,
        score=score,
        reasoning=RecommendationReasoning(
            bullets=["ok"], risk_factors=[], invalidation_signals=[]
        ),
        trade_plans=[],
        summary=f"{action} setup",
    )


def _item(symbol: str, action: str = "BUY", score: float = 88.5) -> StockAnalysisResult:
    return StockAnalysisResult(
        symbol=symbol,
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        fundamental=None,
        backtests=[],
        recommendation=_rec(action, score=score),
        disclaimer="x",
    )


def _response(
    items: list[StockAnalysisResult] | None = None,
    buy: list[str] | None = None,
    watch: list[str] | None = None,
    **kwargs,
) -> ScreenerResponse:
    items = items if items is not None else [_item("RELIANCE", "BUY", 88.5)]
    buy = buy if buy is not None else [i.symbol for i in items if i.recommendation.action == "BUY"]
    watch = watch if watch is not None else [
        i.symbol for i in items if i.recommendation.action == "WATCH"
    ]
    shortlisted = list(dict.fromkeys(buy + watch))
    analysis = FullAnalysisResponse(
        items=items,
        rankings=RankingsResponse(
            rankings=[],
            buy_rankings=[],
            watch_rankings=[],
            best_intraday_candidate=None,
            best_swing_candidate=buy[0] if buy else None,
            disclaimer="x",
        ),
        disclaimer="x",
        generated_at=datetime.now(timezone.utc),
    )
    defaults = dict(
        status="COMPLETED",
        screener_name="test",
        scanned_symbols=max(len(items), 1),
        data_valid_symbols=shortlisted or ["RELIANCE"],
        eligible_symbols=shortlisted or ["RELIANCE"],
        matched_symbols=shortlisted or ["RELIANCE"],
        matches=[],
        shortlisted_symbols=shortlisted,
        buy_candidate_symbols=buy,
        watch_candidate_symbols=watch,
        disclaimer="x",
        analysis=analysis,
    )
    defaults.update(kwargs)
    return ScreenerResponse(**defaults)


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


# ---------------------------------------------------------------------------
# PersistenceService unit tests (canonical upsert)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistence_service_empty_list_is_noop(test_db):
    """Edge: empty candidate batch must not write rows."""
    ps = PersistenceService(test_db)
    await ps.save_latest_scan_results([])
    count = await test_db.scalar(select(func.count(LatestScanResult.id)))
    assert count == 0


@pytest.mark.asyncio
async def test_persistence_service_upserts_and_updates(test_db):
    """FR-002: atomic upsert inserts then updates on symbol conflict."""
    ps = PersistenceService(test_db)
    now = datetime.now(timezone.utc)

    await ps.save_latest_scan_results(
        [
            {
                "symbol": "INFY",
                "signal_type": "BUY",
                "score": 70.0,
                "confidence": 0.7,
                "scanned_at": now,
            }
        ]
    )
    await test_db.commit()

    await ps.save_latest_scan_results(
        [
            {
                "symbol": "INFY",
                "signal_type": "WATCH",
                "score": 55.0,
                "confidence": 0.55,
                "scanned_at": now,
            }
        ]
    )
    await test_db.commit()

    rows = (await test_db.execute(select(LatestScanResult))).scalars().all()
    assert len(rows) == 1
    assert rows[0].symbol == "INFY"
    assert rows[0].signal_type == "WATCH"
    assert float(rows[0].score) == 55.0


# ---------------------------------------------------------------------------
# US1 — Minimal mode (flag ON)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_write_canonical_upsert_and_bypass_snapshots(test_db):
    """US1-AS1: Flag ON upserts latest_scan_results; zero snapshot writes."""
    response = _response()

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        service = LatestScanService(test_db)
        await service.persist_successful_scan(response, duration_ms=150, scan_id="test-scan-001")
        await test_db.commit()

        latest = (
            await test_db.execute(
                select(LatestScanResult).where(LatestScanResult.symbol == "RELIANCE")
            )
        ).scalar_one_or_none()
        assert latest is not None
        assert latest.signal_type == "BUY"
        assert float(latest.score) == 88.5

        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) == 0

        payload_str, _cache_status = await service.get_latest_scan(
            format_type="dashboard", force=True, cache_enabled=False
        )
        assert "RELIANCE" in payload_str
        assert "BUY" in payload_str


@pytest.mark.asyncio
async def test_minimal_mode_writes_multiple_symbols(test_db):
    """FR-001: multi-symbol scan populates only latest_scan_results under minimal mode."""
    response = _response(
        items=[
            _item("RELIANCE", "BUY", 90.0),
            _item("TCS", "WATCH", 65.0),
            _item("INFY", "REJECT", 20.0),
        ],
        buy=["RELIANCE"],
        watch=["TCS"],
    )

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=100, scan_id="multi-001"
        )
        await test_db.commit()

        symbols = {
            r.symbol: r.signal_type
            for r in (await test_db.execute(select(LatestScanResult))).scalars().all()
        }
        assert symbols["RELIANCE"] == "BUY"
        assert symbols["TCS"] == "WATCH"
        assert symbols["INFY"] == "REJECT"
        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0


@pytest.mark.asyncio
async def test_minimal_mode_buy_watch_without_analysis_items(test_db):
    """Edge: BUY/WATCH lists alone still produce canonical latest rows."""
    response = _response(items=[], buy=["HDFCBANK"], watch=["SBIN"])

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=50, scan_id="lists-only"
        )
        await test_db.commit()

        rows = (await test_db.execute(select(LatestScanResult))).scalars().all()
        by_sym = {r.symbol: r.signal_type for r in rows}
        assert by_sym == {"HDFCBANK": "BUY", "SBIN": "WATCH"}
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) == 0


@pytest.mark.asyncio
async def test_minimal_mode_empty_candidates_no_snapshot_writes(test_db):
    """Edge: empty scan still bypasses snapshot tables under minimal mode."""
    response = _response(
        items=[],
        buy=[],
        watch=[],
        scanned_symbols=0,
        data_valid_symbols=[],
        eligible_symbols=[],
        matched_symbols=[],
        shortlisted_symbols=[],
    )

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=10, scan_id="empty-001"
        )
        await test_db.commit()

        assert await test_db.scalar(select(func.count(LatestScanResult.id))) == 0
        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) == 0


@pytest.mark.asyncio
async def test_minimal_mode_canonical_write_failure_skips_snapshots(test_db):
    """Failure path: latest_scan_results write failure must raise and not create snapshots."""
    response = _response()

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        with patch.object(
            PersistenceService,
            "save_latest_scan_results",
            new_callable=AsyncMock,
            side_effect=TimeoutError("connection timeout"),
        ):
            service = LatestScanService(test_db)
            with pytest.raises(RuntimeError, match="DB_CANONICAL_WRITE_FAILED"):
                await service.persist_successful_scan(response, duration_ms=10, scan_id="fail-canon")

        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 0
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) == 0


@pytest.mark.asyncio
async def test_minimal_mode_prefers_canonical_over_stale_snapshot(test_db):
    """C1: With flag ON, dashboard must serve fresh canonical rows, not old snapshots."""
    now = datetime.now(timezone.utc)
    test_db.add(
        ScanSnapshot(
            scan_id="stale-snap",
            scan_timestamp=now,
            scan_duration_ms=100,
            total_scanned=1,
            valid_symbols=1,
            buy_count=1,
            watch_count=0,
            rejected_count=0,
            status="COMPLETED",
            error_type=None,
        )
    )
    test_db.add(
        ScanSnapshotRecord(
            scan_id="stale-snap",
            symbol="OLDCO",
            recommendation="BUY",
            score=50.0,
            close_price=100.0,
            reason="stale",
        )
    )
    await test_db.commit()

    # Fresh canonical write under minimal mode
    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        await LatestScanService(test_db).persist_successful_scan(
            _response(items=[_item("NEWCO", "BUY", 99.0)], buy=["NEWCO"], watch=[]),
            duration_ms=10,
            scan_id="fresh-001",
        )
        await test_db.commit()

        payload = await LatestScanService(test_db).get_latest_completed_scan()
        assert payload is not None
        buy_syms = [c["symbol"] for c in (payload.get("buy_candidates") or [])]
        assert "NEWCO" in buy_syms
        assert "OLDCO" not in buy_syms


def test_build_dashboard_payload_from_screener_includes_contract_keys():
    """M-R1: in-memory ScreenerResponse projection keeps dashboard contract keys."""
    response = _response(items=[_item("RELIANCE", "BUY", 88.5)], buy=["RELIANCE"], watch=[])
    payload = LatestScanService.build_dashboard_payload_from_screener(
        response, duration_ms=42, scan_id="rich-1"
    )
    for key in (
        "scan_id",
        "scan_timestamp",
        "last_scan_completed_at",
        "total_scanned",
        "buy_count",
        "watch_count",
        "rejected_count",
        "buy_candidates",
        "watch_candidates",
        "rejected_candidates",
    ):
        assert key in payload
    assert payload["scan_id"] == "rich-1"
    assert payload["buy_candidates"][0]["symbol"] == "RELIANCE"
    assert "close_price" in payload["buy_candidates"][0]


# ---------------------------------------------------------------------------
# US1 — Legacy mode (flag OFF)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mode_writes_latest_and_snapshots(test_db):
    """US1-AS2 / FR-007: Flag OFF writes latest_scan_results + snapshot tables."""
    response = _response(
        items=[_item("RELIANCE", "BUY", 88.5), _item("TCS", "WATCH", 60.0)],
        buy=["RELIANCE"],
        watch=["TCS"],
    )

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        await LatestScanService(test_db).persist_successful_scan(
            response, duration_ms=200, scan_id="legacy-001"
        )
        await test_db.commit()

        assert await test_db.scalar(select(func.count(LatestScanResult.id))) == 2
        assert await test_db.scalar(select(func.count(ScanSnapshot.id))) == 1
        assert await test_db.scalar(select(func.count(ScanSnapshotRecord.id))) >= 2

        snap = (
            await test_db.execute(
                select(ScanSnapshot).where(ScanSnapshot.scan_id == "legacy-001")
            )
        ).scalar_one()
        assert snap.status == "COMPLETED"
        assert snap.buy_count == 1
        assert snap.watch_count == 1


@pytest.mark.asyncio
async def test_legacy_mode_updates_running_snapshot(test_db):
    """Regression: RUNNING placeholder is updated, not duplicated (one scan_id)."""
    now = datetime.now(timezone.utc)
    test_db.add(
        ScanSnapshot(
            scan_id="running-then-done",
            scan_timestamp=now,
            scan_duration_ms=0,
            total_scanned=1,
            valid_symbols=0,
            buy_count=0,
            watch_count=0,
            rejected_count=0,
            status="RUNNING",
            error_type=None,
        )
    )
    await test_db.commit()

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        await LatestScanService(test_db).persist_successful_scan(
            _response(), duration_ms=333, scan_id="running-then-done"
        )
        await test_db.commit()

        snaps = (
            await test_db.execute(
                select(ScanSnapshot).where(ScanSnapshot.scan_id == "running-then-done")
            )
        ).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].status == "COMPLETED"
        assert snaps[0].scan_duration_ms == 333


# ---------------------------------------------------------------------------
# Scan execution: RUNNING snapshot skip under minimal mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_execution_skips_running_snapshot_when_minimal():
    """FR-006: ScanExecutionService must not insert RUNNING snapshot when flag ON."""
    from app.schemas import ScreenerRequest
    from app.services.scan_execution_service import ScanExecutionService

    req = ScreenerRequest(mode="swing", timeframe={"swing": "1d"}, symbols=["RELIANCE"])
    mock_lock = MagicMock()
    mock_lock.release = AsyncMock()
    mock_lock.worker_id = "test-worker"

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        with patch(
            "app.services.scan_execution_service.AsyncSessionLocal", return_value=mock_cm
        ):
            with patch(
                "app.services.scan_execution_service.get_cached_scanner_result",
                new_callable=AsyncMock,
                return_value={"status": "COMPLETED", "buy_candidate_symbols": []},
            ):
                await ScanExecutionService._run_scan_task(
                    payload=req,
                    progress_queue=None,
                    trigger_source="test",
                    scan_id="skip-running-001",
                    lock=mock_lock,
                    save_history=False,
                )

    # Minimal mode must never create a RUNNING ScanSnapshot parent row.
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_scan_execution_creates_running_snapshot_when_legacy():
    """FR-007: Flag OFF creates RUNNING snapshot parent row."""
    from app.schemas import ScreenerRequest
    from app.services.scan_execution_service import ScanExecutionService

    req = ScreenerRequest(mode="swing", timeframe={"swing": "1d"}, symbols=["RELIANCE"])
    mock_lock = MagicMock()
    mock_lock.release = AsyncMock()
    mock_lock.worker_id = "test-worker"

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        with patch(
            "app.services.scan_execution_service.AsyncSessionLocal", return_value=mock_cm
        ):
            with patch(
                "app.services.scan_execution_service.get_cached_scanner_result",
                new_callable=AsyncMock,
                return_value={"status": "COMPLETED", "buy_candidate_symbols": []},
            ):
                await ScanExecutionService._run_scan_task(
                    payload=req,
                    progress_queue=None,
                    trigger_source="test",
                    scan_id="running-legacy-001",
                    lock=mock_lock,
                    save_history=False,
                )

    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert getattr(added, "status", None) == "RUNNING"
    assert getattr(added, "scan_id", None) == "running-legacy-001"
