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
from .db.session import SessionLocal
from .services.paper_trading_service import PaperTradingService
from .services.fyers_service import FyersService
from .services.market_engine_service import market_engine
from .db.locks import acquire_singleton_lease
from .core.task_supervisor import TaskSupervisor
# token_service refresh automation removed — manual access-token workflow only
import asyncio
from .schemas import AnalysisMode


setup_logging()
configure_logging()
try:
    init_db()
except Exception as e:
    pass # Ignore DB initialization collisions during testing
from .core import log_manager  # ensure module-level loggers (api/http) are created
request_logger = get_logger("app.http")
config_logger = get_logger("app.config")
logger = get_logger("app.scheduler")


# Scheduler for background jobs (nightly tasks)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

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
        market_engine.request_start()
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
        market_engine.heartbeat()
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
        market_engine.request_stop()
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

        with SessionLocal() as db:
            deleted = RetentionService(db).cleanup()
        logger.info("Retention cleanup complete | deleted=%s", deleted)
    except Exception:
        logger.exception("Retention cleanup failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from .config import settings
    # Startup
    if settings.app_env == "test":
        logger.info("Test environment detected; skipping scheduler and background monitors.")
        yield
        # Shutdown for test env: no scheduler running
        try:
            from .core.server_state import write_shutdown_time
            write_shutdown_time()
            print("[server_state] Shutdown time saved.")
        except Exception:
            logger.exception("Failed to write shutdown time on shutdown")
        return

    worker_lease = acquire_singleton_lease("trading-system:singleton-workers")
    app.state.singleton_worker_lease = worker_lease
    app.state.task_supervisor = TaskSupervisor()
    if not worker_lease.acquired:
        logger.warning("Another instance owns singleton workers; API-only mode enabled for this pod.")
        yield
        return

    # Ensure the candle cache DB exists before scheduling jobs
    try:
        from .services import candle_store
        from .services.screener_service import ScreenerService
        from .config import settings
        
        candle_store.init_db()
        logger.info("STARTUP PROGRESS: settings module loaded and db initialized successfully.")
        
        # Run startup validation for screener health
        screener_svc = ScreenerService()
        screener_svc.validate_startup_health(list(settings.nifty500_symbols))
        logger.info("STARTUP SUCCESS: Scanner health bootstrap completed successfully.")
    except Exception:
        logger.exception("STARTUP FATAL: Failed to run startup initialization. Crashing lifespan.")
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

    # JOB 3: Intraday Engine Heartbeat Loop (09:00 AM to 14:45 PM)
    scheduler.add_job(
        job_intraday_heartbeat,
        CronTrigger(day_of_week="mon-fri", hour="9-14", minute="0,15,30,45", timezone="Asia/Kolkata"),
        id="intraday_heartbeat_1",
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
    scheduler.start()
    logger.info("Scheduler started — nightly sync at 18:30 IST")

    # Log DB path and check for FYERS access token in DB
    try:
        import os
        from .db.session import engine
        from .services.token_service import get_current_access_token

        config_logger.info("DATABASE FILE PATH: %s", engine.url)
        config_logger.info("DATABASE FILE EXISTS: %s", os.path.exists(str(engine.url).replace("sqlite:///", "")))

        # Verify token is present
        try:
            with SessionLocal() as db:
                token = get_current_access_token(db)
                if token:
                    logger.info("STARTUP: FYERS access token loaded from DB successfully")
                else:
                    logger.warning("STARTUP: No FYERS access token found in DB. Please add via UI.")
        except Exception:
            logger.exception("Failed to read FYERS access token from DB on startup")
    except Exception:
        logger.exception("Failed to log database engine/url on startup")

    # Start the backend-driven market engine. The service boundary is intentionally
    # separate so the same loop can later be hosted in a dedicated worker process.
    try:
        await market_engine.start_loop()
    except Exception:
        logger.exception("Failed to start market engine loop")

    # Legacy monitor kept only for alert checks; position/order automation now
    # belongs to market_engine so it can survive browser closure cleanly.
    async def _monitor_positions_background():
        logger.info("Legacy alert monitor starting (every 5s)")
        fyers = FyersService()
        while True:
            try:
                db = SessionLocal()
                try:
                    service = PaperTradingService(db)
                    # Check price alerts as well
                    try:
                        alerts = service.get_active_alerts()
                        for a in alerts:
                            try:
                                ltp = await asyncio.to_thread(fyers.fetch_ltp, a.symbol)
                                if ltp is None:
                                    candles = await asyncio.to_thread(
                                        fyers.fetch_ohlcv, a.symbol, AnalysisMode.swing, "1d", 2
                                    )
                                    if candles and len(candles) > 0:
                                        ltp = candles[-1].close
                                    else:
                                        logger.warning("No price data available for alert %s; skipping", a.symbol)
                                        continue
                                if a.condition == ">=" and ltp >= a.target_price:
                                    await asyncio.to_thread(service.trigger_alert, a.id, ltp)
                                elif a.condition == "<=" and ltp <= a.target_price:
                                    await asyncio.to_thread(service.trigger_alert, a.id, ltp)
                            except Exception:
                                logger.exception("Error monitoring alert %s", a.symbol)
                    except Exception:
                        logger.exception("Failed to check price alerts")
                    try:
                        from sqlalchemy import select
                        from .models.workstation import WorkstationAlert

                        app_alerts = list(
                            db.scalars(
                                select(WorkstationAlert).where(
                                    WorkstationAlert.alert_type == "PRICE",
                                    WorkstationAlert.status == "ACTIVE",
                                )
                            )
                        )
                        for alert in app_alerts:
                            if not alert.symbol or not alert.condition or not alert.target_price:
                                continue
                            ltp = await asyncio.to_thread(fyers.fetch_ltp, alert.symbol)
                            if ltp is None:
                                continue
                            triggered = (alert.condition == ">=" and ltp >= alert.target_price) or (
                                alert.condition == "<=" and ltp <= alert.target_price
                            )
                            if triggered:
                                alert.last_triggered_at = datetime.utcnow()
                                alert.last_message = f"{alert.symbol} {alert.condition} {alert.target_price} hit at {round(ltp, 2)}"
                        db.commit()
                    except Exception:
                        logger.exception("Failed to check workstation price alerts")
                finally:
                    db.close()
            except Exception:
                logger.exception("Position monitor loop failed")
            await asyncio.sleep(5)

    # Create background task but don't await it
    try:
        app.state.task_supervisor.start("legacy-alert-monitor", _monitor_positions_background)
    except Exception:
        logger.exception("Failed to start position monitor task")

    # ADD: Run offline gap replay on startup to handle fills/exits while server was down
    try:
        from .core.gap_replay import run_gap_replay

        db = SessionLocal()
        fyers = FyersService()
        try:
            summary = run_gap_replay(db, fyers)
        finally:
            db.close()

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

    # yield control to the application
    yield
    # Shutdown
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
        worker_lease.release()
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




app.include_router(api_router)
app.include_router(fyers_router)


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
                await asyncio.to_thread(fyers.get_candles_cached, symbol, AnalysisMode.swing, "1d", 260, False)
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
    
    from .db import SessionLocal
    from .models.analysis import ScannedCandidate
    db = SessionLocal()
    
    agent = OrchestratorAgent(db)
    request = ScreenerRequest(
        mode=AnalysisMode.swing
    )
    
    try:
        logger.info("AUTOMATED SCREENING triggering scan via OrchestratorAgent")
        response = await asyncio.to_thread(agent.run_screener, request)
        try:
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
            db.commit()
            logger.info("Saved %s candidates to database.", len(response.matches))
        except Exception as db_e:
            logger.error("Failed to save scan candidates to DB: %s", db_e)
            db.rollback()
        finally:
            db.close()
            
        logger_service.log_info(
            message="Automated screening job completed successfully.",
            source="JOB",
            module="Scheduler",
            endpoint="automated_screening_job"
        )
        logger.info("AUTOMATED SCREENING job complete")
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="automated_screening_job",
            exc=e
        )
        logger.exception("AUTOMATED SCREENING failed: %s", e)


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

