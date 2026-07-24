"""Automatic Access-Token → Market Scanner bootstrap workflow.

Runs on application startup (singleton worker) and can also be invoked after
successful token generation endpoints:

1. Check whether today's FYERS access token already exists and is valid.
2. If missing/expired/invalid → generate, validate, persist, update cache.
3. Only after a confirmed good token → auto-trigger Market Scanner once/day.
4. On token failure → do NOT start scanner; log, surface infra status, rely on
   existing generation retry policy inside ``fyers_token.generate_fyers_access_token``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.token_scanner_bootstrap")

IST = ZoneInfo("Asia/Kolkata")

# Auto-scanner allowed window (IST). Wider than cash session so pre-market
# token gen (e.g. 08:30) can still start the daily scan.
_SCAN_WINDOW_START = time(8, 30)
_SCAN_WINDOW_END = time(22, 0)

# Feature flags (env-overridable)
_AUTO_ENABLED = os.getenv("AUTO_TOKEN_SCANNER_ON_STARTUP", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_AUTO_SCAN_ENABLED = os.getenv("AUTO_SCANNER_AFTER_TOKEN", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Process-local guards (once per process day; DB is still source of truth across restarts)
_LOCK = threading.Lock()
_BOOTSTRAP_RUNNING = False
_TOKEN_OK_DATE: date | None = None
_SCAN_TRIGGERED_DATE: date | None = None


@dataclass
class BootstrapResult:
    """Outcome of the token→scanner bootstrap workflow."""

    token_ready: bool = False
    token_source: str = "none"  # existing_today | generated | failed | skipped
    token_saved_at: str | None = None
    scanner_started: bool = False
    scanner_skipped_reason: str | None = None
    error: str | None = None
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_ready": self.token_ready,
            "token_source": self.token_source,
            "token_saved_at": self.token_saved_at,
            "scanner_started": self.scanner_started,
            "scanner_skipped_reason": self.scanner_skipped_reason,
            "error": self.error,
            "steps": list(self.steps),
        }


def _now_ist() -> datetime:
    return datetime.now(IST)


def _today_ist() -> date:
    return _now_ist().date()


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_ist_date(dt: datetime | None, day: date | None = None) -> bool:
    """True when *dt* falls on *day* in Asia/Kolkata (default: today IST)."""
    if dt is None:
        return False
    day = day or _today_ist()
    utc = _as_utc(dt)
    if utc is None:
        return False
    return utc.astimezone(IST).date() == day


def _within_scan_window(now: datetime | None = None) -> bool:
    now = now or _now_ist()
    t = now.timetz().replace(tzinfo=None) if now.tzinfo else now.time()
    # Compare as plain times against window bounds
    local = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    return _SCAN_WINDOW_START <= local.time() <= _SCAN_WINDOW_END


def _record_infra(
    *,
    status: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Surface bootstrap state in diagnostics + structured logs (infra status)."""
    try:
        from .diagnostics_service import diagnostics

        diagnostics.record_token_scanner_bootstrap(
            {
                "status": status,
                "message": message,
                "detail": detail or {},
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        logger.exception("Failed to record bootstrap status on diagnostics")

    try:
        from .logger_service import logger_service

        level = "ERROR" if status in {"token_failed", "scanner_failed", "error"} else "INFO"
        if level == "ERROR":
            logger_service.log_error(
                module="TokenScannerBootstrap",
                message=message,
                source="JOB",
                endpoint="token_scanner_bootstrap",
                structured_data={"status": status, **(detail or {})},
            )
        else:
            logger_service.log_info(
                module="TokenScannerBootstrap",
                message=message,
                source="JOB",
                endpoint="token_scanner_bootstrap",
                structured_data={"status": status, **(detail or {})},
            )
    except Exception:
        # logger_service may not be fully started during early boot
        pass

    try:
        # Fire-and-forget DB log when an event loop is running
        from .db_logger import log_to_db

        loop = asyncio.get_running_loop()
        level = "ERROR" if status in {"token_failed", "scanner_failed", "error"} else "INFO"
        loop.create_task(
            log_to_db(
                level=level,
                module="TokenScannerBootstrap",
                message=f"[{status}] {message}",
                endpoint="token_scanner_bootstrap",
            )
        )
    except RuntimeError:
        # No running loop — skip async DB log
        pass
    except Exception:
        logger.debug("db_logger unavailable for bootstrap status", exc_info=True)


async def _live_validate_token(token: str, *, timeout: float = 15.0) -> None:
    """Validate token against FYERS; raises on failure."""
    from .fyers_service import FyersService

    logger.info("Token validated | step=begin | timeout_sec=%.1f", timeout)
    fyers = FyersService()
    await asyncio.wait_for(
        asyncio.to_thread(fyers.validate_token_sync, token),
        timeout=timeout,
    )
    logger.info("Token validated | step=success")


async def check_todays_valid_token(db: AsyncSession) -> dict[str, Any]:
    """Return whether a valid access token for *today* (IST) is available.

    A token counts as "today's valid" when:
    - ciphertext is present and decryptable
    - row is active
    - ``access_token_saved_at`` is today IST
    - JWT ``exp`` (if present) is still in the future
    - live FYERS validation succeeds
    """
    from . import token_service

    result: dict[str, Any] = {
        "valid": False,
        "reason": "unknown",
        "token": None,
        "saved_at": None,
        "expires_at": None,
    }

    row = await token_service.get_fyers_token_row(db)
    if row is None or not token_service._has_usable_stored_token(row):
        result["reason"] = "missing"
        logger.info(
            "STARTUP_TOKEN_CHECK | valid=false | reason=missing | "
            "today_ist=%s",
            _today_ist().isoformat(),
        )
        return result

    plain = token_service._decrypt_from_storage(row.access_token)
    if not plain:
        result["reason"] = "decrypt_failed"
        logger.warning("STARTUP_TOKEN_CHECK | valid=false | reason=decrypt_failed")
        return result

    saved_at = token_service._ensure_utc(row.access_token_saved_at)
    result["saved_at"] = saved_at.isoformat() if saved_at else None

    if not _is_ist_date(saved_at):
        result["reason"] = "not_today"
        logger.info(
            "STARTUP_TOKEN_CHECK | valid=false | reason=not_today | saved_at=%s | today_ist=%s",
            result["saved_at"],
            _today_ist().isoformat(),
        )
        return result

    expires_at = row.expires_at or token_service._decode_jwt_expiry(plain)
    expires_at = token_service._ensure_utc(expires_at)
    result["expires_at"] = expires_at.isoformat() if expires_at else None
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        result["reason"] = "expired"
        logger.info(
            "STARTUP_TOKEN_CHECK | valid=false | reason=expired | expires_at=%s",
            result["expires_at"],
        )
        return result

    # Ensure cache is warm for downstream consumers
    try:
        token_service._set_token_cache(plain, saved_at)
        logger.info("Memory cache updated | step=existing_token_warm")
    except Exception as cache_exc:
        logger.error(
            "Memory cache update failure | step=existing_token_warm | error=%s",
            cache_exc,
            exc_info=True,
        )
        # Non-fatal: DB still has the token; get_current_access_token can reload.

    try:
        await _live_validate_token(plain, timeout=10.0)
    except Exception as val_exc:
        result["reason"] = f"validation_failed:{type(val_exc).__name__}"
        logger.error(
            "STARTUP_TOKEN_CHECK | valid=false | reason=validation_failed | error=%s",
            val_exc,
        )
        return result

    result["valid"] = True
    result["reason"] = "ok"
    result["token"] = plain
    logger.info(
        "STARTUP_TOKEN_CHECK | valid=true | reason=ok | saved_at=%s | expires_at=%s",
        result["saved_at"],
        result["expires_at"],
    )
    return result


async def has_scanner_completed_for_todays_token(
    db: AsyncSession,
    token_saved_at: datetime | None,
) -> bool:
    """True when a completed scan already exists for today's token (IST day)."""
    try:
        from .latest_scan_service import LatestScanService

        latest = await LatestScanService(db).get_latest_completed_scan()
        if not latest:
            return False
        completed_raw = latest.get("last_scan_completed_at") or latest.get("scan_timestamp")
        if not completed_raw:
            return False
        completed_at = datetime.fromisoformat(str(completed_raw).replace("Z", "+00:00"))
        completed_at = _as_utc(completed_at)
        if not _is_ist_date(completed_at):
            return False
        if token_saved_at is not None:
            ts = _as_utc(token_saved_at)
            if ts is not None and completed_at < ts:
                # Scan finished before today's token was saved — not for this token
                return False
        return True
    except Exception as exc:
        logger.warning(
            "SCANNER_TODAY_CHECK_FAILED | error=%s | treating_as_not_completed",
            exc,
        )
        return False


async def ensure_daily_access_token(db: AsyncSession, result: BootstrapResult) -> str | None:
    """Ensure a valid today's token exists; generate if needed. Returns plaintext token or None."""
    from . import token_service

    check = await check_todays_valid_token(db)
    if check["valid"] and check.get("token"):
        result.token_ready = True
        result.token_source = "existing_today"
        result.token_saved_at = check.get("saved_at")
        result.steps.append("token_existing_valid")
        logger.info(
            "Token generation skipped | reason=todays_valid_token_exists | saved_at=%s",
            check.get("saved_at"),
        )
        _record_infra(
            status="token_ready",
            message="Today's valid access token already present",
            detail={"source": "existing_today", "saved_at": check.get("saved_at")},
        )
        return check["token"]

    logger.info(
        "Token generation started | reason=%s | today_ist=%s",
        check.get("reason"),
        _today_ist().isoformat(),
    )
    result.steps.append(f"token_generate_needed:{check.get('reason')}")
    _record_infra(
        status="token_generating",
        message=f"Generating daily access token (prior check: {check.get('reason')})",
        detail={"reason": check.get("reason")},
    )

    try:
        gen = await token_service.generate_and_persist_fyers_token(db)
        logger.info(
            "Token generated successfully | status=%s | preview=%s | saved_at=%s",
            gen.get("status"),
            gen.get("token_preview"),
            gen.get("saved_at"),
        )
        result.steps.append("token_generated")
        result.token_saved_at = gen.get("saved_at")
        logger.info("Token saved to database | saved_at=%s", gen.get("saved_at"))
        result.steps.append("token_saved")
        logger.info("Memory cache updated | step=post_generation")
        result.steps.append("cache_updated")
    except Exception as gen_exc:
        err = f"{type(gen_exc).__name__}: {gen_exc}"
        logger.error(
            "Token generation failure | error=%s | scanner_will_not_start=true",
            err,
            exc_info=True,
        )
        result.error = err
        result.token_source = "failed"
        result.steps.append("token_generate_failed")
        _record_infra(
            status="token_failed",
            message=f"Daily access token generation failed: {err}",
            detail={"error_type": type(gen_exc).__name__},
        )
        # Retry policy lives inside generate_fyers_access_token (max 3, backoff).
        # No outer retry here to avoid double-budget exhaustion.
        return None

    # Load plaintext for validation + scanner
    try:
        plain = await token_service.get_current_access_token(db)
    except Exception as load_exc:
        logger.error(
            "Token load after save failure | error=%s",
            load_exc,
            exc_info=True,
        )
        result.error = f"load_after_save:{load_exc}"
        result.token_source = "failed"
        _record_infra(
            status="token_failed",
            message=f"Token saved but could not be reloaded: {load_exc}",
        )
        return None

    if not plain:
        logger.error("Token generation reported success but no token available after reload")
        result.error = "empty_after_save"
        result.token_source = "failed"
        _record_infra(
            status="token_failed",
            message="Token generation reported success but token is empty after reload",
        )
        return None

    try:
        await _live_validate_token(plain, timeout=15.0)
        result.steps.append("token_validated")
    except Exception as val_exc:
        err = f"{type(val_exc).__name__}: {val_exc}"
        logger.error(
            "Token validation failure after generation | error=%s | scanner_will_not_start=true",
            err,
            exc_info=True,
        )
        result.error = err
        result.token_source = "failed"
        result.steps.append("token_validate_failed")
        try:
            token_service._clear_token_cache()
        except Exception:
            pass
        _record_infra(
            status="token_failed",
            message=f"Generated token failed live validation: {err}",
            detail={"error_type": type(val_exc).__name__},
        )
        return None

    result.token_ready = True
    result.token_source = "generated"
    _record_infra(
        status="token_ready",
        message="Daily access token generated, validated, saved, and cached",
        detail={"saved_at": result.token_saved_at, "source": "generated"},
    )
    return plain


async def maybe_trigger_auto_scanner(
    db: AsyncSession,
    *,
    token_saved_at: datetime | None,
    result: BootstrapResult,
    trigger_source: str = "startup_token_bootstrap",
) -> bool:
    """Start Market Scanner once if not already done for today's token."""
    global _SCAN_TRIGGERED_DATE

    if not _AUTO_SCAN_ENABLED:
        result.scanner_skipped_reason = "auto_scanner_disabled"
        logger.info("Scanner auto-start skipped | reason=AUTO_SCANNER_AFTER_TOKEN disabled")
        return False

    if not result.token_ready:
        result.scanner_skipped_reason = "token_not_ready"
        logger.info("Scanner auto-start skipped | reason=token_not_ready")
        return False

    today = _today_ist()
    with _LOCK:
        if _SCAN_TRIGGERED_DATE == today:
            result.scanner_skipped_reason = "already_triggered_this_process_today"
            logger.info(
                "Scanner auto-start skipped | reason=already_triggered_this_process_today | day=%s",
                today.isoformat(),
            )
            return False

    try:
        from .diagnostics_service import diagnostics

        if diagnostics.last_scan_status == "RUNNING":
            result.scanner_skipped_reason = "scanner_already_running"
            logger.info("Scanner auto-start skipped | reason=scanner_already_running")
            return False
    except Exception:
        pass

    if await has_scanner_completed_for_todays_token(db, token_saved_at):
        result.scanner_skipped_reason = "scanner_already_completed_today"
        logger.info(
            "Scanner auto-start skipped | reason=scanner_already_completed_for_todays_token"
        )
        with _LOCK:
            _SCAN_TRIGGERED_DATE = today
        return False

    if not _within_scan_window():
        result.scanner_skipped_reason = "outside_scan_window"
        logger.info(
            "Scanner auto-start skipped | reason=outside_scan_window | "
            "window=%s-%s IST | now=%s",
            _SCAN_WINDOW_START.strftime("%H:%M"),
            _SCAN_WINDOW_END.strftime("%H:%M"),
            _now_ist().isoformat(),
        )
        return False

    # Schedule scanner without blocking the bootstrap task. Import of
    # automated_screening_job is deferred inside the task to avoid circular
    # imports with app.main at module load time.
    try:
        logger.info(
            "Scanner started automatically | trigger_source=%s | token_source=%s",
            trigger_source,
            result.token_source,
        )
        result.steps.append("scanner_start_scheduled")
        _record_infra(
            status="scanner_starting",
            message="Market Scanner started automatically after access token ready",
            detail={
                "trigger_source": trigger_source,
                "token_source": result.token_source,
            },
        )

        async def _run_and_log() -> None:
            try:
                # Late import: main ↔ bootstrap would cycle if done at module top.
                from ..main import automated_screening_job

                await automated_screening_job()
                logger.info("Scanner completed | trigger_source=%s", trigger_source)
                _record_infra(
                    status="scanner_completed",
                    message="Automatic Market Scanner completed",
                    detail={"trigger_source": trigger_source},
                )
            except Exception as scan_exc:
                logger.error(
                    "Scanner failed | trigger_source=%s | error=%s",
                    trigger_source,
                    scan_exc,
                    exc_info=True,
                )
                _record_infra(
                    status="scanner_failed",
                    message=f"Automatic Market Scanner failed: {scan_exc}",
                    detail={
                        "trigger_source": trigger_source,
                        "error_type": type(scan_exc).__name__,
                    },
                )

        asyncio.create_task(_run_and_log(), name="auto-scanner-after-token")
        with _LOCK:
            _SCAN_TRIGGERED_DATE = today
        result.scanner_started = True
        result.steps.append("scanner_started")
        return True
    except Exception as start_exc:
        logger.error(
            "Scanner start failure | error=%s",
            start_exc,
            exc_info=True,
        )
        result.scanner_skipped_reason = f"start_error:{start_exc}"
        result.error = str(start_exc)
        _record_infra(
            status="scanner_failed",
            message=f"Failed to schedule automatic scanner: {start_exc}",
        )
        return False


async def run_token_to_scanner_bootstrap(
    *,
    trigger_source: str = "startup",
) -> BootstrapResult:
    """Full workflow: ensure today's token → optionally auto-start scanner.

    Safe to call multiple times: process lock + IST day checks + DB state.
    """
    global _BOOTSTRAP_RUNNING, _TOKEN_OK_DATE

    result = BootstrapResult()

    if not _AUTO_ENABLED and trigger_source == "startup":
        result.scanner_skipped_reason = "bootstrap_disabled"
        logger.info(
            "Token→scanner bootstrap skipped | reason=AUTO_TOKEN_SCANNER_ON_STARTUP disabled"
        )
        return result

    with _LOCK:
        if _BOOTSTRAP_RUNNING:
            result.scanner_skipped_reason = "bootstrap_already_running"
            logger.info("Token→scanner bootstrap skipped | reason=already_running")
            return result
        _BOOTSTRAP_RUNNING = True

    logger.info(
        "TOKEN_TO_SCANNER_BOOTSTRAP | outcome=start | trigger_source=%s | today_ist=%s",
        trigger_source,
        _today_ist().isoformat(),
    )
    _record_infra(
        status="bootstrap_started",
        message="Automatic token→scanner workflow started",
        detail={"trigger_source": trigger_source},
    )

    try:
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            plain = await ensure_daily_access_token(db, result)
            if not plain:
                logger.warning(
                    "TOKEN_TO_SCANNER_BOOTSTRAP | outcome=token_failed | "
                    "scanner_started=false | error=%s",
                    result.error,
                )
                return result

            with _LOCK:
                _TOKEN_OK_DATE = _today_ist()

            token_saved_at: datetime | None = None
            if result.token_saved_at:
                try:
                    token_saved_at = datetime.fromisoformat(
                        str(result.token_saved_at).replace("Z", "+00:00")
                    )
                    token_saved_at = _as_utc(token_saved_at)
                except Exception:
                    token_saved_at = None
            if token_saved_at is None:
                try:
                    from . import token_service

                    row = await token_service.get_fyers_token_row(db)
                    if row and row.access_token_saved_at:
                        token_saved_at = token_service._ensure_utc(row.access_token_saved_at)
                except Exception:
                    pass

            await maybe_trigger_auto_scanner(
                db,
                token_saved_at=token_saved_at,
                result=result,
                trigger_source=trigger_source,
            )

        logger.info(
            "TOKEN_TO_SCANNER_BOOTSTRAP | outcome=done | token_ready=%s | "
            "token_source=%s | scanner_started=%s | skip=%s",
            result.token_ready,
            result.token_source,
            result.scanner_started,
            result.scanner_skipped_reason,
        )
        _record_infra(
            status="bootstrap_done",
            message="Automatic token→scanner workflow finished",
            detail=result.to_dict(),
        )
        return result
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "TOKEN_TO_SCANNER_BOOTSTRAP | outcome=error | error=%s",
            result.error,
        )
        _record_infra(
            status="error",
            message=f"Token→scanner bootstrap crashed: {result.error}",
        )
        return result
    finally:
        with _LOCK:
            _BOOTSTRAP_RUNNING = False


def schedule_startup_bootstrap(app_state: Any | None = None) -> Optional[asyncio.Task]:
    """Schedule the bootstrap workflow as a background task (non-blocking startup)."""
    if not _AUTO_ENABLED:
        logger.info(
            "Startup token→scanner bootstrap not scheduled | "
            "AUTO_TOKEN_SCANNER_ON_STARTUP=false"
        )
        return None

    async def _runner() -> None:
        try:
            await run_token_to_scanner_bootstrap(trigger_source="startup")
        except Exception:
            logger.exception("Unhandled error in startup token→scanner bootstrap task")

    try:
        task = asyncio.create_task(_runner(), name="token-scanner-bootstrap")
        logger.info("Startup token→scanner bootstrap task scheduled")
        if app_state is not None:
            try:
                app_state.token_scanner_bootstrap_task = task
            except Exception:
                pass
        return task
    except Exception as exc:
        logger.error("Failed to schedule startup bootstrap: %s", exc, exc_info=True)
        return None


def reset_bootstrap_guards_for_tests() -> None:
    """Test helper — clear process-local once-per-day guards."""
    global _BOOTSTRAP_RUNNING, _TOKEN_OK_DATE, _SCAN_TRIGGERED_DATE
    with _LOCK:
        _BOOTSTRAP_RUNNING = False
        _TOKEN_OK_DATE = None
        _SCAN_TRIGGERED_DATE = None
