"""Unit tests for automatic token → scanner bootstrap workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services import token_scanner_bootstrap_service as bootstrap


@pytest.fixture(autouse=True)
def _reset_guards():
    bootstrap.reset_bootstrap_guards_for_tests()
    yield
    bootstrap.reset_bootstrap_guards_for_tests()


def test_is_ist_date_today_and_yesterday():
    now_utc = datetime.now(timezone.utc)
    assert bootstrap._is_ist_date(now_utc) is True

    yesterday = now_utc - timedelta(days=1)
    # Edge near midnight IST could still be "today" in rare cases; use 36h back
    older = now_utc - timedelta(hours=36)
    assert bootstrap._is_ist_date(older) is False


def test_within_scan_window_bounds():
    # 10:00 IST is inside window
    noon_ist = datetime(2026, 7, 23, 10, 0, tzinfo=bootstrap.IST)
    assert bootstrap._within_scan_window(noon_ist) is True

    # 07:00 IST is outside
    early = datetime(2026, 7, 23, 7, 0, tzinfo=bootstrap.IST)
    assert bootstrap._within_scan_window(early) is False

    # 23:00 IST is outside
    late = datetime(2026, 7, 23, 23, 0, tzinfo=bootstrap.IST)
    assert bootstrap._within_scan_window(late) is False


@pytest.mark.asyncio
async def test_check_todays_valid_token_missing():
    db = AsyncMock()
    with patch(
        "backend.app.services.token_service.get_fyers_token_row",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await bootstrap.check_todays_valid_token(db)
        assert result["valid"] is False
        assert result["reason"] == "missing"


@pytest.mark.asyncio
async def test_ensure_daily_skips_when_existing_valid():
    db = AsyncMock()
    result = bootstrap.BootstrapResult()
    plain = "valid-token-plaintext"

    with patch.object(
        bootstrap,
        "check_todays_valid_token",
        new_callable=AsyncMock,
        return_value={
            "valid": True,
            "reason": "ok",
            "token": plain,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
    ):
        token = await bootstrap.ensure_daily_access_token(db, result)

    assert token == plain
    assert result.token_ready is True
    assert result.token_source == "existing_today"
    assert "token_existing_valid" in result.steps


@pytest.mark.asyncio
async def test_ensure_daily_does_not_start_on_generate_failure():
    db = AsyncMock()
    result = bootstrap.BootstrapResult()

    with patch.object(
        bootstrap,
        "check_todays_valid_token",
        new_callable=AsyncMock,
        return_value={"valid": False, "reason": "missing", "token": None},
    ), patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
        side_effect=RuntimeError("broker down"),
    ):
        token = await bootstrap.ensure_daily_access_token(db, result)

    assert token is None
    assert result.token_ready is False
    assert result.token_source == "failed"
    assert result.error is not None
    assert "token_generate_failed" in result.steps


@pytest.mark.asyncio
async def test_maybe_trigger_skips_when_token_not_ready():
    db = AsyncMock()
    result = bootstrap.BootstrapResult(token_ready=False)
    started = await bootstrap.maybe_trigger_auto_scanner(
        db, token_saved_at=None, result=result
    )
    assert started is False
    assert result.scanner_skipped_reason == "token_not_ready"


@pytest.mark.asyncio
async def test_maybe_trigger_skips_when_already_completed_today():
    db = AsyncMock()
    result = bootstrap.BootstrapResult(token_ready=True, token_source="existing_today")
    saved = datetime.now(timezone.utc)

    with patch.object(
        bootstrap,
        "has_scanner_completed_for_todays_token",
        new_callable=AsyncMock,
        return_value=True,
    ), patch.object(
        bootstrap,
        "_within_scan_window",
        return_value=True,
    ), patch(
        "backend.app.services.diagnostics_service.diagnostics"
    ) as diag:
        diag.last_scan_status = None
        started = await bootstrap.maybe_trigger_auto_scanner(
            db, token_saved_at=saved, result=result
        )

    assert started is False
    assert result.scanner_skipped_reason == "scanner_already_completed_today"


@pytest.mark.asyncio
async def test_maybe_trigger_starts_scanner_once():
    db = AsyncMock()
    result = bootstrap.BootstrapResult(token_ready=True, token_source="generated")
    saved = datetime.now(timezone.utc)

    with patch.object(
        bootstrap,
        "has_scanner_completed_for_todays_token",
        new_callable=AsyncMock,
        return_value=False,
    ), patch.object(
        bootstrap,
        "_within_scan_window",
        return_value=True,
    ), patch(
        "backend.app.services.diagnostics_service.diagnostics"
    ) as diag, patch(
        "asyncio.create_task"
    ) as create_task:
        diag.last_scan_status = None
        create_task.return_value = MagicMock()
        started = await bootstrap.maybe_trigger_auto_scanner(
            db, token_saved_at=saved, result=result, trigger_source="test"
        )

    assert started is True
    assert result.scanner_started is True
    create_task.assert_called_once()

    # Second call same process day must not re-trigger
    result2 = bootstrap.BootstrapResult(token_ready=True, token_source="generated")
    with patch.object(
        bootstrap,
        "has_scanner_completed_for_todays_token",
        new_callable=AsyncMock,
        return_value=False,
    ), patch.object(
        bootstrap,
        "_within_scan_window",
        return_value=True,
    ), patch(
        "backend.app.services.diagnostics_service.diagnostics"
    ) as diag2, patch(
        "asyncio.create_task"
    ) as create_task2:
        diag2.last_scan_status = None
        started2 = await bootstrap.maybe_trigger_auto_scanner(
            db, token_saved_at=saved, result=result2, trigger_source="test"
        )

    assert started2 is False
    assert result2.scanner_skipped_reason == "already_triggered_this_process_today"
    create_task2.assert_not_called()


@pytest.mark.asyncio
async def test_run_bootstrap_skips_scanner_on_token_failure():
    with patch.object(
        bootstrap,
        "ensure_daily_access_token",
        new_callable=AsyncMock,
        return_value=None,
    ) as ensure, patch(
        "backend.app.db.session.AsyncSessionLocal"
    ) as session_local:
        # Async context manager mock
        cm = AsyncMock()
        session_local.return_value = cm
        cm.__aenter__.return_value = AsyncMock()
        cm.__aexit__.return_value = None

        # ensure_daily_access_token sets failure on result — simulate via side effect
        async def _fail(db, result):
            result.token_ready = False
            result.token_source = "failed"
            result.error = "boom"
            return None

        ensure.side_effect = _fail

        with patch.object(
            bootstrap,
            "maybe_trigger_auto_scanner",
            new_callable=AsyncMock,
        ) as trigger:
            out = await bootstrap.run_token_to_scanner_bootstrap(trigger_source="test")

        trigger.assert_not_called()
        assert out.token_ready is False
        assert out.scanner_started is False


def test_bootstrap_result_to_dict():
    r = bootstrap.BootstrapResult(
        token_ready=True,
        token_source="generated",
        scanner_started=True,
        steps=["a", "b"],
    )
    d = r.to_dict()
    assert d["token_ready"] is True
    assert d["scanner_started"] is True
    assert d["steps"] == ["a", "b"]
