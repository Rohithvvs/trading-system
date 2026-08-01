"""Automated tests for Sprint 4 – Database Storage + Basic Monitoring
(feature branch: 009-db-storage-monitoring).

Specification: specs/009-db-storage-monitoring/spec.md
Plan: specs/009-db-storage-monitoring/plan.md

Coverage targets:
  US1  – Persist access token on success (status=Success, last_error=NULL, encrypted)
  US2  – Record failure diagnostics without wiping prior token
  US3  – Environment parity via AsyncSessionLocal / settings (no hardcoded creds)
  Edge – first-run success/failure, recovery transitions, encryption, timing, CLI

All external Fyers network calls are mocked. Persistence uses an isolated
in-memory SQLite engine so the suite stays offline, deterministic, and does not
touch development or production databases.

Automation persists in a dedicated atomic path (does not call UI
``save_access_token`` / live re-validation).
"""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest import mock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.pool import StaticPool

from backend.app.core.token_crypto import is_encrypted
from backend.app.db.base import Base
from backend.app.models import FyersToken, FyersTokenHistory
from backend.app.services.token_service import (
    _decrypt_from_storage,
    _encrypt_for_storage,
    _mask_token,
    generate_and_persist_fyers_token,
    mask_access_token_preview,
)
from fyers_token import FyersAuthError, FyersConfigError, FyersConnectionError

# ---------------------------------------------------------------------------
# SQLite dialect shims (PG-only column types used elsewhere in the schema)
# ---------------------------------------------------------------------------


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "CHAR(36)"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_env() -> AsyncGenerator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]], None]:
    """Isolated in-memory engine + session factory (APP_ENV=test forced).

    StaticPool keeps a single shared connection so multiple sessions see the
    same ``:memory:`` database (default SQLite memory DBs are per-connection).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with mock.patch(
        "backend.app.services.token_service.settings.app_env",
        "test",
    ):
        yield engine, maker

    await engine.dispose()


async def _seed_token(
    maker: async_sessionmaker[AsyncSession],
    *,
    plain: str = "old_valid_token",
    status: str = "Success",
    last_error: str | None = None,
) -> str:
    """Insert singleton id=1 with encrypted token; returns encrypted ciphertext."""
    async with maker() as db:
        await db.execute(delete(FyersToken).where(FyersToken.id == 1))
        now = datetime.now(timezone.utc)
        cipher = _encrypt_for_storage(plain)
        row = FyersToken(
            id=1,
            access_token=cipher,
            status=status,
            last_error=last_error,
            is_active=True,
            access_token_saved_at=now - timedelta(hours=1),
            created_at=now - timedelta(days=1),
        )
        db.add(row)
        await db.commit()
        return cipher


async def _get_row(maker: async_sessionmaker[AsyncSession]) -> FyersToken | None:
    async with maker() as db:
        return (await db.scalars(select(FyersToken).where(FyersToken.id == 1))).first()


# ===========================================================================
# US1 – Persist Access Token on Success (P1)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generate_and_persist_token_success(db_env):
    """US1 / FR-001 / FR-003 / FR-004 / FR-005:
    Success path encrypts the token, sets status=Success, clears last_error,
    and refreshes access_token_saved_at.
    """
    _, maker = db_env
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_success_token"
    before = datetime.now(timezone.utc)

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=test_token,
    ):
        async with maker() as db:
            result = await generate_and_persist_fyers_token(db)

    assert result["status"] == "Success"
    assert "saved_at" in result
    assert result.get("token_preview")
    assert test_token not in str(result["token_preview"])

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Success"
    assert row.last_error is None
    assert row.access_token is not None
    assert test_token not in row.access_token
    assert is_encrypted(row.access_token)
    assert _decrypt_from_storage(row.access_token) == test_token
    assert row.access_token_saved_at is not None
    saved_at = row.access_token_saved_at
    if saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    assert saved_at >= before - timedelta(seconds=2)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_success_creates_singleton_row_when_missing(db_env):
    """US1 edge: first run with empty table creates id=1 singleton."""
    _, maker = db_env
    assert await _get_row(maker) is None
    token = "first_run_token_abc123xyz"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=token,
    ):
        async with maker() as db:
            result = await generate_and_persist_fyers_token(db)

    assert result["status"] == "Success"
    row = await _get_row(maker)
    assert row is not None
    assert row.id == 1
    assert row.status == "Success"
    assert row.last_error is None
    assert _decrypt_from_storage(row.access_token) == token


@pytest.mark.asyncio
@pytest.mark.integration
async def test_success_clears_previous_last_error(db_env):
    """FR-004: recovery from Failed → Success must NULL last_error."""
    _, maker = db_env
    await _seed_token(
        maker,
        plain="stale_token",
        status="Failed",
        last_error="previous network outage",
    )
    new_token = "recovered_token_xyz789"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=new_token,
    ):
        async with maker() as db:
            await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Success"
    assert row.last_error is None
    assert _decrypt_from_storage(row.access_token) == new_token


@pytest.mark.asyncio
@pytest.mark.integration
async def test_success_persists_within_two_seconds(db_env):
    """SC-001: successful DB update completes within 2.0s of generation."""
    _, maker = db_env
    token = "perf_success_token_001"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=token,
    ):
        started = time.perf_counter()
        async with maker() as db:
            await generate_and_persist_fyers_token(db)
        elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"Success persistence took {elapsed:.3f}s (budget 2.0s)"
    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Success"


# ===========================================================================
# US2 – Record Failure and Diagnostic Info (P2)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generate_and_persist_token_failure(db_env):
    """US2 / FR-002 / FR-003 / FR-004:
    Permanent auth failure → status=Failed, last_error set, old token kept,
    exception re-raised.
    """
    _, maker = db_env
    error_msg = "PIN verification failed: Invalid PIN"
    await _seed_token(maker, plain="old_valid_token", status="Success")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError(error_msg),
    ):
        async with maker() as db:
            with pytest.raises(FyersAuthError, match=error_msg):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert error_msg in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "old_valid_token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_after_transient_retries_exhausted(db_env):
    """US2 acceptance scenario 1: transient exhaustion → Failed + last_error."""
    _, maker = db_env
    await _seed_token(maker, plain="keep_me", status="Success")
    err = FyersConnectionError(
        "Connection timed out [after 3 attempts; maximum retries exhausted]"
    )

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=err,
    ):
        async with maker() as db:
            with pytest.raises(FyersConnectionError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert "maximum retries exhausted" in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "keep_me"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_fail_fast_config_error(db_env):
    """US2 acceptance scenario 2: permanent config error fail-fast."""
    _, maker = db_env
    await _seed_token(maker, plain="prev_token", status="Success")
    err = FyersConfigError("Missing required environment variable: FYERS_PIN")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=err,
    ):
        async with maker() as db:
            with pytest.raises(FyersConfigError, match="FYERS_PIN"):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert "FYERS_PIN" in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "prev_token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_does_not_wipe_previous_token(db_env):
    """Edge case: failed run MUST NOT delete or nullify prior access_token."""
    _, maker = db_env
    encrypted_before = await _seed_token(maker, plain="still_valid_for_hours")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError("Invalid PIN"),
    ):
        async with maker() as db:
            with pytest.raises(FyersAuthError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.access_token == encrypted_before
    assert row.access_token not in ("", None)
    assert _decrypt_from_storage(row.access_token) == "still_valid_for_hours"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_creates_placeholder_when_no_prior_row(db_env):
    """Edge: first-run failure with empty table still records monitoring fields."""
    _, maker = db_env
    assert await _get_row(maker) is None

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError("auth boom"),
    ):
        async with maker() as db:
            with pytest.raises(FyersAuthError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.id == 1
    assert row.status == "Failed"
    assert "auth boom" in (row.last_error or "")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_updates_last_error_on_repeated_failure(db_env):
    """Failed → Failed: last_error is replaced with the new message."""
    _, maker = db_env
    await _seed_token(
        maker,
        plain="old_token",
        status="Failed",
        last_error="old error message",
    )

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersConnectionError("new network failure"),
    ):
        async with maker() as db:
            with pytest.raises(FyersConnectionError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert "new network failure" in (row.last_error or "")
    assert "old error message" not in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "old_token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_persists_within_two_seconds(db_env):
    """SC-002: failure DB update completes within 2.0s."""
    _, maker = db_env
    await _seed_token(maker)

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError("fast fail"),
    ):
        started = time.perf_counter()
        async with maker() as db:
            with pytest.raises(FyersAuthError):
                await generate_and_persist_fyers_token(db)
        elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"Failure persistence took {elapsed:.3f}s (budget 2.0s)"
    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_updates_access_token_saved_at(db_env):
    """FR-002: failure still refreshes monitoring timestamp."""
    _, maker = db_env
    await _seed_token(maker)
    before = datetime.now(timezone.utc)

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=RuntimeError("unexpected"),
    ):
        async with maker() as db:
            with pytest.raises(RuntimeError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    saved_at = row.access_token_saved_at
    if saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    assert saved_at >= before - timedelta(seconds=2)


# ===========================================================================
# Encryption / FR-005 / SC-003
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_persisted_token_is_never_plaintext(db_env):
    """SC-003 / FR-005: 100% of stored tokens are encrypted (no plaintext JWT)."""
    _, maker = db_env
    plain = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.plaintext_must_not_appear.sig"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=plain,
    ):
        async with maker() as db:
            await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    stored = row.access_token
    assert plain not in stored
    assert "plaintext_must_not_appear" not in stored
    assert is_encrypted(stored)
    assert _decrypt_from_storage(stored) == plain


@pytest.mark.unit
def test_encrypt_for_storage_roundtrip_and_mask():
    """Unit: storage helpers encrypt and mask without leaking full secret."""
    plain = "secret_access_token_value_1234"
    cipher = _encrypt_for_storage(plain)
    assert cipher != plain
    assert is_encrypted(cipher)
    assert _decrypt_from_storage(cipher) == plain

    masked = _mask_token(plain)
    assert masked is not None
    assert plain not in masked
    assert masked.endswith("1234")


# ===========================================================================
# Automation path decoupled from UI save / live validation
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_automation_does_not_call_ui_save_access_token(db_env):
    """Automation must not use UI save_access_token (avoids live re-validation)."""
    _, maker = db_env

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="auto_token_no_ui_save",
    ), mock.patch(
        "backend.app.services.token_service.save_access_token",
        new=mock.AsyncMock(
            side_effect=AssertionError("save_access_token must not be called")
        ),
    ) as mocked_save:
        async with maker() as db:
            result = await generate_and_persist_fyers_token(db)

    assert result["status"] == "Success"
    mocked_save.assert_not_called()
    row = await _get_row(maker)
    assert row is not None
    assert _decrypt_from_storage(row.access_token) == "auto_token_no_ui_save"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_automation_history_note_not_manual_ui(db_env):
    """History audit trail must identify automated generation (not UI)."""
    _, maker = db_env

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="history_note_token_ZZ99",
    ):
        async with maker() as db:
            await generate_and_persist_fyers_token(db)

    async with maker() as db:
        hist = (
            await db.scalars(
                select(FyersTokenHistory).order_by(FyersTokenHistory.id.desc())
            )
        ).first()
    assert hist is not None
    assert hist.note == "Automated headless token generation"
    assert "Manual save via UI" not in (hist.note or "")
    assert hist.status == "Success"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_generated_token_records_failed(db_env):
    """Empty generation result is treated as job failure (token preserved)."""
    _, maker = db_env
    await _seed_token(maker, plain="previous", status="Success")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="   ",
    ):
        async with maker() as db:
            with pytest.raises(RuntimeError, match="empty"):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert "empty" in (row.last_error or "").lower()
    assert _decrypt_from_storage(row.access_token) == "previous"


# ===========================================================================
# US3 – Environment Parity / FR-006 / SC-004
# ===========================================================================


@pytest.mark.unit
def test_update_token_cli_uses_async_session_local_and_settings():
    """US3 / FR-006 / SC-004: CLI wires AsyncSessionLocal; no hardcoded secrets."""
    import update_token

    source = inspect.getsource(update_token)
    assert "AsyncSessionLocal" in source
    assert "generate_and_persist_fyers_token" in source
    # Must not import private service helpers
    assert "_decrypt_from_storage" not in source
    assert "_mask_token" not in source
    for forbidden in (
        "YJ08718",
        "L9NY305RTW",
        "sk_live",
        "postgres://",
        "postgresql://",
        "neon.tech",
    ):
        assert forbidden not in source


@pytest.mark.unit
def test_mask_access_token_preview_is_public():
    """Public preview helper for CLI without private imports."""
    token = "public_preview_token_WXYZ"
    masked = mask_access_token_preview(token)
    assert masked is not None
    assert token not in masked
    assert masked.endswith("WXYZ")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cli_main_success_exit_zero_and_masks_token(db_env, capsys):
    """CLI contract: exit 0 and print masked token preview on success."""
    import update_token

    _, maker = db_env
    token = "cli_success_token_ABCD"

    class _CM:
        def __init__(self, session: AsyncSession):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            return False

    async with maker() as session:
        with mock.patch(
            "update_token.AsyncSessionLocal",
            return_value=_CM(session),
        ), mock.patch(
            "fyers_token.generate_fyers_access_token",
            return_value=token,
        ):
            code = await update_token.main()

    assert code == 0
    out = capsys.readouterr().out
    assert "Token updated successfully" in out
    assert token not in out
    assert "ABCD" in out or "*" in out


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cli_main_failure_exit_one_and_stderr(db_env, capsys):
    """CLI contract: exit 1 and write Error: Class - message to stderr."""
    import update_token

    _, maker = db_env
    await _seed_token(maker)

    class _CM:
        def __init__(self, session: AsyncSession):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            return False

    async with maker() as session:
        with mock.patch(
            "update_token.AsyncSessionLocal",
            return_value=_CM(session),
        ), mock.patch(
            "fyers_token.generate_fyers_access_token",
            side_effect=FyersAuthError("PIN rejected"),
        ):
            code = await update_token.main()

    assert code == 1
    err = capsys.readouterr().err
    assert "Error:" in err
    assert "FyersAuthError" in err
    assert "PIN rejected" in err


# ===========================================================================
# Database unavailability edge case
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_database_commit_failure_on_success_path_propagates(db_env):
    """Edge: DB unreachable / commit failure is raised (must not hang)."""
    _, maker = db_env

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="token_when_db_breaks",
    ):
        async with maker() as session:
            with mock.patch.object(
                session,
                "commit",
                side_effect=OSError("database is locked"),
            ):
                with pytest.raises(Exception):
                    await asyncio.wait_for(
                        generate_and_persist_fyers_token(session),
                        timeout=2.0,
                    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_database_failure_during_failure_recording_still_reraises(db_env):
    """If recording Failed status itself fails, original exception still propagates."""
    _, maker = db_env
    await _seed_token(maker)

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError("auth failed"),
    ):
        async with maker() as db:
            with mock.patch.object(
                db,
                "commit",
                side_effect=OSError("connection refused"),
            ):
                with pytest.raises(FyersAuthError, match="auth failed"):
                    await asyncio.wait_for(
                        generate_and_persist_fyers_token(db),
                        timeout=2.0,
                    )


# ===========================================================================
# State-machine transitions (data-model.md)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_state_success_to_success_updates_token(db_env):
    """Success → Success: new token replaces old, monitoring fields refreshed."""
    _, maker = db_env
    await _seed_token(maker, plain="day1_token", status="Success")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="day2_token",
    ):
        async with maker() as db:
            await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Success"
    assert row.last_error is None
    assert _decrypt_from_storage(row.access_token) == "day2_token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_state_success_to_failed_preserves_token(db_env):
    """Success → Failed: status/error updated, token preserved."""
    _, maker = db_env
    await _seed_token(maker, plain="day1_token", status="Success")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersConnectionError("broker down"),
    ):
        async with maker() as db:
            with pytest.raises(FyersConnectionError):
                await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Failed"
    assert "broker down" in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "day1_token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_state_failed_to_success_recovery(db_env):
    """Failed → Success: new token, status Success, last_error cleared."""
    _, maker = db_env
    await _seed_token(maker, plain="old", status="Failed", last_error="yesterday fail")

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="fresh_token",
    ):
        async with maker() as db:
            await generate_and_persist_fyers_token(db)

    row = await _get_row(maker)
    assert row is not None
    assert row.status == "Success"
    assert row.last_error is None
    assert _decrypt_from_storage(row.access_token) == "fresh_token"


# ===========================================================================
# Regression – existing save_access_token / mask helpers remain valid
# ===========================================================================


@pytest.mark.unit
def test_mask_token_regression_short_and_none():
    """Regression: _mask_token edge behavior used by CLI and history writes."""
    assert _mask_token(None) is None
    assert _mask_token("") is None
    short = _mask_token("short")
    assert short is not None
    assert "short" not in short or short == "*****" or short.startswith("*")
    long_masked = _mask_token("abcdefghijklmnop1234")
    assert long_masked is not None
    assert long_masked.endswith("1234")
    assert "abcdefghijklmnop" not in long_masked
