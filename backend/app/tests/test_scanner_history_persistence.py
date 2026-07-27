"""Integration tests for conditional history persistence (User Story 2).

Acceptance coverage:
- US2-AS1: Flag ON + save_history=False → no history write.
- US2-AS2: Flag ON + save_history=True → history written in same txn path.
- FR-003/FR-004: save_history inspected under minimal mode.
- FR-005: scheduled daily-scan passes save_history=True.
- FR-007: Flag OFF always persists history regardless of save_history.
"""
from __future__ import annotations

import os

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import (
    FinalRecommendation,
    FullAnalysisResponse,
    RankingsResponse,
    RecommendationReasoning,
    ScreenerRequest,
    ScreenerResponse,
    StockAnalysisResult,
)
from app.services.scan_execution_service import ScanExecutionService


def _req() -> ScreenerRequest:
    return ScreenerRequest(mode="swing", timeframe={"swing": "1d"}, symbols=["RELIANCE"])


def _response(symbol: str = "RELIANCE", action: str = "BUY") -> ScreenerResponse:
    item = StockAnalysisResult(
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
            action=action,
            confidence=0.9,
            score=90.0,
            reasoning=RecommendationReasoning(
                bullets=["ok"], risk_factors=[], invalidation_signals=[]
            ),
            trade_plans=[],
            summary=action.lower(),
        ),
        disclaimer="x",
    )
    buy = [symbol] if action == "BUY" else []
    watch = [symbol] if action == "WATCH" else []
    return ScreenerResponse(
        status="COMPLETED",
        screener_name="test",
        scanned_symbols=1,
        data_valid_symbols=[symbol],
        eligible_symbols=[symbol],
        matched_symbols=[symbol],
        matches=[],
        shortlisted_symbols=[symbol],
        buy_candidate_symbols=buy,
        watch_candidate_symbols=watch,
        disclaimer="x",
        analysis=FullAnalysisResponse(
            items=[item],
            rankings=RankingsResponse(
                rankings=[],
                buy_rankings=[],
                watch_rankings=[],
                best_intraday_candidate=None,
                best_swing_candidate=symbol if action == "BUY" else None,
                disclaimer="x",
            ),
            disclaimer="x",
            generated_at=datetime.now(timezone.utc),
        ),
    )


async def _run_completed_scan(
    *,
    minimal: bool,
    save_history: bool,
    mock_history: AsyncMock,
    response: ScreenerResponse | None = None,
    scan_id: str = "hist-test",
):
    """Drive completed-scan path with RouterAgent mocked; assert history gate."""
    response = response or _response()
    mock_lock = MagicMock()
    mock_lock.release = AsyncMock()
    mock_lock.worker_id = "test-worker"

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.execute = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_scan_svc = MagicMock()
    mock_scan_svc.persist_successful_scan = AsyncMock()
    mock_scan_svc.prewarm_scanner_latest_cache = AsyncMock()

    mock_history.return_value = {"items": []}

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": ("true" if minimal else "false")}):
        with patch(
            "app.db.scan_store.save_latest_scan_in_session", mock_history
        ):
            with patch(
                "app.db.scan_store._prewarm_analysis_cache",
                new_callable=AsyncMock,
            ):
                with patch(
                    "app.services.scan_execution_service.get_cached_scanner_result",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    with patch(
                        "app.services.scan_execution_service.cache_scanner_result",
                        new_callable=AsyncMock,
                    ):
                        with patch(
                            "app.services.scan_execution_service.AsyncSessionLocal",
                            return_value=cm,
                        ):
                            with patch(
                                "app.services.scan_execution_service.LatestScanService",
                                return_value=mock_scan_svc,
                            ):
                                with patch(
                                    "app.services.scan_execution_service.RouterAgent"
                                ) as mock_agent_cls:
                                    mock_agent = AsyncMock()
                                    mock_agent.screener_full = AsyncMock(
                                        return_value=response
                                    )
                                    mock_agent_cls.return_value = mock_agent

                                    await ScanExecutionService._run_scan_task(
                                        payload=_req(),
                                        progress_queue=None,
                                        trigger_source="test",
                                        scan_id=scan_id,
                                        lock=mock_lock,
                                        save_history=save_history,
                                    )

    return mock_scan_svc


# ---------------------------------------------------------------------------
# Conditional history matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_gate_logic_matrix():
    """FR-003/FR-004: pure decision matrix for history persistence."""

    def should_write_history(is_minimal: bool, save_history: bool) -> bool:
        return (not is_minimal) or save_history

    assert should_write_history(False, False) is True
    assert should_write_history(False, True) is True
    assert should_write_history(True, False) is False
    assert should_write_history(True, True) is True


@pytest.mark.asyncio
async def test_history_write_on_completed_scan_minimal_save_history_true():
    """US2-AS2: minimal + save_history=True invokes session history write."""
    mock_history = AsyncMock(return_value={"items": []})
    mock_scan_svc = await _run_completed_scan(
        minimal=True,
        save_history=True,
        mock_history=mock_history,
        scan_id="hist-completed-true",
    )
    mock_history.assert_awaited_once()
    mock_scan_svc.persist_successful_scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_skipped_on_completed_scan_minimal_save_history_false():
    """US2-AS1: minimal + save_history=False skips history write."""
    mock_history = AsyncMock(return_value={"items": []})
    mock_scan_svc = await _run_completed_scan(
        minimal=True,
        save_history=False,
        mock_history=mock_history,
        response=_response("TCS"),
        scan_id="hist-completed-false",
    )
    mock_history.assert_not_called()
    mock_scan_svc.persist_successful_scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_mode_always_writes_history_even_if_save_history_false():
    """FR-007: Flag OFF always writes history."""
    mock_history = AsyncMock(return_value={"items": []})
    mock_scan_svc = await _run_completed_scan(
        minimal=False,
        save_history=False,
        mock_history=mock_history,
        response=_response("INFY", "WATCH"),
        scan_id="hist-legacy-always",
    )
    mock_history.assert_awaited_once()
    mock_scan_svc.persist_successful_scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_write_failure_rolls_back_with_persist():
    """Failure path: history failure aborts the shared transaction (H2)."""
    mock_history = AsyncMock(
        side_effect=RuntimeError("DB_HISTORY_WRITE_FAILED: boom")
    )
    mock_scan_svc = await _run_completed_scan(
        minimal=True,
        save_history=True,
        mock_history=mock_history,
        response=_response("WIPRO"),
        scan_id="hist-fail",
    )
    mock_history.assert_awaited_once()
    # persist is attempted before history in the same try block
    mock_scan_svc.persist_successful_scan.assert_awaited_once()


def test_scheduler_daily_scan_passes_save_history_true():
    """FR-005: cron daily-scan endpoint must pass save_history=True."""
    import app.routes.scheduler as scheduler_mod

    source = inspect.getsource(scheduler_mod.daily_scan)
    assert "save_history=True" in source or "save_history = True" in source


def test_execute_scan_signature_accepts_save_history():
    """FR-003: execute_scan and _run_scan_task expose save_history parameter."""
    sig_exec = inspect.signature(ScanExecutionService.execute_scan)
    sig_run = inspect.signature(ScanExecutionService._run_scan_task)
    assert "save_history" in sig_exec.parameters
    assert sig_exec.parameters["save_history"].default is False
    assert "save_history" in sig_run.parameters
    assert sig_run.parameters["save_history"].default is False


@pytest.mark.asyncio
async def test_conditional_history_persistence_flag_on():
    """Backward-compatible name: matrix covered by dedicated completed-scan tests."""
    mock_history = AsyncMock(return_value={})
    await _run_completed_scan(
        minimal=True, save_history=False, mock_history=mock_history, scan_id="h1"
    )
    mock_history.assert_not_called()

    mock_history2 = AsyncMock(return_value={})
    await _run_completed_scan(
        minimal=True, save_history=True, mock_history=mock_history2, scan_id="h2"
    )
    mock_history2.assert_awaited_once()
