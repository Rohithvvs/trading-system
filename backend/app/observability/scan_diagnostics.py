"""
Forensic-grade scan diagnostics module.

Provides:
- scan_id correlation (UUID per scan)
- Structured logging helpers with consistent key=value format
- Scan-scoped counters for cache/fyers/failure tracking
- Token hashing for safe logging
- NO_DATA root cause analysis engine

This module is OBSERVABILITY ONLY — it does not modify any business logic.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import socket
import time
import traceback as traceback_module
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..utils.datetime_utils import parse_utc, utc_now

logger = logging.getLogger("app.scan_diagnostics")

# ---------------------------------------------------------------------------
# Global context — deployment / process identity
# ---------------------------------------------------------------------------
_PROCESS_START_TIME = utc_now().isoformat()
_PROCESS_PID = os.getpid()
_HOSTNAME = socket.gethostname()
_DEPLOYMENT_ID = os.getenv("RENDER_SERVICE_ID", os.getenv("RENDER_INSTANCE_ID", "local"))
_RENDER_INSTANCE = os.getenv("RENDER_INSTANCE_ID", "unknown")

def get_process_context() -> dict[str, Any]:
    """Return immutable process-level context for log enrichment."""
    return {
        "pid": _PROCESS_PID,
        "hostname": _HOSTNAME,
        "deployment_id": _DEPLOYMENT_ID,
        "render_instance": _RENDER_INSTANCE,
    }


# ---------------------------------------------------------------------------
# Token hashing — NEVER log raw tokens
# ---------------------------------------------------------------------------
def hash_token_prefix(token: str | None) -> str:
    """Return a safe hash of the first 10 chars of a token. Never logs raw token."""
    if not token:
        return "NO_TOKEN"
    prefix = token[:10]
    return hashlib.sha256(prefix.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ScanContext — per-scan correlation and counters
# ---------------------------------------------------------------------------
@dataclass
class ScanContext:
    """Holds all per-scan diagnostic counters and metadata.

    Created at SCAN_START, passed through the pipeline, emitted at SCAN_SUMMARY.
    """
    scan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_source: str = "unknown"  # manual / scheduler / api
    start_time: float = field(default_factory=time.perf_counter)
    start_timestamp: str = field(default_factory=lambda: utc_now().isoformat())
    universe: str = "unknown"
    symbols_requested: int = 0

    # Token state at scan start
    token_loaded: bool = False
    token_source: str = "unknown"  # memory / database / none
    token_saved_at: str | None = None
    token_age_minutes: float = 0.0

    # Cache counters
    cache_hits: int = 0
    cache_misses: int = 0

    # FYERS API counters
    fyers_success: int = 0
    fyers_failures: int = 0
    fyers_timeouts: int = 0
    fyers_unauthorized: int = 0
    fyers_empty_responses: int = 0
    fyers_rate_limited: int = 0

    # Symbol processing
    symbols_processed: int = 0
    symbols_failed: int = 0
    failure_reasons: Counter = field(default_factory=Counter)

    # Pipeline stage counters
    valid: int = 0
    eligible: int = 0
    matched: int = 0
    buy: int = 0
    watch: int = 0
    reject: int = 0

    # Data source failures
    data_source_failures: int = 0

    def elapsed_ms(self) -> int:
        """Return elapsed time since scan start in milliseconds."""
        return int((time.perf_counter() - self.start_time) * 1000)

    def base_fields(self) -> dict[str, Any]:
        """Return the base fields that EVERY log line during this scan must include."""
        ctx = get_process_context()
        return {
            "scan_id": self.scan_id,
            "pid": ctx["pid"],
            "hostname": ctx["hostname"],
            "deployment_id": ctx["deployment_id"],
            "timestamp": utc_now().isoformat(),
        }

    def format_log(self, event: str, **kwargs: Any) -> str:
        """Format a structured log line with base fields + extra kwargs."""
        parts = [f"event={event}"]
        for k, v in self.base_fields().items():
            parts.append(f"{k}={v}")
        for k, v in kwargs.items():
            parts.append(f"{k}={v}")
        return " | ".join(parts)

    def record_fyers_failure(self, reason: str) -> None:
        """Increment fyers failure counters based on reason category."""
        self.fyers_failures += 1
        reason_lower = reason.lower() if reason else "unknown"
        if "timeout" in reason_lower:
            self.fyers_timeouts += 1
            self.failure_reasons["timeout"] += 1
        elif "401" in reason_lower or "unauthorized" in reason_lower or "expired" in reason_lower or "invalid token" in reason_lower:
            self.fyers_unauthorized += 1
            self.failure_reasons["unauthorized"] += 1
        elif "rate limit" in reason_lower or "429" in reason_lower or "too many" in reason_lower:
            self.fyers_rate_limited += 1
            self.failure_reasons["rate_limit"] += 1
        elif "empty" in reason_lower or "no candle" in reason_lower:
            self.fyers_empty_responses += 1
            self.failure_reasons["empty_response"] += 1
        else:
            self.failure_reasons[reason[:80]] += 1

    def top_failure_reasons(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the top N failure reasons with counts."""
        return [{"reason": reason, "count": count} for reason, count in self.failure_reasons.most_common(n)]


# ---------------------------------------------------------------------------
# Module-level current scan context (thread-safe via scanner's sequential nature)
# ---------------------------------------------------------------------------
_current_scan: ScanContext | None = None


def begin_scan(trigger_source: str = "unknown", universe: str = "unknown", symbol_count: int = 0) -> ScanContext:
    """Create a new ScanContext and set it as the current active scan."""
    global _current_scan
    ctx = ScanContext(
        trigger_source=trigger_source,
        universe=universe,
        symbols_requested=symbol_count,
    )
    _current_scan = ctx

    log_msg = ctx.format_log(
        "SCAN_START",
        trigger=trigger_source,
        universe=universe,
        symbols=symbol_count,
        render_instance=_RENDER_INSTANCE,
    )
    logger.info(log_msg)
    return ctx


def get_current_scan() -> ScanContext | None:
    """Return the currently active scan context, if any."""
    return _current_scan


def end_scan(ctx: ScanContext) -> None:
    """Emit SCAN_SUMMARY and clear the current scan context."""
    global _current_scan
    duration_ms = ctx.elapsed_ms()

    summary = ctx.format_log(
        "SCAN_SUMMARY",
        duration_ms=duration_ms,
        symbols_requested=ctx.symbols_requested,
        symbols_processed=ctx.symbols_processed,
        cache_hits=ctx.cache_hits,
        cache_misses=ctx.cache_misses,
        fyers_success=ctx.fyers_success,
        fyers_failures=ctx.fyers_failures,
        symbols_failed=ctx.symbols_failed,
        valid=ctx.valid,
        eligible=ctx.eligible,
        matched=ctx.matched,
        buy=ctx.buy,
        watch=ctx.watch,
        reject=ctx.reject,
        data_source_failures=ctx.data_source_failures,
    )
    logger.info(summary)

    # NO_DATA root cause analysis
    if ctx.valid == 0 and ctx.symbols_requested > 0:
        top_reasons = ctx.top_failure_reasons()
        top_reasons_str = "; ".join(f"{r['reason']}={r['count']}" for r in top_reasons) if top_reasons else "no_data_collected"
        root_cause = ctx.format_log(
            "NO_DATA_ROOT_CAUSE",
            symbols_requested=ctx.symbols_requested,
            symbols_processed=ctx.symbols_processed,
            symbols_failed=ctx.symbols_failed,
            fyers_failures=ctx.fyers_failures,
            fyers_timeouts=ctx.fyers_timeouts,
            fyers_unauthorized=ctx.fyers_unauthorized,
            fyers_rate_limited=ctx.fyers_rate_limited,
            fyers_empty_responses=ctx.fyers_empty_responses,
            token_loaded=ctx.token_loaded,
            token_source=ctx.token_source,
            token_saved_at=ctx.token_saved_at,
            cache_hits=ctx.cache_hits,
            cache_misses=ctx.cache_misses,
            top_failure_reasons=top_reasons_str,
        )
        logger.error(root_cause)

    _current_scan = None


# ---------------------------------------------------------------------------
# Event-specific log helpers
# ---------------------------------------------------------------------------

def log_token_status(
    ctx: ScanContext,
    token_exists: bool,
    token_source: str,
    token_saved_at: str | None,
    token_age_minutes: float,
    token_hash: str,
) -> None:
    """Log FYERS_TOKEN_STATUS at scan start."""
    ctx.token_loaded = token_exists
    ctx.token_source = token_source
    ctx.token_saved_at = token_saved_at
    ctx.token_age_minutes = token_age_minutes

    msg = ctx.format_log(
        "FYERS_TOKEN_STATUS",
        token_exists=token_exists,
        token_source=token_source,
        token_saved_at=token_saved_at or "N/A",
        token_age_minutes=round(token_age_minutes, 1),
        token_hash=token_hash,
    )
    logger.info(msg)


def log_fyers_request(ctx: ScanContext, symbol: str, endpoint: str, from_date: str, to_date: str, attempt: int) -> None:
    """Log FYERS_REQUEST before each FYERS API call."""
    msg = ctx.format_log(
        "FYERS_REQUEST",
        symbol=symbol,
        endpoint=endpoint,
        from_date=from_date,
        to_date=to_date,
        attempt=attempt,
    )
    logger.info(msg)


def log_fyers_response(ctx: ScanContext, symbol: str, candles_returned: int, response_time_ms: int, success: bool = True) -> None:
    """Log FYERS_RESPONSE after successful API response."""
    if success:
        ctx.fyers_success += 1
    msg = ctx.format_log(
        "FYERS_RESPONSE",
        symbol=symbol,
        success=success,
        candles_returned=candles_returned,
        response_time_ms=response_time_ms,
    )
    logger.info(msg)


def log_fyers_failure(ctx: ScanContext, symbol: str, exception_type: str, exception_message: str, retry_count: int) -> None:
    """Log FYERS_FAILURE on API error."""
    ctx.record_fyers_failure(exception_message)
    msg = ctx.format_log(
        "FYERS_FAILURE",
        symbol=symbol,
        exception_type=exception_type,
        exception_message=str(exception_message)[:500],
        retry_count=retry_count,
    )
    logger.error(msg)


def log_cache_lookup(ctx: ScanContext, symbol: str, hit: bool, available_candles: int = 0, required_candles: int = 0) -> None:
    """Log CACHE_HIT or CACHE_MISS."""
    if hit:
        ctx.cache_hits += 1
        event = "CACHE_HIT"
    else:
        ctx.cache_misses += 1
        event = "CACHE_MISS"
    msg = ctx.format_log(
        event,
        symbol=symbol,
        available_candles=available_candles,
        required_candles=required_candles,
    )
    logger.info(msg)


def log_data_source_selection(ctx: ScanContext, symbol: str, selected_source: str, reason: str, cache_available: bool = False, cache_candles: int = 0, fyers_available: bool = False) -> None:
    """Log DATA_SOURCE_SELECTION for each symbol."""
    if selected_source == "none":
        ctx.data_source_failures += 1
    msg = ctx.format_log(
        "DATA_SOURCE_SELECTION",
        symbol=symbol,
        cache_available=cache_available,
        cache_candles=cache_candles,
        fyers_available=fyers_available,
        selected_source=selected_source,
        reason=reason,
    )
    logger.info(msg)


def log_symbol_failure(ctx: ScanContext, symbol: str, stage: str, exc: Exception | None = None) -> None:
    """Log SYMBOL_PROCESSING_FAILURE with full traceback."""
    ctx.symbols_failed += 1
    tb = ""
    exc_type = "unknown"
    exc_msg = "unknown"
    if exc:
        exc_type = type(exc).__name__
        exc_msg = str(exc)[:500]
        tb = traceback_module.format_exception(type(exc), exc, exc.__traceback__)
        tb = "".join(tb)[-2000:]  # cap traceback length

    msg = ctx.format_log(
        "SYMBOL_PROCESSING_FAILURE",
        symbol=symbol,
        stage=stage,
        exception_type=exc_type,
        exception_message=exc_msg,
    )
    logger.error(msg)
    if tb:
        logger.error(f"SYMBOL_TRACEBACK | scan_id={ctx.scan_id} | symbol={symbol} | traceback:\n{tb}")


def log_pipeline_stage(ctx: ScanContext, stage_name: str, stage_number: int, input_count: int, output_count: int, failure_count: int, duration_ms: int) -> None:
    """Log PIPELINE_STAGE completion."""
    msg = ctx.format_log(
        "PIPELINE_STAGE",
        stage_name=stage_name,
        stage_number=stage_number,
        input_count=input_count,
        output_count=output_count,
        failure_count=failure_count,
        duration_ms=duration_ms,
    )
    logger.info(msg)


def log_scan_persist(ctx: ScanContext, event: str, buy_count: int = 0, watch_count: int = 0, reject_count: int = 0, rows_written: int = 0) -> None:
    """Log SCAN_PERSIST_BEGIN / SCAN_PERSIST_SUCCESS / SCAN_PERSIST_VERIFY."""
    msg = ctx.format_log(
        event,
        buy_count=buy_count,
        watch_count=watch_count,
        reject_count=reject_count,
        rows_written=rows_written,
    )
    logger.info(msg)


def log_dashboard_request(scan_id: str | None, endpoint: str, returned_records: int, query_duration_ms: int) -> None:
    """Log DASHBOARD_SCAN_LOAD or DASHBOARD_EMPTY_RESULT."""
    event = "DASHBOARD_SCAN_LOAD" if returned_records > 0 else "DASHBOARD_EMPTY_RESULT"
    parts = [
        f"event={event}",
        f"scan_id={scan_id or 'none'}",
        f"endpoint={endpoint}",
        f"returned_records={returned_records}",
        f"query_duration_ms={query_duration_ms}",
        f"pid={_PROCESS_PID}",
        f"timestamp={utc_now().isoformat()}",
    ]
    logger.info(" | ".join(parts))


def log_scheduler_event(event: str, job_name: str, **kwargs: Any) -> None:
    """Log SCHEDULER_REGISTER / SCHEDULER_TRIGGER / SCHEDULER_SKIP / SCHEDULER_COMPLETE."""
    parts = [
        f"event={event}",
        f"job_name={job_name}",
        f"pid={_PROCESS_PID}",
        f"timestamp={utc_now().isoformat()}",
    ]
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    logger.info(" | ".join(parts))


def log_db_pool_status(pool_size: int = 0, checked_out: int = 0, overflow: int = 0, checkedin: int = 0) -> None:
    """Log DB_POOL_STATUS."""
    parts = [
        f"event=DB_POOL_STATUS",
        f"pool_size={pool_size}",
        f"checked_out={checked_out}",
        f"overflow={overflow}",
        f"checkedin={checkedin}",
        f"pid={_PROCESS_PID}",
        f"timestamp={utc_now().isoformat()}",
    ]
    logger.info(" | ".join(parts))


def log_process_event(event: str, reason: str = "") -> None:
    """Log PROCESS_START / PROCESS_STOP."""
    parts = [
        f"event={event}",
        f"pid={_PROCESS_PID}",
        f"hostname={_HOSTNAME}",
        f"deployment_id={_DEPLOYMENT_ID}",
        f"render_instance={_RENDER_INSTANCE}",
        f"timestamp={utc_now().isoformat()}",
        f"startup_timestamp={_PROCESS_START_TIME}",
    ]
    if reason:
        parts.append(f"reason={reason}")
    logger.info(" | ".join(parts))


def log_incident_summary(ctx: ScanContext, token_status: str, cache_status: str, fyers_status: str, persistence_status: str, overall_health: str) -> None:
    """Log INCIDENT_DIAGNOSTIC_SUMMARY at scan completion."""
    msg = ctx.format_log(
        "INCIDENT_DIAGNOSTIC_SUMMARY",
        token_status=token_status,
        cache_status=cache_status,
        fyers_status=fyers_status,
        persistence_status=persistence_status,
        overall_health=overall_health,
        duration_ms=ctx.elapsed_ms(),
    )
    logger.info(msg)


def log_scan_environment(
    ctx: ScanContext,
    token_loaded: bool,
    token_source: str,
    token_saved_at: str | None,
    token_age_minutes: float,
    token_hash: str,
    app_uptime_minutes: float,
    market_open: bool,
    market_session: str,
    exchange_time: str,
    weekday: str,
    db_connected: bool,
    pool_size: int,
    checked_out: int,
    overflow: int,
    fyers_validation_result: str,
    fyers_validation_latency_ms: int,
    last_scan_timestamp: str | None,
    last_scan_result: str,
    last_scan_source: str,
    minutes_since_last_scan: float,
    cache_enabled: bool,
    cache_entries: int,
    cache_health: str,
) -> None:
    """Log SCAN_ENVIRONMENT and emit warnings for stale tokens or recent restarts."""
    # 1. Emit warnings
    if app_uptime_minutes < 15.0:
        logger.warning(f"RECENT_RENDER_RESTART | uptime_minutes={app_uptime_minutes:.1f}")
        
    if token_saved_at:
        try:
            token_saved_dt = parse_utc(token_saved_at)
            startup_dt = parse_utc(_PROCESS_START_TIME)
            if token_saved_dt is not None and startup_dt is not None and token_saved_dt > startup_dt:
                logger.warning(
                    "TOKEN_POSSIBLY_STALE | token_saved_at=%s | app_started_at=%s",
                    token_saved_at,
                    _PROCESS_START_TIME,
                )
        except Exception:
            # Observability only — never fail the scan because of parse issues
            logger.debug("token_saved_at parse failed for SCAN_ENVIRONMENT warning", exc_info=True)

    if token_source == "memory" and token_age_minutes < app_uptime_minutes:
        logger.warning(f"PROCESS_RUNNING_OLD_TOKEN | token_age_minutes={token_age_minutes:.1f} | app_uptime_minutes={app_uptime_minutes:.1f} | token_source=memory")

    # 2. Emit environment log
    parts = [
        "SCAN_ENVIRONMENT",
        f"scan_id={ctx.scan_id}",
        f"trigger={ctx.trigger_source}",
        f"token_source={token_source}",
        f"token_saved_at={token_saved_at or 'none'}",
        f"token_age_minutes={token_age_minutes:.1f}",
        f"process_id={_PROCESS_PID}",
        f"deployment_id={_DEPLOYMENT_ID}",
        f"app_uptime_minutes={app_uptime_minutes:.1f}",
        f"market_open={str(market_open).lower()}",
        f"market_session={market_session}",
        f"database_connected={str(db_connected).lower()}",
        f"pool_size={pool_size}",
        f"checked_out={checked_out}",
        f"fyers_validation_result={fyers_validation_result}",
        f"last_scan_result={last_scan_result}",
        f"minutes_since_last_scan={minutes_since_last_scan:.1f}"
    ]
    logger.info(" | ".join(parts))

