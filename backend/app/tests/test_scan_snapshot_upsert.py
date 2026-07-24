"""Prove one scan_id ⇒ one scan_snapshots row (RUNNING then COMPLETED)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pytest

from app.schemas import (
    FinalRecommendation,
    FullAnalysisResponse,
    RankingsResponse,
    RecommendationReasoning,
    ScreenerResponse,
    StockAnalysisResult,
)
from app.services.latest_scan_service import LatestScanService


def _empty_response(**kwargs) -> ScreenerResponse:
    analysis = FullAnalysisResponse(
        items=[
            StockAnalysisResult(
                symbol="A",
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
                    confidence=0.8,
                    score=80.0,
                    reasoning=RecommendationReasoning(
                        bullets=["ok"], risk_factors=[], invalidation_signals=[]
                    ),
                    trade_plans=[],
                    summary="buy",
                ),
                disclaimer="x",
            )
        ],
        rankings=RankingsResponse(
            rankings=[],
            buy_rankings=[],
            watch_rankings=[],
            best_intraday_candidate=None,
            best_swing_candidate="A",
            disclaimer="x",
        ),
        disclaimer="x",
        generated_at=datetime.now(timezone.utc),
    )
    defaults = dict(
        scanned_symbols=10,
        screener_name="test",
        data_valid_symbols=["A"],
        eligible_symbols=["A"],
        shortlisted_symbols=["A"],
        buy_candidate_symbols=["A"],
        watch_candidate_symbols=[],
        matched_symbols=["A"],
        matches=[],
        all_analyzed_stocks=[],
        analysis=analysis,
        disclaimer="x",
    )
    defaults.update(kwargs)
    return ScreenerResponse(**defaults)


class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self


class _FakeSession:
    """Minimal async session that records adds/deletes/flushes for upsert tests."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added: list = []
        self.executed: list = []
        self.flushed = 0

    async def scalar(self, stmt):
        return self.existing

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1


@pytest.mark.asyncio
async def test_persist_updates_existing_running_row_no_second_insert():
    """Mirrors production: RUNNING insert then persist_successful_scan(same scan_id)."""
    from app.models.market_data import ScanSnapshot, ScanSnapshotRecord

    scan_id = str(uuid.uuid4())
    running = ScanSnapshot(
        scan_id=scan_id,
        scan_timestamp=datetime.now(timezone.utc),
        scan_duration_ms=0,
        total_scanned=0,
        valid_symbols=0,
        buy_count=0,
        watch_count=0,
        rejected_count=0,
        status="RUNNING",
        error_type=None,
    )
    session = _FakeSession(existing=running)
    svc = LatestScanService(session)
    response = _empty_response()

    await svc.persist_successful_scan(response, duration_ms=1234, scan_id=scan_id)

    # Must NOT add a second ScanSnapshot parent
    parent_adds = [o for o in session.added if isinstance(o, ScanSnapshot)]
    assert parent_adds == [], f"expected UPDATE path, got INSERT parents={parent_adds}"

    # Existing row mutated to COMPLETED
    assert running.status == "COMPLETED"
    assert running.scan_duration_ms == 1234
    assert running.buy_count == 1
    assert session.flushed == 1

    children = [o for o in session.added if isinstance(o, ScanSnapshotRecord)]
    assert len(children) >= 1
    assert all(c.scan_id == scan_id for c in children)


@pytest.mark.asyncio
async def test_persist_inserts_when_no_prior_row():
    """Scheduler path: no RUNNING placeholder → single INSERT."""
    from app.models.market_data import ScanSnapshot, ScanSnapshotRecord

    scan_id = str(uuid.uuid4())
    session = _FakeSession(existing=None)
    svc = LatestScanService(session)
    response = _empty_response()

    await svc.persist_successful_scan(response, duration_ms=500, scan_id=scan_id)

    parents = [o for o in session.added if isinstance(o, ScanSnapshot)]
    assert len(parents) == 1
    assert parents[0].scan_id == scan_id
    assert parents[0].status == "COMPLETED"
    children = [o for o in session.added if isinstance(o, ScanSnapshotRecord)]
    assert len(children) >= 1


@pytest.mark.asyncio
async def test_persist_idempotent_second_call_updates_same_row():
    """Calling persist twice with same scan_id never creates two parents."""
    from app.models.market_data import ScanSnapshot

    scan_id = str(uuid.uuid4())
    row = ScanSnapshot(
        scan_id=scan_id,
        scan_timestamp=datetime.now(timezone.utc),
        scan_duration_ms=100,
        total_scanned=5,
        valid_symbols=5,
        buy_count=1,
        watch_count=0,
        rejected_count=0,
        status="COMPLETED",
        error_type=None,
    )
    session = _FakeSession(existing=row)
    svc = LatestScanService(session)
    response = _empty_response(
        buy_candidate_symbols=["A", "B"],
        shortlisted_symbols=["A", "B"],
    )

    await svc.persist_successful_scan(response, duration_ms=999, scan_id=scan_id)

    parents = [o for o in session.added if isinstance(o, ScanSnapshot)]
    assert parents == []
    assert row.status == "COMPLETED"
    assert row.buy_count == 2
    assert row.scan_duration_ms == 999


def test_scan_execution_has_single_persist_invocation():
    """Static guard: _run_scan_task awaits persist_successful_scan exactly once."""
    import inspect
    from app.services import scan_execution_service as ses

    src = inspect.getsource(ses.ScanExecutionService._run_scan_task)
    # Count actual await calls, not comments
    calls = re.findall(r"await\s+scan_service\.persist_successful_scan\s*\(", src)
    assert len(calls) == 1, f"expected exactly 1 await persist call, found {len(calls)}"
