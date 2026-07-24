import asyncio
import time
import logging
import uuid
from ..agents import RouterAgent
from ..db.session import AsyncSessionLocal
from ..db.scan_store import save_latest_scan
from ..services.latest_scan_service import LatestScanService
from ..utils import sanitize_for_json
from ..schemas import ScreenerRequest
from ..services.scanner_cache import get_cached_scanner_result, cache_scanner_result
from ..services.lock_service import DistributedLockService, LockAcquisitionError

logger = logging.getLogger("app.services.scan_execution_service")


class _ScanState:
    """Thread-safe scan state shared between the scan task and heartbeat sender."""

    def __init__(self):
        self.stage: str = "Initializing..."
        self.progress: int = 0
        self.current_symbol: str = ""
        self.done: int = 0
        self.remaining: int = 0
        self.total: int = 0

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, v)

    def snapshot(self) -> dict:
        return {
            "stage": self.stage,
            "progress": self.progress,
            "current_symbol": self.current_symbol,
            "done": self.done,
            "remaining": self.remaining,
            "total": self.total,
        }


# Global scan state — only one scan runs at a time (distributed lock enforces this)
_scan_state = _ScanState()


class ScanExecutionService:

    _active_scan_start: float | None = None
    _active_scan_stage: str = "Initializing..."

    @staticmethod
    async def _emit(progress_queue: asyncio.Queue | None, payload: dict) -> None:
        """Push a progress/result event; never raise into the scan worker."""
        if progress_queue is None:
            return
        try:
            progress_queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                # Drop oldest and retry once so the UI is never starved.
                _ = progress_queue.get_nowait()
                progress_queue.put_nowait(payload)
            except Exception:
                logger.warning("[SCAN] progress_queue full; dropped event stage=%s", payload.get("stage"))
        except Exception as exc:
            logger.warning("[SCAN] progress emit failed: %s", exc)

    @staticmethod
    async def _heartbeat_sender(progress_queue: asyncio.Queue | None, scan_id: str):
        """Emit heartbeat progress every 5s so UI never freezes at Connecting..."""
        import time as _time

        start = _time.monotonic()
        # Immediate first pulse so clients leave "Connecting data feed..." quickly.
        state = _scan_state.snapshot()
        await ScanExecutionService._emit(
            progress_queue,
            {
                "status": "heartbeat",
                "stage": state["stage"] or "Connecting data feed...",
                "progress": max(int(state["progress"] or 0), 2),
                "heartbeat": True,
                "elapsed": 0,
                "scan_id": scan_id,
                "current_symbol": state["current_symbol"],
                "done": state["done"],
                "remaining": state["remaining"],
            },
        )
        while True:
            await asyncio.sleep(5.0)
            if progress_queue is None:
                break
            elapsed = int(_time.monotonic() - start)
            state = _scan_state.snapshot()
            msg = {
                "status": "heartbeat",
                "stage": state["stage"] or "Scanning...",
                "progress": int(state["progress"] or 0),
                "heartbeat": True,
                "elapsed": elapsed,
                "scan_id": scan_id,
                "current_symbol": state["current_symbol"],
                "done": state["done"],
                "remaining": state["remaining"],
            }
            if elapsed > 0 and elapsed % 30 == 0 and int(state["progress"] or 0) < 15:
                msg["stage"] = f"{state['stage']} (waiting for broker / market data...)"
                logger.warning(
                    "[SCAN] slow_progress | scan_id=%s | elapsed=%ss | stage=%s | progress=%s",
                    scan_id,
                    elapsed,
                    state["stage"],
                    state["progress"],
                )
            await ScanExecutionService._emit(progress_queue, msg)

    @staticmethod
    async def execute_scan(
        payload: ScreenerRequest,
        progress_queue: asyncio.Queue | None,
        trigger_source: str = "ui",
    ):
        scan_id = str(uuid.uuid4())
        # Shorter TTL + frequent heartbeat so crashed workers release quickly.
        lock = DistributedLockService("scan_execution", ttl_seconds=600)

        logger.info("[SCAN] Started | scan_id=%s | trigger_source=%s", scan_id, trigger_source)
        await ScanExecutionService._emit(
            progress_queue,
            {
                "stage": "Connecting data feed...",
                "progress": 1,
                "heartbeat": True,
                "scan_id": scan_id,
            },
        )

        try:
            acquired = await asyncio.wait_for(lock.acquire(timeout_seconds=2), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error(
                "[SCAN] Lock acquisition timed out (DB/lock table unresponsive) | scan_id=%s",
                scan_id,
                exc_info=True,
            )
            await ScanExecutionService._emit(
                progress_queue,
                {
                    "status": "error",
                    "message": "Scanner lock timed out — database may be unavailable. Retry in a moment.",
                    "scan_id": scan_id,
                },
            )
            raise LockAcquisitionError("Scan lock acquisition timed out.")

        if not acquired:
            logger.warning(
                "SCAN_LOCK_DENIED | trigger_source=%s | scan_id=%s | timestamp=%s",
                trigger_source,
                scan_id,
                time.time(),
            )
            raise LockAcquisitionError("Scan is already in progress.")

        logger.info(
            "SCAN_LOCK_ACQUIRED | trigger_source=%s | scan_id=%s | lock_owner=%s | timestamp=%s",
            trigger_source,
            scan_id,
            lock.worker_id,
            time.time(),
        )
        lock.start_heartbeat()

        ScanExecutionService._active_scan_start = time.perf_counter()
        ScanExecutionService._active_scan_stage = "Starting scan..."
        _scan_state.update(stage="Starting scan...", progress=3, current_symbol="", done=0, remaining=0, total=0)

        await ScanExecutionService._emit(
            progress_queue,
            {
                "stage": "Broker session check...",
                "progress": 5,
                "heartbeat": True,
                "scan_id": scan_id,
            },
        )

        heartbeat_task = asyncio.create_task(
            ScanExecutionService._heartbeat_sender(progress_queue, scan_id)
        )

        asyncio.create_task(
            ScanExecutionService._run_scan_task(
                payload, progress_queue, trigger_source, scan_id, lock, heartbeat_task
            )
        )

    @staticmethod
    async def _run_scan_task(
        payload: ScreenerRequest,
        progress_queue: asyncio.Queue | None,
        trigger_source: str,
        scan_id: str,
        lock: DistributedLockService,
        heartbeat_task: asyncio.Task | None = None,
    ):
        start_t = time.perf_counter()
        scan_status = "FAILED"
        error_type = None
        duration_ms = 0
        response_data = None

        try:
            logger.info(
                "[SCAN] SCAN_STARTED | trigger_source=%s | mode=%s | top_n=%s | lookback=%s | swing=%s | custom_symbols=%s | scan_id=%s",
                trigger_source,
                payload.mode.value,
                payload.top_n,
                payload.timeframe.lookback_window,
                payload.timeframe.swing,
                len(payload.symbols),
                scan_id,
            )

            # --- Access token validation (non-fatal if missing; broker calls will fail later) ---
            try:
                from ..services import token_service as token_svc

                token_ok = token_svc.has_cached_token()
                if not token_ok:
                    async with AsyncSessionLocal() as db:
                        tok = await token_svc.get_current_access_token(db)
                        token_ok = bool(tok)
                logger.info(
                    "[SCAN] Access token %s | scan_id=%s",
                    "found" if token_ok else "MISSING",
                    scan_id,
                )
                if not token_ok:
                    logger.warning(
                        "[SCAN] No FYERS access token in cache/DB — market data may fail | scan_id=%s",
                        scan_id,
                    )
                else:
                    logger.info("[SCAN] Token validated (present) | scan_id=%s", scan_id)
            except Exception as tok_exc:
                logger.error(
                    "[SCAN] Token status check failed | scan_id=%s | error=%s",
                    scan_id,
                    tok_exc,
                    exc_info=True,
                )

            _scan_state.update(
                stage="Loading universe...",
                progress=10,
                current_symbol="",
                done=0,
                remaining=len(payload.symbols),
                total=len(payload.symbols),
            )
            await ScanExecutionService._emit(
                progress_queue,
                {
                    "stage": "Loading universe...",
                    "progress": 10,
                    "heartbeat": True,
                    "scan_id": scan_id,
                },
            )

            import datetime
            from ..models.market_data import ScanSnapshot
            from sqlalchemy import update

            # Lifecycle phase 1: insert exactly one RUNNING parent row for this scan_id.
            # Phase 2 (after screener): persist_successful_scan(scan_id=...) must UPDATE
            # that same row — never INSERT a second parent (see UniqueViolationError on
            # ix_scan_snapshots_scan_id).
            try:
                async with AsyncSessionLocal() as db:
                    snapshot = ScanSnapshot(
                        scan_id=scan_id,
                        scan_timestamp=datetime.datetime.now(datetime.timezone.utc),
                        scan_duration_ms=0,
                        total_scanned=len(payload.symbols),
                        valid_symbols=0,
                        buy_count=0,
                        watch_count=0,
                        rejected_count=0,
                        status="RUNNING",
                        error_type=None,
                    )
                    db.add(snapshot)
                    await db.commit()
                logger.info(
                    "[SCAN] Snapshot RUNNING created (single parent) | scan_id=%s | "
                    "phase=1_of_2 | next=persist_successful_scan_UPDATE",
                    scan_id,
                )
            except Exception as snap_exc:
                # Do not abort the scan if snapshot insert fails (schema/status quirks).
                # Persist path will INSERT if no row exists.
                logger.error(
                    "[SCAN] Snapshot RUNNING insert failed (continuing; persist may INSERT) | "
                    "scan_id=%s | error=%s",
                    scan_id,
                    snap_exc,
                    exc_info=True,
                )

            loop = asyncio.get_running_loop()

            def progress_callback(update_dict: dict):
                if isinstance(update_dict, dict):
                    _scan_state.update(
                        stage=update_dict.get("stage", _scan_state.stage),
                        progress=update_dict.get("progress", _scan_state.progress),
                        current_symbol=update_dict.get("current_symbol", _scan_state.current_symbol),
                        done=update_dict.get("done", _scan_state.done),
                        remaining=update_dict.get("remaining", _scan_state.remaining),
                        total=update_dict.get(
                            "total_scoring",
                            update_dict.get("total_fetch", _scan_state.total),
                        ),
                    )
                    logger.info(
                        "[SCAN] progress | stage=%s | progress=%s | symbol=%s | done=%s",
                        update_dict.get("stage"),
                        update_dict.get("progress"),
                        update_dict.get("current_symbol"),
                        update_dict.get("done"),
                    )
                if progress_queue is not None:
                    try:
                        loop.call_soon_threadsafe(progress_queue.put_nowait, update_dict)
                    except Exception:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                ScanExecutionService._emit(progress_queue, update_dict),
                                loop,
                            )
                        except Exception as cb_exc:
                            logger.warning("[SCAN] progress_callback emit failed: %s", cb_exc)

            try:
                cache_universe = "NIFTY500" if not payload.symbols else "custom"
                cached_result = await get_cached_scanner_result(
                    cache_universe, payload.mode.value, payload.timeframe.swing or "1d"
                )
                if cached_result:
                    logger.info(
                        "[SCAN] CACHE_HIT | universe=%s | mode=%s | scan_id=%s",
                        cache_universe,
                        payload.mode.value,
                        scan_id,
                    )
                    response_data = cached_result
                    duration_ms = 0
                    scan_status = "COMPLETED"
                    result = cached_result
                    await ScanExecutionService._emit(
                        progress_queue,
                        {
                            "stage": "Loaded from cache",
                            "progress": 100,
                            "current_symbol": "",
                            "done": 0,
                            "remaining": 0,
                            "eta_sec": 0,
                            "scan_id": scan_id,
                        },
                    )
                    await ScanExecutionService._emit(
                        progress_queue, {"status": "complete", "result": result, "scan_id": scan_id}
                    )
                    return result

                logger.info("[SCAN] Connecting to broker / loading market data | scan_id=%s", scan_id)
                await ScanExecutionService._emit(
                    progress_queue,
                    {
                        "stage": "Connecting to broker...",
                        "progress": 12,
                        "heartbeat": True,
                        "scan_id": scan_id,
                    },
                )
                _scan_state.update(stage="Connecting to broker...", progress=12)

                # Yield so SSE can flush before heavy work
                await asyncio.sleep(0.05)

                logger.info("[SCAN] Invoking RouterAgent.screener_full | scan_id=%s", scan_id)
                response = await RouterAgent(None).screener_full(
                    payload, progress_callback=progress_callback
                )
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                response_data = response
                scan_status = "COMPLETED"
                result = sanitize_for_json(response.model_dump(mode="json"))

                await ScanExecutionService._emit(
                    progress_queue,
                    {
                        "stage": "Persisting results...",
                        "progress": 97,
                        "heartbeat": True,
                        "scan_id": scan_id,
                    },
                )

                await cache_scanner_result(
                    cache_universe, payload.mode.value, payload.timeframe.swing or "1d", result
                )

                # Lifecycle phase 2: single persist call for this scan_id (UPSERT parent).
                # Do not call persist_successful_scan more than once per scan_id here.
                logger.info(
                    "[SCAN] PERSIST_BEGIN | phase=2_of_2 | scan_id=%s | shortlisted=%s | "
                    "buy=%s | watch=%s | analysis_items=%s | expect=UPDATE_running_row",
                    scan_id,
                    len(response.shortlisted_symbols or []),
                    len(response.buy_candidate_symbols or []),
                    len(response.watch_candidate_symbols or []),
                    len(response.analysis.items) if response.analysis and response.analysis.items else 0,
                )

                try:
                    async with AsyncSessionLocal() as db:
                        scan_service = LatestScanService(db)
                        await scan_service.persist_successful_scan(
                            response, duration_ms, scan_id=scan_id
                        )
                        await db.commit()
                    logger.info(
                        "[SCAN] PERSIST_COMMIT_OK | scan_id=%s | buy=%s | watch=%s | "
                        "persist_calls=1",
                        scan_id,
                        len(response.buy_candidate_symbols or []),
                        len(response.watch_candidate_symbols or []),
                    )
                except Exception as persist_exc:
                    logger.error(
                        "[SCAN] Persist failed (results still returned) | scan_id=%s | error=%s",
                        scan_id,
                        persist_exc,
                        exc_info=True,
                    )

                try:
                    await save_latest_scan(result)
                    logger.info(
                        "[SCAN] SAVE_LATEST_OK | scan_id=%s | shortlisted=%s | buy=%s | watch=%s",
                        scan_id,
                        len(response.shortlisted_symbols or []),
                        len(response.buy_candidate_symbols or []),
                        len(response.watch_candidate_symbols or []),
                    )
                except Exception as save_exc:
                    logger.error(
                        "[SCAN] save_latest_scan failed | scan_id=%s | error=%s",
                        scan_id,
                        save_exc,
                        exc_info=True,
                    )

                logger.info(
                    "[SCAN] COMPLETED | trigger_source=%s | duration_ms=%s | scanned=%s | valid=%s | "
                    "eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | data_source=%s | stopped_at=%s",
                    trigger_source,
                    duration_ms,
                    response.scanned_symbols,
                    len(response.data_valid_symbols),
                    len(response.eligible_symbols),
                    len(response.matched_symbols),
                    len(response.shortlisted_symbols),
                    len(response.buy_candidate_symbols),
                    len(response.watch_candidate_symbols),
                    response.data_source,
                    response.stopped_at_stage,
                )

                await ScanExecutionService._emit(
                    progress_queue,
                    {
                        "stage": "Completed",
                        "progress": 100,
                        "heartbeat": True,
                        "scan_id": scan_id,
                    },
                )
                await ScanExecutionService._emit(
                    progress_queue, {"status": "complete", "result": result, "scan_id": scan_id}
                )

            except asyncio.CancelledError:
                error_type = "CancelledError"
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                try:
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            update(ScanSnapshot)
                            .where(ScanSnapshot.scan_id == scan_id)
                            .values(
                                status="FAILED",
                                error_type=error_type,
                                scan_duration_ms=duration_ms,
                            )
                        )
                        await db.execute(stmt)
                        await db.commit()
                except Exception:
                    pass
                logger.warning("[SCAN] CANCELLED | trigger_source=%s | scan_id=%s", trigger_source, scan_id)
                raise
            except Exception as e:
                error_type = type(e).__name__
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                try:
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            update(ScanSnapshot)
                            .where(ScanSnapshot.scan_id == scan_id)
                            .values(
                                status="FAILED",
                                error_type=error_type,
                                scan_duration_ms=duration_ms,
                            )
                        )
                        await db.execute(stmt)
                        await db.commit()
                except Exception:
                    pass
                logger.exception(
                    "[SCAN] FAILED | trigger_source=%s | error_type=%s | error=%s | scan_id=%s",
                    trigger_source,
                    error_type,
                    e,
                    scan_id,
                )
                await ScanExecutionService._emit(
                    progress_queue,
                    {
                        "status": "error",
                        "message": str(e) or f"Scanner failed ({error_type})",
                        "scan_id": scan_id,
                        "error_type": error_type,
                    },
                )
        finally:
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            ScanExecutionService._active_scan_start = None
            ScanExecutionService._active_scan_stage = "Idle"
            _scan_state.update(stage="Idle", progress=0)

            if duration_ms == 0:
                duration_ms = int((time.perf_counter() - start_t) * 1000)
            logger.info(
                "SCAN_SUMMARY | scan_id=%s | trigger_source=%s | status=%s | error_type=%s | "
                "duration_sec=%.2f | symbols_scanned=%s | eligible_count=%s | shortlisted_count=%s | "
                "buy_count=%s | watch_count=%s",
                scan_id,
                trigger_source,
                scan_status,
                error_type,
                duration_ms / 1000.0,
                getattr(response_data, "scanned_symbols", None)
                if response_data and not isinstance(response_data, dict)
                else (response_data.get("scanned_symbols") if isinstance(response_data, dict) else len(payload.symbols)),
                len(getattr(response_data, "eligible_symbols", []) or [])
                if response_data and not isinstance(response_data, dict)
                else len((response_data or {}).get("eligible_symbols", []) if isinstance(response_data, dict) else []),
                len(getattr(response_data, "shortlisted_symbols", []) or [])
                if response_data and not isinstance(response_data, dict)
                else len((response_data or {}).get("shortlisted_symbols", []) if isinstance(response_data, dict) else []),
                len(getattr(response_data, "buy_candidate_symbols", []) or [])
                if response_data and not isinstance(response_data, dict)
                else len((response_data or {}).get("buy_candidate_symbols", []) if isinstance(response_data, dict) else []),
                len(getattr(response_data, "watch_candidate_symbols", []) or [])
                if response_data and not isinstance(response_data, dict)
                else len((response_data or {}).get("watch_candidate_symbols", []) if isinstance(response_data, dict) else []),
            )
            try:
                await lock.release()
                logger.info(
                    "SCAN_LOCK_RELEASED | trigger_source=%s | scan_id=%s | lock_owner=%s",
                    trigger_source,
                    scan_id,
                    lock.worker_id,
                )
            except Exception as rel_exc:
                logger.error(
                    "[SCAN] lock release failed | scan_id=%s | error=%s",
                    scan_id,
                    rel_exc,
                    exc_info=True,
                )
