from .core.logger import setup_logging
setup_logging()

from datetime import datetime
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routes import api_router
from .routes.fyers import router as fyers_router
from .utils import configure_logging, get_logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.app.services.candle_store import (
    get_all_cached_symbols,
    is_cache_fresh,
    get_last_stored_date,
)
from backend.app.db.session import SessionLocal
from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.services.fyers_service import FyersService
# token_service refresh automation removed — manual access-token workflow only
import asyncio
from backend.app.schemas import AnalysisMode


configure_logging()
init_db()
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

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://trading-system-frontend.vercel.app",
    "https://trading-system01.vercel.app",
],
 allow_origin_regex=r"(http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app)",    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_requests(request, call_next):
    started_at = perf_counter()
    request_logger.info(
        "HTTP request start | method=%s | path=%s | client=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
        request_logger.exception(
            "HTTP request failed | method=%s | path=%s | elapsed_ms=%s",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    request_logger.info(
        "HTTP request end | method=%s | path=%s | status=%s | elapsed_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


app.include_router(api_router)
app.include_router(fyers_router)


async def nightly_candle_sync():
    logger.info("NIGHTLY SYNC started")
    from backend.app.services.fyers_service import FyersService
    fyers = FyersService()
    symbols = get_all_cached_symbols()
    stale = [s for s in symbols if not is_cache_fresh(s)]
    logger.info("NIGHTLY SYNC stale_symbols=%s total=%s", len(stale), len(symbols))
    import asyncio
    from backend.app.schemas import AnalysisMode
    for symbol in stale:
        try:
            # Run the synchronous cache-refresh in a thread so we don't block the event loop
            await asyncio.to_thread(fyers.get_candles_cached, symbol, AnalysisMode.swing, "1d", 260, False)
            logger.info("NIGHTLY SYNC refreshed symbol=%s", symbol)
        except Exception as e:
            logger.error("NIGHTLY SYNC failed symbol=%s error=%s", symbol, e)
    logger.info("NIGHTLY SYNC complete")


@app.on_event("startup")
async def startup_event():
    # Ensure the candle cache DB exists before scheduling jobs
    try:
        from backend.app.services import candle_store
        candle_store.init_db()
    except Exception:
        logger.exception("Failed to init candle_store DB on startup")

    scheduler.add_job(
        nightly_candle_sync,
        CronTrigger(hour=18, minute=30, timezone="Asia/Kolkata"),
        id="nightly_candle_sync",
        replace_existing=True,
    )
    # FYERS refresh automation removed. Manual access-token workflow only.
    scheduler.start()
    logger.info("Scheduler started — nightly sync at 18:30 IST")

    # Start the positions monitor background task
    async def _monitor_positions_background():
        logger.info("Position monitor starting (every 5s)")
        fyers = FyersService()
        while True:
            try:
                db = SessionLocal()
                try:
                    service = PaperTradingService(db)
                    account = service._get_or_create_account()
                    positions = service._position_models(account.id)
                    for pos in positions:
                        try:
                            # Fetch LTP in a thread to avoid blocking event loop
                            ltp = await asyncio.to_thread(fyers.fetch_ltp, pos.symbol)
                            if ltp is None:
                                candles = await asyncio.to_thread(
                                    fyers.fetch_ohlcv, pos.symbol, AnalysisMode.swing, "1d", 2
                                )
                                if candles and len(candles) > 0:
                                    ltp = candles[-1].close
                                else:
                                    logger.warning("No price data available for %s; skipping monitoring", pos.symbol)
                                    continue
                            if pos.target is not None and ltp >= pos.target:
                                await asyncio.to_thread(service.auto_exit, pos.id, ltp, "TARGET_HIT")
                            elif pos.stop_loss is not None and ltp <= pos.stop_loss:
                                await asyncio.to_thread(service.auto_exit, pos.id, ltp, "STOPLOSS_HIT")
                        except Exception:
                            logger.exception("Error monitoring position %s", pos.symbol)
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
                        from backend.app.models.workstation import WorkstationAlert

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
        asyncio.create_task(_monitor_positions_background())
    except Exception:
        logger.exception("Failed to start position monitor task")

    # ADD: Run offline gap replay on startup to handle fills/exits while server was down
    try:
        from backend.app.core.gap_replay import run_gap_replay

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
                print(f"  ⚠️  {w}")
    except Exception as e:
        logger.exception("GAP_REPLAY startup failed: %s", e)
        print(f"[GAP_REPLAY] Startup replay failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    try:
        from backend.app.core.server_state import write_shutdown_time

        write_shutdown_time()
        print("[server_state] Shutdown time saved.")
    except Exception:
        logger.exception("Failed to write shutdown time on shutdown")
