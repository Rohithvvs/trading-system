from datetime import datetime
from time import perf_counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response
import traceback
from datetime import date
from .services.db_logger import log_to_db
from sqlalchemy import select
from .models.system_log import SystemLog

from .core.logger import setup_logging
import sys
import logging

# Fail-fast config validation
try:
    from .config import settings
except ImportError as e:
    logging.critical(f"STARTUP FATAL: Missing or corrupted settings/config module. Diagnostic: {e}")
    sys.exit(1)
from .db import init_db
from .routes import api_router
from .routes.fyers import router as fyers_router
from .utils import configure_logging, get_logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .services.candle_store import (
    get_all_cached_symbols,
    is_cache_fresh,
    get_last_stored_date,
)
from .db.session import AsyncSessionLocal, SessionLocal
from .services.paper_trading_service import PaperTradingService
from .services.fyers_service import FyersService
from .services.market_engine_service import market_engine
from .db.locks import acquire_singleton_lease
from .core.task_supervisor import TaskSupervisor
# token_service refresh automation removed — manual access-token workflow only
import asyncio
from .schemas import AnalysisMode
from .observability.scan_diagnostics import (
    begin_scan, end_scan, get_current_scan, log_token_status,
    log_process_event, log_scheduler_event, log_incident_summary,
    log_db_pool_status, hash_token_prefix, ScanContext, log_scan_environment
)


setup_logging()
configure_logging()
# DB init moved or handled by alembic
from .core import log_manager  # ensure module-level loggers (api/http) are created
request_logger = get_logger("app.http")
config_logger = get_logger("app.config")
logger = get_logger("app.scheduler")


from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_SUBMITTED

# Scheduler for background jobs (nightly tasks)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

_job_starts = {}
def _scheduler_listener(event):
    from .services.diagnostics_service import diagnostics
    import time
    import datetime
    
    scheduled_time = getattr(event, "scheduled_run_time", None)
    scheduled_time_str = scheduled_time.isoformat() if scheduled_time else "unknown"
    actual_time_str = datetime.datetime.utcnow().isoformat()
    
    if event.code == EVENT_JOB_SUBMITTED:
        _job_starts[event.job_id] = time.perf_counter()
        logger.info("SCHEDULER_JOB_STARTED | job_name=%s | scheduled_time=%s | actual_time=%s", event.job_id, scheduled_time_str, actual_time_str)
        return

    duration_ms = 0
    if event.job_id in _job_starts:
        duration_ms = int((time.perf_counter() - _job_starts[event.job_id]) * 1000)
        del _job_starts[event.job_id]

    status = "success"
    if event.code == EVENT_JOB_ERROR:
        status = "error"
    elif event.code == EVENT_JOB_MISSED:
        status = "skipped"

    success = status == "success"
    failure_reason = ""
    if status == "error":
        failure_reason = str(getattr(event, "exception", "Unknown Error"))
        logger.error("SCHEDULER_JOB_FAILED | job_name=%s | scheduled_time=%s | actual_time=%s | duration_ms=%s | error=%s", event.job_id, scheduled_time_str, actual_time_str, duration_ms, failure_reason)
    elif status == "skipped":
        failure_reason = "Missed schedule"
        logger.warning("SCHEDULER_JOB_MISSED | job_name=%s | scheduled_time=%s | actual_time=%s | duration_ms=%s", event.job_id, scheduled_time_str, actual_time_str, duration_ms)
    else:
        logger.info("SCHEDULER_JOB_SUCCESS | job_name=%s | scheduled_time=%s | actual_time=%s | duration_ms=%s", event.job_id, scheduled_time_str, actual_time_str, duration_ms)

    diagnostics.record_scheduler_run({
        "job_name": event.job_id,
        "scheduled_time": scheduled_time_str,
        "actual_time": actual_time_str,
        "duration_ms": duration_ms,
        "success": success,
        "failure_reason": failure_reason
    })

scheduler.add_listener(_scheduler_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_SUBMITTED)


# Log configuration at startup
config_logger.info(
    "System Configuration | app_env=%s | app_name=%s | host=%s | port=%s",
    settings.app_env,
    settings.app_name,
    settings.app_host,
    settings.app_port,
)
config_logger.info(
    "Data Source Configuration | fyers_enabled=%s",
    bool(settings.fyers_access_token),
)
config_logger.info(
    "Universe Configuration | nifty500=%s | nifty_next_500=%s | bse500=%s | bse1000=%s",
    len(settings.nifty500_symbols),
    len(settings.nifty_next_500_symbols),
    len(settings.bse500_symbols),
    len(settings.bse1000_symbols),
)
if not settings.nifty500_symbols:
    config_logger.warning(
        "Nifty 500 universe is empty | Check NIFTY500_CSV_PATH, ind_nifty500list.csv, or NIFTY500_SYMBOLS"
    )

async def job_market_engine_spin_up():
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="Market engine spin up triggered.",
        source="JOB",
        module="Scheduler",
        endpoint="job_market_engine_spin_up"
    )
    try:
        from .services.market_engine_service import market_engine
        await market_engine.request_start()
        logger_service.log_info(
            message="Market engine spin up completed successfully.",
            source="JOB",
            module="Scheduler",
            endpoint="job_market_engine_spin_up"
        )
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="job_market_engine_spin_up",
            exc=e
        )

async def job_intraday_heartbeat():
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="15-minute market data trigger started.",
        source="JOB",
        module="Scheduler",
        endpoint="job_intraday_heartbeat"
    )
    try:
        from .services.market_engine_service import market_engine
        await market_engine.heartbeat()
        logger_service.log_info(
            message="15-minute market data trigger completed successfully.",
            source="JOB",
            module="Scheduler",
            endpoint="job_intraday_heartbeat"
        )
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="job_intraday_heartbeat",
            exc=e
        )

async def job_market_engine_cool_down():
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="Market engine cool down triggered.",
        source="JOB",
        module="Scheduler",
        endpoint="job_market_engine_cool_down"
    )
    try:
        from .services.market_engine_service import market_engine
        await market_engine.request_stop()
        logger_service.log_info(
            message="Market engine cool down completed successfully.",
            source="JOB",
            module="Scheduler",
            endpoint="job_market_engine_cool_down"
        )
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="job_market_engine_cool_down",
            exc=e
        )

async def job_retention_cleanup():
    try:
        from .services.retention_service import RetentionService

        async with AsyncSessionLocal() as db:
            deleted = await RetentionService(db).cleanup()
        logger.info("Retention cleanup complete | deleted=%s", deleted)
    except Exception:
        logger.exception("Retention cleanup failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from .config import settings
    import asyncio
    from .db import session as session_module
    import anyio
    session_module.main_event_loop = asyncio.get_running_loop()
    
    logger.info("APP_START | Application is starting")
    try:
        from .core.server_state import read_shutdown_time
        last_shutdown = read_shutdown_time()
        if last_shutdown:
            logger.warning("APP_RESTART_DETECTED | Application was previously shutdown at %s", last_shutdown)
    except Exception:
        pass
    logger.info("APP_LIFESPAN_INITIALIZED | Lifespan initialization started")
    
    log_process_event("PROCESS_START")
    
    # Configure AnyIO thread pool for high concurrency (Phase E4.1)
    try:
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 100
        logger.info("AnyIO default thread limiter set to 100")
    except Exception as e:
        logger.warning(f"Failed to set AnyIO thread limiter: {e}")
    # Startup
    if settings.app_env == "test":
        logger.info("Test environment detected; setting up tables and skipping scheduler/monitors.")
        from .db.session import engine
        from .db.base import Base
        import backend.app.models  # ensure all models are registered
        
        # Patch SQLite JSONB support for testing
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.dialects.postgresql import JSONB
        
        @compiles(JSONB, "sqlite")
        def compile_jsonb_sqlite(type_, compiler, **kw):
            return "JSON"

        async def _init_db():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        
        await _init_db()
        
        yield
        # Shutdown for test env: no scheduler running
        try:
            from .core.server_state import write_shutdown_time
            write_shutdown_time()
            print("[server_state] Shutdown time saved.")
        except Exception:
            logger.exception("Failed to write shutdown time on shutdown")
        return

    worker_lease = await acquire_singleton_lease("trading-system:singleton-workers")
    app.state.singleton_worker_lease = worker_lease
    app.state.task_supervisor = TaskSupervisor()
    
    from .services.partition_manager import verify_and_create_partitions
    try:
        await verify_and_create_partitions()
    except Exception as e:
        logger.error(f"Failed to verify partitions: {e}")

    if not worker_lease.acquired:
        logger.warning("Another instance owns singleton workers; API-only mode enabled for this pod.")
        yield
        return
    try:
        from .services.screener_service import ScreenerService
        from .config import settings
        from .db.session import check_alembic_head
        
        # Enforce Alembic Migration Gate
        logger.info("STARTUP PROGRESS: Validating database schema lineage...")
        check_alembic_head()
        logger.info("STARTUP PROGRESS: Database schema is up-to-date.")
        
        logger.info("STARTUP PROGRESS: settings module loaded successfully.")
        
        # Run startup validation for screener health
        from .services.universe_service import UniverseService
        active_symbols = await UniverseService.get_all_active_symbols()
        count = len(active_symbols)
        logger.info(f"UNIVERSE_LOADED | count={count}")
        if count == 0:
            raise RuntimeError("Startup failed: Universe count is 0. Please import stocks_master.")

        screener_svc = ScreenerService()
        await screener_svc.validate_startup_health(active_symbols)
        logger.info("STARTUP SUCCESS: Scanner health bootstrap completed successfully.")
    except Exception as e:
        logger.critical("STARTUP FATAL: Failed to run startup initialization. Crashing lifespan: %s", repr(e))
        logger.critical("FAILED CHECK: Startup Initialization")
        logger.critical("EXCEPTION TYPE: %s", type(e).__name__)
        logger.critical("EXCEPTION MESSAGE: %s", str(e))
        
        # Connection cleanup
        try:
            from .db.session import engine, sync_engine
            sync_engine.dispose()
            await engine.dispose()
            if 'worker_lease' in locals() and hasattr(worker_lease, 'release'):
                await worker_lease.release()
        except Exception as cleanup_e:
            logger.error("Failed during connection cleanup on fatal exit: %s", cleanup_e)
            
        sys.exit(1)

    # JOB 1: Market Engine Spin Up
    scheduler.add_job(
        job_market_engine_spin_up,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=55, timezone="Asia/Kolkata"),
        id="market_engine_spin_up",
        replace_existing=True,
    )

    # JOB 2: Pre-Market Deep Scan
    scheduler.add_job(
        automated_screening_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone="Asia/Kolkata"),
        id="pre_market_deep_scan",
        replace_existing=True,
    )

    # JOB 3a: Intraday Engine Heartbeat Loop (09:15 AM to 09:45 AM)
    scheduler.add_job(
        job_intraday_heartbeat,
        CronTrigger(day_of_week="mon-fri", hour=9, minute="15,30,45", timezone="Asia/Kolkata"),
        id="intraday_heartbeat_1a",
        replace_existing=True,
    )

    # JOB 3b: Intraday Engine Heartbeat Loop (10:00 AM to 14:45 PM)
    scheduler.add_job(
        job_intraday_heartbeat,
        CronTrigger(day_of_week="mon-fri", hour="10-14", minute="0,15,30,45", timezone="Asia/Kolkata"),
        id="intraday_heartbeat_1b",
        replace_existing=True,
    )

    # JOB 3 continued: Intraday Engine Heartbeat Loop (15:00 PM to 15:30 PM)
    scheduler.add_job(
        job_intraday_heartbeat,
        CronTrigger(day_of_week="mon-fri", hour=15, minute="0,15,30", timezone="Asia/Kolkata"),
        id="intraday_heartbeat_2",
        replace_existing=True,
    )

    # JOB 4: Market Engine Cool Down
    scheduler.add_job(
        job_market_engine_cool_down,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone="Asia/Kolkata"),
        id="market_engine_cool_down",
        replace_existing=True,
    )

    # JOB 5: Strategy Performance & Drift Tracker
    scheduler.add_job(
        track_strategy_drift_job,
        CronTrigger(day_of_week="fri", hour=16, minute=0, timezone="Asia/Kolkata"),
        id="track_strategy_drift_job",
        replace_existing=True,
    )

    scheduler.add_job(
        job_retention_cleanup,
        CronTrigger(hour=2, minute=15, timezone="Asia/Kolkata"),
        id="retention_cleanup",
        replace_existing=True,
    )

    # FYERS refresh automation removed. Manual access-token workflow only.
    if not settings.quarantine_mode:
        scheduler.start()
        logger.info("SCHEDULER_STARTED | timezone=%s | jobs_registered=%d", str(scheduler.timezone), len(scheduler.get_jobs()))
    else:
        logger.info("QUARANTINE MODE: Scheduler execution bypassed.")

    # Log DB path
    try:
        from .db.session import engine
        from .services.token_service import get_current_access_token

        config_logger.info("DATABASE URL: %s", engine.url)

        # Verify token is present
        try:
            async with AsyncSessionLocal() as db:
                from .services.token_service import get_fyers_token_row
                token = await get_current_access_token(db)
                token_row = await get_fyers_token_row(db)
                token_saved_at = token_row.access_token_saved_at.isoformat() if token_row and token_row.access_token_saved_at else "N/A"
                token_age_min = 0.0
                if token_row and token_row.access_token_saved_at:
                    token_age_min = (datetime.now(token_row.access_token_saved_at.tzinfo) - token_row.access_token_saved_at).total_seconds() / 60.0
                logger.info(
                    "STARTUP_TOKEN_VERIFICATION | token_found=%s | saved_at=%s | age_minutes=%.1f",
                    bool(token), token_saved_at, token_age_min,
                )
                if token:
                    logger.info("STARTUP: FYERS access token loaded from DB successfully")
                    # Lightweight FYERS validation
                    try:
                        fyers_svc = FyersService()
                        await asyncio.wait_for(
                            asyncio.to_thread(fyers_svc.validate_token_sync, token),
                            timeout=10.0,
                        )
                        logger.info("TOKEN_VALIDATION_SUCCESS | saved_at=%s | age_minutes=%.1f", token_saved_at, token_age_min)
                    except Exception as val_exc:
                        logger.error("TOKEN_VALIDATION_FAILED | saved_at=%s | age_minutes=%.1f | error=%s", token_saved_at, token_age_min, val_exc)
                else:
                    logger.warning("STARTUP: No FYERS access token found in DB. Please add via UI.")
        except Exception:
            logger.exception("Failed to read FYERS access token from DB on startup")
    except Exception:
        logger.exception("Failed to log database engine/url on startup")

    # Start the backend-driven market engine. The service boundary is intentionally
    # separate so the same loop can later be hosted in a dedicated worker process.
    if not settings.quarantine_mode:
        try:
            await market_engine.start_loop()
        except Exception:
            logger.exception("Failed to start market engine loop")
    else:
        logger.info("QUARANTINE MODE: Market engine loop bypassed.")

    # Legacy monitor kept only for alert checks; position/order automation now
    # belongs to market_engine so it can survive browser closure cleanly.
    async def _monitor_positions_background():
        logger.info("Legacy alert monitor starting (every 5s)")
        fyers = FyersService()
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    service = PaperTradingService(db)
                    # Check price alerts as well
                    try:
                        def _get_alerts():
                            with SessionLocal() as s:
                                # We map the sqlalchemy models to dictionaries so we don't hold the session
                                return [{"id": x.id, "symbol": x.symbol, "condition": x.condition, "target_price": x.target_price} for x in PaperTradingService(s).get_active_alerts()]
                        
                        alerts = await asyncio.to_thread(_get_alerts)
                        for a in alerts:
                            try:
                                ltp_coro = fyers.fetch_ltp(a["symbol"])
                                if asyncio.iscoroutine(ltp_coro): ltp = await ltp_coro
                                else: ltp = ltp_coro

                                if ltp is None:
                                    candles = await fyers.fetch_ohlcv(
                                        a["symbol"], AnalysisMode.swing, "1d", 2
                                    )
                                    if candles and len(candles) > 0:
                                        ltp = candles[-1].close
                                    else:
                                        logger.warning("No price data available for alert %s; skipping", a["symbol"])
                                        continue
                                if a["condition"] == ">=" and ltp >= a["target_price"]:
                                    def _trigger(aid, val):
                                        with SessionLocal() as s:
                                            PaperTradingService(s).trigger_alert(aid, val)
                                    await asyncio.to_thread(_trigger, a["id"], ltp)
                                elif a["condition"] == "<=" and ltp <= a["target_price"]:
                                    def _trigger(aid, val):
                                        with SessionLocal() as s:
                                            PaperTradingService(s).trigger_alert(aid, val)
                                    await asyncio.to_thread(_trigger, a["id"], ltp)
                            except Exception:
                                logger.exception("Error monitoring alert %s", a["symbol"])
                    except Exception:
                        logger.exception("Failed to check price alerts")
                    try:
                        from sqlalchemy import select
                        from .models.workstation import WorkstationAlert

                        app_alerts = list(
                            (await db.scalars(
                                select(WorkstationAlert).where(
                                    WorkstationAlert.alert_type == "PRICE",
                                    WorkstationAlert.status == "ACTIVE",
                                )
                            )).all()
                        )
                        for alert in app_alerts:
                            if not alert.symbol or not alert.condition or not alert.target_price:
                                continue
                            ltp = await fyers.fetch_ltp(alert.symbol)
                            if ltp is None:
                                continue
                            triggered = (alert.condition == ">=" and ltp >= alert.target_price) or (
                                alert.condition == "<=" and ltp <= alert.target_price
                            )
                            if triggered:
                                alert.last_triggered_at = datetime.utcnow()
                                alert.last_message = f"{alert.symbol} {alert.condition} {alert.target_price} hit at {round(ltp, 2)}"
                        await db.commit()
                    except Exception:
                        logger.exception("Failed to check workstation price alerts")
            except Exception:
                logger.exception("Position monitor loop failed")
            await asyncio.sleep(5)

    # Create background task but don't await it
    if not settings.quarantine_mode:
        try:
            app.state.task_supervisor.start("legacy-alert-monitor", _monitor_positions_background)
        except Exception:
            logger.exception("Failed to start position monitor task")
    else:
        logger.info("QUARANTINE MODE: Legacy alert monitor bypassed.")

    # ADD: Run offline gap replay on startup to handle fills/exits while server was down
    if not settings.quarantine_mode:
        try:
            from .core.gap_replay import run_gap_replay

            async with AsyncSessionLocal() as db:
                fyers = FyersService()
                summary = await run_gap_replay(db, fyers)

            app.state.last_gap_replay = summary
            if summary.get("skipped_reason"):
                print(f"[GAP_REPLAY] Skipped: {summary['skipped_reason']}")
            else:
                print("[GAP_REPLAY] Complete!")
                print(f"  Orders filled:     {len(summary.get('orders_filled', []))}")
                print(f"  Positions exited:  {len(summary.get('positions_exited', []))}")
                for w in summary.get("warnings", []):
                    print(f"  [WARNING]  {w}")
        except Exception as e:
            logger.exception("GAP_REPLAY startup failed: %s", e)
            print(f"[GAP_REPLAY] Startup replay failed: {e}")
    else:
        logger.info("QUARANTINE MODE: Offline gap replay bypassed.")

    logger.info("APP_LIFESPAN_COMPLETED | Lifespan startup fully completed")
    # yield control to the application
    yield
    # Shutdown
    logger.info("APP_SHUTDOWN | Application is shutting down")
    log_process_event("PROCESS_STOP", reason="lifespan_shutdown")
    if settings.app_env != "test" and scheduler.running:
        scheduler.shutdown()
    try:
        await market_engine.shutdown()
    except Exception:
        logger.exception("Failed to stop market engine loop")
    try:
        await app.state.task_supervisor.shutdown()
    except Exception:
        logger.exception("Failed to stop supervised tasks")
    try:
        from .core.server_state import write_shutdown_time

        write_shutdown_time()
        print("[server_state] Shutdown time saved.")
    except Exception:
        logger.exception("Failed to write shutdown time on shutdown")
    try:
        await worker_lease.release()
    except Exception:
        logger.exception("Failed to release singleton worker lease")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"(http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app|https://.*\.onrender\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/scanner/health")
def scanner_health():
    from .services.screener_service import ScreenerService
    svc = ScreenerService()
    return svc.get_metrics()

@app.get("/metrics", include_in_schema=False)
def metrics():
    from .observability import render_metrics

    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    started_at = perf_counter()
    request_logger.info(
        "HTTP request start | method=%s | path=%s | client=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
        request_logger.exception(
            "HTTP request failed | method=%s | path=%s | elapsed_ms=%s",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        
        # Log to DB and return 500 gracefully
        tb = traceback.format_exc()
        print(f"EXCEPTION CAUGHT IN MIDDLEWARE:\n{tb}")
        await log_to_db(
            level="ERROR",
            module="http_middleware_exception",
            message=str(exc),
            endpoint=request.url.path,
            tb=tb
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected system error occurred. This has been logged for our engineers."}
        )

    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    request_logger.info(
        "HTTP request end | method=%s | path=%s | status=%s | elapsed_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    
    # Log critical user actions to DB
    if request.method in ["POST", "PUT", "DELETE"]:
        await log_to_db(
            level="INFO",
            module="http_middleware",
            message=f"{request.method} {request.url.path} returned {response.status_code}",
            endpoint=request.url.path
        )
    return response




from .routes import scheduler as scheduler_router

app.include_router(api_router)
app.include_router(fyers_router)
app.include_router(scheduler_router.router)


async def nightly_candle_sync():
    logger.info("NIGHTLY SYNC started")
    from .services.fyers_service import FyersService
    fyers = FyersService()
    symbols = get_all_cached_symbols()
    stale = [s for s in symbols if not is_cache_fresh(s)]
    logger.info("NIGHTLY SYNC stale_symbols=%s total=%s", len(stale), len(symbols))
    import asyncio
    from .schemas import AnalysisMode
    sem = asyncio.Semaphore(10)

    async def _sync_symbol(symbol: str):
        async with sem:
            try:
                await fyers.get_candles_cached(symbol, AnalysisMode.swing, "1d", 260, False)
                logger.info("NIGHTLY SYNC refreshed symbol=%s", symbol)
            except Exception as e:
                logger.error("NIGHTLY SYNC failed symbol=%s error=%s", symbol, e)

    if stale:
        await asyncio.gather(*[_sync_symbol(s) for s in stale])
        
    logger.info("NIGHTLY SYNC complete")


# Lifespan managed startup/shutdown is handled by the `lifespan` context manager above.

async def automated_screening_job():
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="Automated screening job started.",
        source="JOB",
        module="Scheduler",
        endpoint="automated_screening_job"
    )
    logger.info("AUTOMATED SCREENING job triggered")
    from .agents.orchestrator_agent import OrchestratorAgent
    from .schemas import ScreenerRequest, AnalysisMode
    import asyncio
    
    scan_ctx = begin_scan(trigger_source="scheduler", universe="NIFTY500", symbol_count=len(settings.nifty500_symbols))
    from .db.session import AsyncSessionLocal, SessionLocal
    from .models.analysis import ScannedCandidate
    try:
        async with AsyncSessionLocal() as db:
            agent = OrchestratorAgent(db)
            request = ScreenerRequest(
                mode=AnalysisMode.swing
            )
            
            from .services import token_service
            from .services.fyers_service import FyersService, FyersAuthInvalidError, FyersAuthExpiredError, FyersAPIError
            
            token = await token_service.get_current_access_token(db)
            if not token:
                logger.error("Scan aborted: No cached token available in memory or DB.")
                from .services.diagnostics_service import diagnostics
                diagnostics.set_scanner_failed("No FYERS token configured")
                scan_ctx.token_loaded = False
                scan_ctx.token_source = "none"
                end_scan(scan_ctx)
                from .services.paper_trading_service import PaperTradingService
                try:
                    PaperTradingService(db).add_notification(
                        account_id=1,
                        message="Scheduled scan aborted: No FYERS token configured. Please authenticate.",
                        level="error",
                        event_type="TOKEN_MISSING",
                        entity_type="system",
                        dedupe_key="TOKEN_MISSING_ALERT",
                        commit=True
                    )
                except Exception as ne:
                    pass
                return
            
            try:
                logger.info("Validating FYERS token before scheduled scan...")
                fyers_service = FyersService()
                val_start_t = perf_counter()
                await asyncio.wait_for(
                    asyncio.to_thread(fyers_service.validate_token_sync, token),
                    timeout=15.0
                )
                val_latency_ms = int((perf_counter() - val_start_t) * 1000)
            except asyncio.TimeoutError:
                logger.error("Scan aborted: FYERS API timeout during token validation.")
                from .services.diagnostics_service import diagnostics
                diagnostics.set_scanner_failed("FYERS Validation Timeout")
                scan_ctx.token_loaded = False
                scan_ctx.token_source = "none"
                end_scan(scan_ctx)
                return
            except (FyersAuthInvalidError, FyersAuthExpiredError) as e:
                logger.error("Scan aborted: TOKEN_EXPIRED or invalid. %s", e)
                from .services.diagnostics_service import diagnostics
                diagnostics.set_scanner_failed("FYERS Token Expired")
                scan_ctx.token_loaded = False
                scan_ctx.token_source = "none"
                end_scan(scan_ctx)
                token_service._clear_token_cache()
                from .services.paper_trading_service import PaperTradingService
                PaperTradingService(db).add_notification(
                    account_id=1,
                    message="Scheduled scan aborted: FYERS token expired. Please re-authenticate.",
                    level="error",
                    event_type="TOKEN_EXPIRED",
                    entity_type="system",
                    dedupe_key="TOKEN_EXPIRED_ALERT",
                    commit=True
                )
                logger.info("TOKEN_EXPIRED_NOTIFICATION_CREATED")
                return
            except FyersAPIError as e:
                logger.error("Scan aborted: FYERS API Error during token validation. %s", e)
                from .services.diagnostics_service import diagnostics
                diagnostics.set_scanner_failed("FYERS API Error")
                scan_ctx.token_loaded = False
                scan_ctx.token_source = "none"
                end_scan(scan_ctx)
                return
            
            logger.info("AUTOMATED SCREENING triggering scan via OrchestratorAgent")
            # Token forensics
            try:
                token_row = await token_service.get_fyers_token_row(db)
                token_saved_at = token_row.access_token_saved_at.isoformat() if token_row and token_row.access_token_saved_at else "N/A"
                token_age = (datetime.utcnow() - token_row.access_token_saved_at).total_seconds() / 60.0 if token_row and token_row.access_token_saved_at else 0.0
                log_token_status(
                    scan_ctx,
                    token_exists=bool(token),
                    token_source="memory" if token_service.has_cached_token() else "database",
                    token_saved_at=token_saved_at,
                    token_age_minutes=token_age,
                    token_hash=hash_token_prefix(token),
                )
            except Exception:
                logger.exception("Failed to log token status for scan")
                
            # Emit full SCAN_ENVIRONMENT block
            try:
                from .observability.scan_diagnostics import _PROCESS_START_TIME
                from .db.session import engine
                from .services.latest_scan_service import LatestScanService
                from .services.candle_store import get_all_cached_symbols
                import datetime
                
                startup_dt = datetime.datetime.fromisoformat(_PROCESS_START_TIME)
                app_uptime = (datetime.datetime.now(datetime.timezone.utc) - startup_dt).total_seconds() / 60.0
                
                ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
                market_open = ist_now.weekday() < 5 and (9 <= ist_now.hour <= 15) and not (ist_now.hour == 9 and ist_now.minute < 15) and not (ist_now.hour == 15 and ist_now.minute > 30)
                if ist_now.weekday() >= 5:
                    market_session = "closed"
                elif ist_now.hour < 9 or (ist_now.hour == 9 and ist_now.minute < 15):
                    market_session = "pre_open"
                elif ist_now.hour > 15 or (ist_now.hour == 15 and ist_now.minute > 30):
                    market_session = "post_close"
                else:
                    market_session = "open"
                
                pool = engine.pool
                
                last_scan = await LatestScanService(db).get_latest_completed_scan()
                if last_scan:
                    last_scan_ts = last_scan.get("scan_timestamp")
                    last_scan_dt = datetime.datetime.fromisoformat(last_scan_ts)
                    minutes_since = (datetime.datetime.utcnow() - last_scan_dt.replace(tzinfo=None)).total_seconds() / 60.0
                    last_scan_res = "SUCCESS" if last_scan.get("valid_symbols", 0) > 0 else "NO_DATA"
                else:
                    last_scan_ts = None
                    minutes_since = 0.0
                    last_scan_res = "NONE"
                    
                cache_entries = len(get_all_cached_symbols())
                
                log_scan_environment(
                    ctx=scan_ctx,
                    token_loaded=bool(token),
                    token_source="memory" if token_service.has_cached_token() else "database",
                    token_saved_at=token_saved_at if 'token_row' in locals() and token_row else None,
                    token_age_minutes=token_age if 'token_age' in locals() else 0.0,
                    token_hash=hash_token_prefix(token),
                    app_uptime_minutes=app_uptime,
                    market_open=market_open,
                    market_session=market_session,
                    exchange_time=ist_now.strftime("%H:%M:%S"),
                    weekday=ist_now.strftime("%A"),
                    db_connected=True,
                    pool_size=pool.size(),
                    checked_out=pool.checkedout(),
                    overflow=pool.overflow(),
                    fyers_validation_result="success",
                    fyers_validation_latency_ms=val_latency_ms if 'val_latency_ms' in locals() else 0,
                    last_scan_timestamp=last_scan_ts,
                    last_scan_result=last_scan_res,
                    last_scan_source="db",
                    minutes_since_last_scan=minutes_since,
                    cache_enabled=True,
                    cache_entries=cache_entries,
                    cache_health="ok" if cache_entries > 0 else "empty"
                )
            except Exception:
                logger.exception("Failed to emit SCAN_ENVIRONMENT block")
            import datetime, os
            try:
                import psutil
            except ImportError:
                psutil = None
            start_t_iso = datetime.datetime.utcnow().isoformat()
            
            # Record scanner memory before run
            from .services.diagnostics_service import diagnostics
            mem_before = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else 0.0
            
            diagnostics.set_scanner_running()
            start_t = perf_counter()
            response = await agent.run_screener(request)
            duration_ms = int((perf_counter() - start_t) * 1000)
            
            # Record scanner memory after run
            mem_after = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else 0.0
            diagnostics.set_scanner_memory(mem_before, mem_after)
            
            # Record scanner execution log
            diagnostics.record_scanner_run({
                "scan_id": response.screener_name or f"scan-{start_t_iso}",
                "start_time": start_t_iso,
                "end_time": datetime.datetime.utcnow().isoformat(),
                "duration_ms": duration_ms,
                "requested_symbols": response.scanned_symbols,
                "valid_symbols": len(response.data_valid_symbols),
                "buy_count": len(response.buy_candidate_symbols),
                "watch_count": len(response.watch_candidate_symbols),
                "rejected_count": response.scanned_symbols - len(response.matched_symbols),
                "exception_count": response.duplicate_symbols_skipped
            })
            # Update scan context counters from response
            scan_ctx.valid = len(response.data_valid_symbols)
            scan_ctx.eligible = len(response.eligible_symbols)
            scan_ctx.matched = len(response.matched_symbols)
            scan_ctx.buy = len(response.buy_candidate_symbols)
            scan_ctx.watch = len(response.watch_candidate_symbols)
            scan_ctx.reject = response.scanned_symbols - len(response.matched_symbols)
            scan_ctx.symbols_processed = response.scanned_symbols
            
            try:
                # Still add to ScannedCandidate if it's used elsewhere
                for item in response.matches:
                    candidate = ScannedCandidate(
                        symbol=item.symbol,
                        screener_name=response.screener_name,
                        technical_score=item.technical_score,
                        technical_signal=item.technical_signal,
                        screener_score=item.screener_score,
                        matched=item.matched
                    )
                    db.add(candidate)
                    
                # New logic for PHASE S1: Persist full scan snapshot
                from .services.latest_scan_service import LatestScanService
                scan_service = LatestScanService(db)
                await scan_service.persist_successful_scan(response, duration_ms)
                
                await db.commit()
                logger.info("Saved scan candidates and latest scan snapshot to database.")
                
                diagnostics.set_scanner_success(response.screener_name or f"scan-{start_t_iso}")
                # Emit scan diagnostic summary
                token_status = "valid" if token else "missing"
                cache_status = "ok" if scan_ctx.cache_hits > 0 else "empty"
                fyers_status = "ok" if scan_ctx.fyers_failures == 0 else f"failures={scan_ctx.fyers_failures}"
                persistence_status = "ok"  # we just persisted successfully
                overall = "healthy" if scan_ctx.valid > 0 else "degraded"
                log_incident_summary(scan_ctx, token_status, cache_status, fyers_status, persistence_status, overall)
                end_scan(scan_ctx)
                logger_service.log_info(
                    message="Automated screening job completed successfully.",
                    source="JOB",
                    module="Scheduler",
                    endpoint="automated_screening_job"
                )
                logger.info("AUTOMATED SCREENING job complete")
            except Exception as db_e:
                logger.error("Failed to save scan candidates to DB: %s", db_e)
                await db.rollback()
                diagnostics.set_scanner_failed(str(db_e))
                end_scan(scan_ctx)
                logger_service.log_error(
                    message=f"Scheduled job failed to persist: {str(db_e)}",
                    source="JOB",
                    module="Scheduler",
                    endpoint="automated_screening_job",
                    exc=db_e
                )
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="automated_screening_job",
            exc=e
        )
        logger.exception("AUTOMATED SCREENING failed: %s", e)
        from .services.diagnostics_service import diagnostics
        diagnostics.set_scanner_failed(str(e))
        end_scan(scan_ctx)


async def track_strategy_drift_job():
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="Strategy drift tracker job started.",
        source="JOB",
        module="Scheduler",
        endpoint="track_strategy_drift_job"
    )
    logger.info("STRATEGY DRIFT TRACKER job triggered")
    from .services.analytics_service import AnalyticsService
    try:
        service = AnalyticsService()
        await service.track_strategy_drift()
        logger_service.log_info(
            message="Strategy drift tracker job completed successfully.",
            source="JOB",
            module="Scheduler",
            endpoint="track_strategy_drift_job"
        )
        logger.info("STRATEGY DRIFT TRACKER job complete")
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="track_strategy_drift_job",
            exc=e
        )
        logger.exception("STRATEGY DRIFT TRACKER failed: %s", e)

