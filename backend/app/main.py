import sys
from pathlib import Path

# Ensure backend/ is on sys.path so 'app' is importable as a top-level package
# (uvicorn imports backend.app.main which makes backend findable, but nested
#  files using 'from app.xxx import yyy' need 'app' on sys.path)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Ensure repo root is on sys.path so root modules like `fyers_token.py` import
# correctly when uvicorn is started with cwd=backend (start_backend.ps1).
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Load repo-root .env into os.environ before any route reads secrets
# (e.g. SCHEDULER_SECRET via os.environ.get). Pydantic settings alone does not
# populate os.environ for non-Settings keys.
try:
    from dotenv import load_dotenv

    load_dotenv(_repo_root / ".env", override=False)
except Exception:
    pass

from time import perf_counter
from contextlib import asynccontextmanager

from .utils.datetime_utils import (
    age_minutes,
    ensure_utc,
    ist_now,
    minutes_between,
    parse_utc,
    to_iso_utc,
    utc_now,
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
import traceback
from .services.db_logger import log_to_db

from .core.logger import setup_logging
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
from apscheduler.triggers.interval import IntervalTrigger
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
# Daily access-token automation: see token_scanner_bootstrap_service
# (startup: ensure today's token → auto Market Scanner once/day).
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
# Settings() runs before handlers exist; re-emit SMTP status so console/file show it.
try:
    settings.log_smtp_config_snapshot()
except Exception as _smtp_log_exc:  # pragma: no cover
    config_logger.warning("Could not log SMTP config snapshot: %s", _smtp_log_exc)


from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_SUBMITTED

# Scheduler for background jobs (nightly tasks)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

_job_starts = {}
def _scheduler_listener(event):
    from .services.diagnostics_service import diagnostics
    import time

    scheduled_time = getattr(event, "scheduled_run_time", None)
    scheduled_time_str = scheduled_time.isoformat() if scheduled_time else "unknown"
    actual_time_str = utc_now().isoformat()
    
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


async def job_execute_pending_market_open_orders():
    """At market open, execute all PENDING_MARKET_OPEN paper orders across accounts."""
    from .services.logger_service import logger_service
    logger_service.log_info(
        message="Pending market-open order execution triggered.",
        source="JOB",
        module="Scheduler",
        endpoint="job_execute_pending_market_open_orders",
    )
    try:
        from .services.paper_trading_service import PaperTradingService

        summary = await asyncio.to_thread(PaperTradingService.execute_all_pending_market_open_orders)
        logger_service.log_info(
            message=f"Pending market-open execution complete: {summary}",
            source="JOB",
            module="Scheduler",
            endpoint="job_execute_pending_market_open_orders",
        )
        logger.info("MARKET_OPEN_TRIGGER | job_summary=%s", summary)
    except Exception as e:
        logger_service.log_error(
            message=f"Scheduled job failed: {str(e)}",
            source="JOB",
            module="Scheduler",
            endpoint="job_execute_pending_market_open_orders",
            exc=e,
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


async def job_weekly_rule_governance_report():
    """FEAT-026: weekly on-schedule governance evaluation for promoted rules."""
    try:
        from .db.session import AsyncSessionLocal
        from .governance.rule_governance import (
            evaluate_all_promoted_rules,
            persist_governance_report,
        )

        async with AsyncSessionLocal() as db:
            response = await evaluate_all_promoted_rules(db)
        try:
            path = persist_governance_report(response)
            logger.info(
                "WEEKLY_RULE_GOVERNANCE_OK | rules=%s | path=%s | evaluated_at=%s",
                response.promoted_rules_count,
                path,
                response.evaluated_at,
            )
        except Exception:
            # Evaluation succeeded; persistence failure must not mark job as total failure only.
            logger.exception(
                "WEEKLY_RULE_GOVERNANCE_PERSIST_FAILED | rules=%s | evaluated_at=%s",
                response.promoted_rules_count,
                response.evaluated_at,
            )
    except Exception:
        logger.exception("WEEKLY_RULE_GOVERNANCE_FAILED")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from .config import settings
    import asyncio
    from .db import session as session_module
    import anyio
    session_module.main_event_loop = asyncio.get_running_loop()
    
    logger.info("APP_START | Application is starting")
    try:
        # Make DB target visible immediately — avoids confusion when multiple Neon projects exist.
        db_target = settings.database_url.split("@")[-1] if "@" in settings.database_url else "(local/unknown)"
        # Never log credentials; host/db path only.
        logger.info("DATABASE_TARGET | %s", db_target.split("?")[0])
    except Exception:
        pass
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
        import app.models  # ensure all models are registered
        
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
            from .core.redis import close_redis_client
            await close_redis_client()
        except Exception:
            logger.exception("Failed to close Redis client on test shutdown")
        try:
            from .core.server_state import write_shutdown_time
            write_shutdown_time()
            print("[server_state] Shutdown time saved.")
        except Exception:
            logger.exception("Failed to write shutdown time on shutdown")
        return

    try:
        worker_lease = await acquire_singleton_lease("trading-system:singleton-workers")
    except Exception as db_exc:
        # Common local-dev failure: Neon free-tier data transfer / compute quota.
        msg = str(db_exc)
        logger.error("DATABASE_STARTUP_FAILURE | error_type=%s | error=%s", type(db_exc).__name__, msg[:300])
        if "data transfer quota" in msg.lower() or "exceeded" in msg.lower() and "quota" in msg.lower():
            logger.error(
                "DATABASE_QUOTA_EXCEEDED | Neon (or your cloud Postgres) rejected the connection because "
                "the project data-transfer quota is exhausted. The API cannot start until DATABASE_URL "
                "points at a reachable database. Fix options: (1) upgrade/reset Neon quota, "
                "(2) create a new Neon project and update DATABASE_URL in the repo root .env, "
                "(3) install local PostgreSQL and set DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
            )
        elif "connect" in msg.lower() or "refused" in msg.lower() or "timeout" in msg.lower():
            logger.error(
                "DATABASE_UNREACHABLE | Could not connect using DATABASE_URL. "
                "Check that Postgres is running and DATABASE_URL in the repo root .env is correct."
            )
        raise RuntimeError(
            f"Database unavailable during startup ({type(db_exc).__name__}). "
            "See DATABASE_* log lines above for fix steps."
        ) from db_exc
    app.state.singleton_worker_lease = worker_lease
    app.state.task_supervisor = TaskSupervisor()
    
    from .services.partition_manager import verify_and_create_partitions
    try:
        await verify_and_create_partitions()
    except Exception as e:
        logger.error(f"Failed to verify partitions: {e}")

    # JWT secret hardening (production/staging fail-closed).
    try:
        from .config import settings as _settings_for_jwt
        from .core.security import assert_jwt_secrets_safe_for_env

        assert_jwt_secrets_safe_for_env(_settings_for_jwt.app_env)
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("JWT secret safety check skipped: %s", e)

    from .config import settings as _startup_settings

    def _is_prod_like() -> bool:
        return str(_startup_settings.app_env).strip().lower() in {"production", "prod", "staging"}

    if not worker_lease.acquired:
        logger.warning("Another instance owns singleton workers; API-only mode enabled for this pod.")
        # Still ensure schema + default admin on API-only pods after migration gate.
        try:
            from .db.session import check_alembic_head
            from .services.admin_bootstrap_service import ensure_default_admin_safe
            from .services.feature_permission_service import (
                assert_feature_permissions_table_ready,
                ensure_default_feature_permissions,
            )

            check_alembic_head()
            async with AsyncSessionLocal() as admin_db_session:
                await ensure_default_admin_safe(admin_db_session, fail_closed=_is_prod_like())
            # Sprint 3: table readiness (M-5) + idempotent catalog seed (H-1: commit on dedicated session)
            try:
                async with AsyncSessionLocal() as fp_db:
                    await assert_feature_permissions_table_ready(
                        fp_db, fail_closed=_is_prod_like()
                    )
                    inserted = await ensure_default_feature_permissions(
                        fp_db, commit=True
                    )
                    if inserted:
                        logger.info("FEATURE_PERMISSIONS_SEEDED | inserted=%s", inserted)
            except Exception as fp_exc:
                if _is_prod_like():
                    logger.critical("FEATURE_PERMISSIONS_SEED | fatal: %s", fp_exc)
                    raise
                logger.warning("FEATURE_PERMISSIONS_SEED | skipped/failed: %s", fp_exc)
        except Exception as e:
            if _is_prod_like():
                logger.critical("API-only pod migration/admin bootstrap failed fatally: %s", e)
                raise
            logger.warning("API-only pod migration/admin bootstrap check failed: %s", e)
        yield
        return
    try:
        from .services.screener_service import ScreenerService
        from .config import settings
        from .db.session import check_alembic_head
        
        # Enforce Alembic Migration Gate BEFORE admin bootstrap (H-4).
        logger.info("STARTUP PROGRESS: Validating database schema lineage...")
        check_alembic_head()
        logger.info("STARTUP PROGRESS: Database schema is up-to-date.")

        # Default admin seed only after schema is current (FR-011..014).
        try:
            from .services.admin_bootstrap_service import ensure_default_admin_safe

            async with AsyncSessionLocal() as admin_db_session:
                await ensure_default_admin_safe(admin_db_session, fail_closed=_is_prod_like())
        except Exception as e:
            if _is_prod_like():
                logger.critical("Default admin bootstrap failed fatally: %s", e)
                raise
            logger.warning("Default admin bootstrap check failed: %s", e)

        # Sprint 3: feature permission table readiness + catalog seed (after schema gate).
        try:
            from .services.feature_permission_service import (
                assert_feature_permissions_table_ready,
                ensure_default_feature_permissions,
            )

            async with AsyncSessionLocal() as fp_db:
                await assert_feature_permissions_table_ready(
                    fp_db, fail_closed=_is_prod_like()
                )
                inserted = await ensure_default_feature_permissions(
                    fp_db, commit=True
                )
                if inserted:
                    logger.info("FEATURE_PERMISSIONS_SEEDED | inserted=%s", inserted)
                else:
                    logger.info("FEATURE_PERMISSIONS_SEED | catalog already present")
        except Exception as e:
            if _is_prod_like():
                logger.critical("FEATURE_PERMISSIONS_SEED | fatal: %s", e)
                raise
            # Non-prod: list/update paths also ensure seeds; log for ops visibility.
            logger.warning("FEATURE_PERMISSIONS_SEED | failed: %s", e)

        # Drop any async connections that may hold prepared plans from before DDL
        try:
            from .db.session import dispose_async_pool

            await dispose_async_pool(reason="post_alembic_startup")
        except Exception:
            logger.warning("Could not dispose async DB pool after alembic check", exc_info=True)
        
        logger.info("STARTUP PROGRESS: settings module loaded successfully.")
        
        # Run startup validation for screener health
        from .services.universe_service import UniverseService
        active_symbols = await UniverseService.get_all_active_symbols()
        count = len(active_symbols)
        logger.info(f"UNIVERSE_LOADED | count={count}")

        if count == 0:
            logger.warning("Universe is empty. Attempting automatic seed from bundled ind_nifty500list.csv ...")
            try:
                from pathlib import Path

                repo_root = Path(__file__).resolve().parents[2]
                if str(repo_root) not in sys.path:
                    sys.path.insert(0, str(repo_root))

                # Try several import styles that work in different runtimes (Render, local, uvicorn -m, etc.)
                import_csv = None
                for mod_name in [
                    "backend.scripts.import_stocks_master",
                    "scripts.import_stocks_master",
                    "import_stocks_master",
                ]:
                    try:
                        mod = __import__(mod_name, fromlist=["import_csv"])
                        import_csv = getattr(mod, "import_csv")
                        break
                    except Exception:
                        pass

                if import_csv is None:
                    # Last resort: run the script via subprocess (synchronous but acceptable at startup)
                    import subprocess
                    csv_path = str(repo_root / "ind_nifty500list.csv")
                    cmd = [sys.executable, str(repo_root / "backend" / "scripts" / "import_stocks_master.py"), csv_path, "NIFTY500"]
                    subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(repo_root))
                else:
                    csv_path = str(repo_root / "ind_nifty500list.csv")
                    await import_csv(csv_path, "NIFTY500")

                active_symbols = await UniverseService.get_all_active_symbols()
                count = len(active_symbols)
                logger.info(f"UNIVERSE_LOADED after auto-seed | count={count}")
            except Exception as seed_err:
                logger.exception("Auto-seed of stocks_master failed: %s", seed_err)

        if count == 0:
            if settings.require_universe_data:
                raise RuntimeError(
                    "Startup failed: Universe count is 0 after auto-seed attempt. "
                    "Please ensure ind_nifty500list.csv is present and DATABASE_URL is correct. "
                    "(Manual: python backend/scripts/import_stocks_master.py ind_nifty500list.csv NIFTY500)"
                )
            else:
                logger.warning("UNIVERSE EMPTY but REQUIRE_UNIVERSE_DATA=false — continuing in degraded mode.")

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

    # JOB 2: Pre-Market Deep Scan (Disabled)
    logger.info("Automatic scheduled scanner execution is disabled.")
    # scheduler.add_job(
    #     automated_screening_job,
    #     CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone="Asia/Kolkata"),
    #     id="pre_market_deep_scan",
    #     replace_existing=True,
    # )

    # JOB 3a: Intraday Engine Heartbeat Loop (09:15 AM to 09:45 AM)
    scheduler.add_job(
        job_intraday_heartbeat,
        CronTrigger(day_of_week="mon-fri", hour=9, minute="15,30,45", timezone="Asia/Kolkata"),
        id="intraday_heartbeat_1a",
        replace_existing=True,
    )

    # JOB 3a2: Execute after-hours paper orders at market open (09:15 IST)
    scheduler.add_job(
        job_execute_pending_market_open_orders,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=15, timezone="Asia/Kolkata"),
        id="execute_pending_market_open_orders",
        replace_existing=True,
        max_instances=1,
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

    # JOB 6: Diagnostics alert evaluation (every 10s — NFR-002)
    from .observability.alert_jobs import (
        evaluate_system_alerts_job,
        rotate_observability_logs_job,
    )

    # Evaluate every 30s (NFR-002 is 10s breach-to-alert budget; 30s keeps
    # load low while still meeting Phase 0 thresholds for most metrics).
    scheduler.add_job(
        evaluate_system_alerts_job,
        IntervalTrigger(seconds=30),
        id="diagnostics_alert_evaluation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # JOB 7: Observability JSONL retention (90 days — NFR-004)
    scheduler.add_job(
        rotate_observability_logs_job,
        CronTrigger(hour=3, minute=0, timezone="Asia/Kolkata"),
        id="observability_log_rotation",
        replace_existing=True,
    )

    # JOB 8: Weekly Production Rule Governance report (FEAT-026 / FR-001)
    scheduler.add_job(
        job_weekly_rule_governance_report,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone="Asia/Kolkata"),
        id="weekly_rule_governance_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Clear in-memory FYERS quarantine on every app start
    from .services.fyers_service import QUARANTINED_SYMBOLS
    QUARANTINED_SYMBOLS.clear()
    logger.info("FYERS in-memory symbol quarantine cleared on startup")

    # Scheduler + automatic daily Access Token → Market Scanner bootstrap.
    # Token generation uses existing fyers_token retry policy; scanner starts only
    # after a confirmed valid token is saved and cached (once per IST day).
    if not settings.quarantine_mode:
        scheduler.start()
        logger.info("SCHEDULER_STARTED | timezone=%s | jobs_registered=%d", str(scheduler.timezone), len(scheduler.get_jobs()))
    else:
        logger.info("QUARANTINE MODE: Scheduler execution bypassed.")

    # Log DB path + schedule automatic token→scanner workflow
    try:
        from .db.session import engine

        config_logger.info("DATABASE URL: %s", engine.url)
    except Exception:
        logger.exception("Failed to log database engine/url on startup")

    if not settings.quarantine_mode:
        try:
            from .services.token_scanner_bootstrap_service import schedule_startup_bootstrap

            schedule_startup_bootstrap(app.state)
            logger.info(
                "STARTUP: Automatic token→scanner bootstrap scheduled "
                "(generate/validate/save if needed, then scanner once/day)"
            )
        except Exception:
            logger.exception(
                "Failed to schedule automatic token→scanner bootstrap on startup"
            )
    else:
        logger.info("QUARANTINE MODE: Automatic token→scanner bootstrap bypassed.")

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
                                alert.last_triggered_at = utc_now()
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
    try:
        from .core.redis import close_redis_client
        await close_redis_client()
    except Exception:
        logger.exception("Failed to close Redis client on shutdown")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
# Compress JSON responses > 500 bytes (reduces payload for dashboard/analytics)
app.add_middleware(GZipMiddleware, minimum_size=500)
# CORS for SPA on Vercel (incl. preview URLs) talking to Render API with credentials.
# Do NOT use allow_origins=["*"] with allow_credentials=True — browsers reject it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=(
        r"https://.*\.vercel\.app"
        r"|https://.*\.onrender\.com"
        r"|http://(localhost|127\.0\.0\.1):\d+"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)
# Correlation ID propagation (X-Correlation-ID request/response header).
from .middleware import CorrelationIdMiddleware  # noqa: E402

app.add_middleware(CorrelationIdMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch unhandled exceptions, mask secrets in logs, and return a safe 500 body.
    Does not override FastAPI/Starlette HTTPException handlers (more specific).
    """
    from fastapi import HTTPException as FastAPIHTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from fastapi.exceptions import RequestValidationError

    if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException, RequestValidationError)):
        raise exc

    from .services.logger_service import logger_service

    cid = getattr(request.state, "correlationId", None) or request.headers.get("X-Correlation-ID")
    endpoint = f"{request.method} {request.url.path}"
    try:
        logger_service.log_error(
            module="global_exception_handler",
            message=str(exc),
            exc=exc,
            endpoint=endpoint,
            correlationId=cid,
        )
        await logger_service.flush_now()
        # Prevent middleware safety-net from double-logging the same exception (L-1).
        request.state.exception_logged = True
    except Exception:
        logger.exception("Failed to persist global exception log")

    headers = {"X-Correlation-ID": cid} if cid else None
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected system error occurred. This has been logged for our engineers."},
        headers=headers,
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
        # BaseHTTPMiddleware may re-surface route exceptions even after the app
        # exception handler runs — convert to a safe 500 here as a safety net.
        elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
        request_logger.exception(
            "HTTP request failed | method=%s | path=%s | elapsed_ms=%s",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        cid = getattr(request.state, "correlationId", None) or request.headers.get("X-Correlation-ID")
        # Skip DB log if global_exception_handler already persisted this failure.
        if not getattr(request.state, "exception_logged", False):
            from .services.logger_service import logger_service

            endpoint = f"{request.method} {request.url.path}"
            try:
                logger_service.log_error(
                    module="global_exception_handler",
                    message=str(exc),
                    exc=exc,
                    endpoint=endpoint,
                    correlationId=cid,
                )
                await logger_service.flush_now()
                request.state.exception_logged = True
            except Exception:
                logger.exception("Failed to persist middleware exception log")
        headers = {"X-Correlation-ID": cid} if cid else None
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected system error occurred. This has been logged for our engineers."},
            headers=headers,
        )

    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    # Performance log: route execution time (surface slow endpoints)
    slow = elapsed_ms >= 1000
    log_fn = request_logger.warning if slow else request_logger.info
    log_fn(
        "HTTP request end | method=%s | path=%s | status=%s | elapsed_ms=%s | slow=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        slow,
    )
    # Expose server timing for browser/devtools without changing response body
    try:
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms}"
    except Exception:
        pass
    
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
from .routers.walk_forward import router as walk_forward_router
from .routers.event_calendar import router as event_calendar_router

app.include_router(api_router)
app.include_router(fyers_router)
app.include_router(scheduler_router.router)
app.include_router(walk_forward_router)
app.include_router(event_calendar_router)


@app.middleware("http")
async def diagnostics_rate_monitor_middleware(request: Request, call_next):
    from .observability.rate_monitor import record_request, record_error
    record_request()
    response = await call_next(request)
    if response.status_code >= 400:
        record_error()
    return response


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
    from .db.session import AsyncSessionLocal, SessionLocal, is_db_connection_error, dispose_async_pool
    from .models.analysis import ScannedCandidate
    try:
        from .services import token_service
        from .services.fyers_service import FyersService, FyersAuthInvalidError, FyersAuthExpiredError, FyersAPIError

        request = ScreenerRequest(mode=AnalysisMode.swing)
        token = None
        val_latency_ms = 0
        token_saved_at: str | None = None
        token_age: float = 0.0

        # ------------------------------------------------------------------
        # Phase A — preflight only. Postgres sets idle_in_transaction_session_timeout
        # to 30s on connect; holding one session open across the multi-minute
        # screener run is what produced "connection is closed" on persist.
        # ------------------------------------------------------------------
        async with AsyncSessionLocal() as db:
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
                token_row = await token_service.get_fyers_token_row(db)
                if token_row and token_row.access_token_saved_at:
                    saved_utc = ensure_utc(token_row.access_token_saved_at)
                    token_saved_at = to_iso_utc(saved_utc)
                    token_age = age_minutes(saved_utc)
                else:
                    token_saved_at = "N/A"
                    token_age = 0.0
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

            try:
                from .observability.scan_diagnostics import _PROCESS_START_TIME
                from .db.session import engine
                from .services.latest_scan_service import LatestScanService
                from .services.candle_store import get_all_cached_symbols

                startup_dt = parse_utc(_PROCESS_START_TIME)
                app_uptime = age_minutes(startup_dt) if startup_dt is not None else 0.0
                exchange_now = ist_now()
                pool = engine.pool
                last_scan = await LatestScanService(db).get_latest_completed_scan()
                if last_scan:
                    last_scan_ts = last_scan.get("scan_timestamp")
                    last_scan_dt = parse_utc(last_scan_ts)
                    if last_scan_dt is not None:
                        minutes_since = minutes_between(utc_now(), last_scan_dt)
                    else:
                        minutes_since = 0.0
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
                    token_saved_at=token_saved_at,
                    token_age_minutes=token_age,
                    token_hash=hash_token_prefix(token),
                    app_uptime_minutes=app_uptime,
                    exchange_time=exchange_now.strftime("%H:%M:%S"),
                    weekday=exchange_now.strftime("%A"),
                    db_connected=True,
                    pool_size=pool.size(),
                    checked_out=pool.checkedout(),
                    overflow=pool.overflow(),
                    fyers_validation_result="pending",
                    fyers_validation_latency_ms=0,
                    last_scan_timestamp=last_scan_ts,
                    last_scan_result=last_scan_res,
                    last_scan_source="db",
                    minutes_since_last_scan=minutes_since,
                    cache_enabled=True,
                    cache_entries=cache_entries,
                    cache_health="ok" if cache_entries > 0 else "empty",
                )
            except Exception:
                logger.exception("Failed to emit SCAN_ENVIRONMENT block")

            # Drop any open transaction before the long external I/O below.
            try:
                await db.rollback()
            except Exception:
                pass

        # Token validation does not need a DB session (avoids idle-in-transaction).
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
            try:
                async with AsyncSessionLocal() as db:
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
            except Exception:
                pass
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

        # ------------------------------------------------------------------
        # Phase B — long screener run with NO open DB session/transaction.
        # OrchestratorAgent does not use the injected db handle.
        # ------------------------------------------------------------------
        logger.info("AUTOMATED SCREENING triggering scan via OrchestratorAgent")
        import os
        try:
            import psutil
        except ImportError:
            psutil = None
        start_t_iso = utc_now().isoformat()

        from .services.diagnostics_service import diagnostics
        mem_before = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else 0.0

        diagnostics.set_scanner_running()
        agent = OrchestratorAgent(None)
        start_t = perf_counter()
        response = await agent.run_screener(request)
        duration_ms = int((perf_counter() - start_t) * 1000)

        mem_after = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else 0.0
        diagnostics.set_scanner_memory(mem_before, mem_after)

        diagnostics.record_scanner_run({
            "scan_id": response.screener_name or f"scan-{start_t_iso}",
            "start_time": start_t_iso,
            "end_time": utc_now().isoformat(),
            "duration_ms": duration_ms,
            "requested_symbols": response.scanned_symbols,
            "valid_symbols": len(response.data_valid_symbols),
            "buy_count": len(response.buy_candidate_symbols),
            "watch_count": len(response.watch_candidate_symbols),
            "rejected_count": response.scanned_symbols - len(response.matched_symbols),
            "exception_count": response.duplicate_symbols_skipped,
        })
        scan_ctx.valid = len(response.data_valid_symbols)
        scan_ctx.eligible = len(response.eligible_symbols)
        scan_ctx.matched = len(response.matched_symbols)
        scan_ctx.buy = len(response.buy_candidate_symbols)
        scan_ctx.watch = len(response.watch_candidate_symbols)
        scan_ctx.reject = response.scanned_symbols - len(response.matched_symbols)
        scan_ctx.symbols_processed = response.scanned_symbols

        # ------------------------------------------------------------------
        # Phase C — fresh session for canonical/history writes (+ one retry).
        # ------------------------------------------------------------------
        from .config.settings import settings as _scan_settings
        from .services.latest_scan_service import LatestScanService

        _minimal = False
        try:
            _minimal = bool(_scan_settings.is_scan_result_minimal_writes())
        except Exception:
            _minimal = False

        for attempt in range(2):
            try:
                async with AsyncSessionLocal() as db:
                    if not _minimal:
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
                    else:
                        logger.info(
                            "SCAN_RESULT_MINIMAL_WRITES=ON | skipping scanned_candidates writes"
                        )

                    scan_service = LatestScanService(db)
                    await scan_service.persist_successful_scan(
                        response, duration_ms, minimal_writes=_minimal
                    )
                    await db.commit()

                logger.info("Saved scan candidates and latest scan snapshot to database.")
                diagnostics.set_scanner_success(response.screener_name or f"scan-{start_t_iso}")
                token_status = "valid" if token else "missing"
                cache_status = "ok" if scan_ctx.cache_hits > 0 else "empty"
                fyers_status = "ok" if scan_ctx.fyers_failures == 0 else f"failures={scan_ctx.fyers_failures}"
                persistence_status = "ok"
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
                break
            except Exception as db_e:
                if attempt == 0 and is_db_connection_error(db_e):
                    logger.warning(
                        "Scheduled scan persist hit dead DB connection; disposing pool and retrying once | error=%s",
                        db_e,
                    )
                    try:
                        await dispose_async_pool(reason="scheduled_scan_persist_connection_closed")
                    except Exception:
                        pass
                    continue
                logger.error(
                    "Failed to save scan candidates to DB%s: %s",
                    " after retry" if attempt > 0 else "",
                    db_e,
                )
                diagnostics.set_scanner_failed(str(db_e))
                end_scan(scan_ctx)
                logger_service.log_error(
                    message=f"Scheduled job failed to persist: {str(db_e)}",
                    source="JOB",
                    module="Scheduler",
                    endpoint="automated_screening_job",
                    exc=db_e
                )
                break
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

