import asyncio
import time
import logging
from ..agents import RouterAgent
from ..db.session import AsyncSessionLocal
from ..db.scan_store import save_latest_scan
from ..services.latest_scan_service import LatestScanService
from ..utils import sanitize_for_json
from ..schemas import ScreenerRequest

logger = logging.getLogger("backend.app.services.scan_execution_service")

import uuid
from ..services.lock_service import DistributedLockService, LockAcquisitionError

class ScanExecutionService:
    @staticmethod
    async def execute_scan(payload: ScreenerRequest, progress_queue: asyncio.Queue | None, trigger_source: str = "ui"):
        scan_id = str(uuid.uuid4())
        lock = DistributedLockService("scan_execution", ttl_seconds=3600)
        
        acquired = await lock.acquire(timeout_seconds=0)
        if not acquired:
            logger.warning("SCAN_LOCK_DENIED | trigger_source=%s | scan_id=%s | timestamp=%s", trigger_source, scan_id, time.time())
            raise LockAcquisitionError("Scan is already in progress.")
            
        logger.info("SCAN_LOCK_ACQUIRED | trigger_source=%s | scan_id=%s | lock_owner=%s | timestamp=%s", trigger_source, scan_id, lock.worker_id, time.time())
        lock.start_heartbeat()
        asyncio.create_task(ScanExecutionService._run_scan_task(payload, progress_queue, trigger_source, scan_id, lock))
        return scan_id

    @staticmethod
    async def _run_scan_task(payload: ScreenerRequest, progress_queue: asyncio.Queue | None, trigger_source: str, scan_id: str, lock: DistributedLockService):
        start_t = time.perf_counter()
        scan_status = "FAILED"
        error_type = None
        duration_ms = 0
        response_data = None

        try:
            logger.info(
                "SCAN_STARTED | trigger_source=%s | mode=%s | top_n=%s | lookback=%s | swing=%s | custom_symbols=%s",
                trigger_source,
                payload.mode.value,
                payload.top_n,
                payload.timeframe.lookback_window,
                payload.timeframe.swing,
                len(payload.symbols),
            )

            import datetime
            from ..models.market_data import ScanSnapshot
            from sqlalchemy import update
            
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
                    status="completed",
                    error_type=None
                )
                db.add(snapshot)
                await db.commit()

            loop = asyncio.get_running_loop()

            def progress_callback(update_dict: dict):
                if progress_queue is not None:
                    loop.call_soon_threadsafe(progress_queue.put_nowait, update_dict)

            try:
                # Replicating original behaviour
                if progress_queue is not None:
                    await asyncio.sleep(2.0)

                response = await RouterAgent(None).screener_full(payload, progress_callback=progress_callback)
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                response_data = response
                scan_status = "COMPLETED"
                result = sanitize_for_json(response.model_dump(mode="json"))
                
                async with AsyncSessionLocal() as db:
                    scan_service = LatestScanService(db)
                    await scan_service.persist_successful_scan(response, duration_ms, scan_id=scan_id)
                    await db.commit()
                    
                await save_latest_scan(result)
                
                logger.info(
                    "SCAN_COMPLETED | trigger_source=%s | duration_ms=%s | scanned=%s | valid=%s | eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | data_source=%s | stopped_at=%s",
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

                if progress_queue is not None:
                    await progress_queue.put({"status": "complete", "scan_id": scan_id, "result": result})

            except asyncio.CancelledError:
                error_type = "CancelledError"
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                async with AsyncSessionLocal() as db:
                    stmt = update(ScanSnapshot).where(ScanSnapshot.scan_id == scan_id).values(status="FAILED", error_type=error_type, scan_duration_ms=duration_ms)
                    await db.execute(stmt)
                    await db.commit()
                logger.warning("SCAN_CANCELLED | trigger_source=%s", trigger_source)
                raise
            except Exception as e:
                error_type = type(e).__name__
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                async with AsyncSessionLocal() as db:
                    stmt = update(ScanSnapshot).where(ScanSnapshot.scan_id == scan_id).values(status="FAILED", error_type=error_type, scan_duration_ms=duration_ms)
                    await db.execute(stmt)
                    await db.commit()
                logger.exception("SCAN_FAILED | trigger_source=%s | error_type=%s | timestamp=%s", trigger_source, error_type, time.time())
                if progress_queue is not None:
                    await progress_queue.put({"status": "error", "scan_id": scan_id, "message": str(e), "error_type": error_type})
        finally:
            if duration_ms == 0:
                duration_ms = int((time.perf_counter() - start_t) * 1000)
            logger.info(
                "SCAN_SUMMARY | scan_id=%s | trigger_source=%s | status=%s | error_type=%s | duration_sec=%.2f | symbols_scanned=%s | eligible_count=%s | shortlisted_count=%s | buy_count=%s | watch_count=%s",
                scan_id,
                trigger_source,
                scan_status,
                error_type,
                duration_ms / 1000.0,
                response_data.scanned_symbols if response_data else len(payload.symbols),
                len(response_data.eligible_symbols) if response_data else 0,
                len(response_data.shortlisted_symbols) if response_data else 0,
                len(response_data.buy_candidate_symbols) if response_data else 0,
                len(response_data.watch_candidate_symbols) if response_data else 0
            )
            await lock.release()
            logger.info("SCAN_LOCK_RELEASED | trigger_source=%s | scan_id=%s | lock_owner=%s | timestamp=%s", trigger_source, scan_id, lock.worker_id, time.time())
