"""Production-safe database bootstrap for application startup.

Order of operations (called from FastAPI lifespan):

1. Connectivity check
2. Detect fresh vs existing database
3. Alembic upgrade (when enabled) OR strict validation
4. Never ``stamp head`` on an empty database
5. Caller then runs partition verification and remaining jobs

Partition managers and other schema consumers must run *after* this module
reports schema-ready.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ..config import settings
from .session import sync_engine

logger = logging.getLogger("app.db.bootstrap")


def _alembic_paths() -> tuple[Path, Path, Path]:
    """Return (alembic.ini, script_location, versions_dir) as absolute paths."""
    # backend/app/db/bootstrap.py -> parents[2] == backend/
    backend_dir = Path(__file__).resolve().parents[2]
    ini = backend_dir / "alembic.ini"
    script = backend_dir / "alembic"
    versions = script / "versions"
    return ini, script, versions


def _make_alembic_config() -> Config:
    ini, script_loc, versions = _alembic_paths()
    if not ini.is_file():
        raise FileNotFoundError(f"Missing alembic.ini at {ini}")
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(script_loc))
    cfg.set_main_option("version_locations", str(versions))
    # env.py overrides URL from settings; keep configparser happy.
    return cfg


def _connect_with_retry(max_retries: int = 5, delay_s: float = 2.0):
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return sync_engine.connect()
        except OperationalError as e:
            last_err = e
            if attempt == max_retries:
                break
            logger.warning(
                "BOOTSTRAP | stage=connectivity | attempt=%s/%s failed: %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay_s)
    assert last_err is not None
    raise last_err


def is_fresh_database(connection) -> bool:
    """True when no Alembic revision is recorded (empty / brand-new DB)."""
    try:
        exists = connection.execute(
            text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
        ).scalar()
        if not exists:
            return True
        rows = connection.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        return len(rows) == 0
    except Exception as e:
        logger.warning("BOOTSTRAP | stage=fresh_detect | assuming fresh DB (%s)", e)
        return True


def schema_exists(connection, schema_name: str) -> bool:
    row = connection.execute(
        text(
            "SELECT 1 FROM information_schema.schemata "
            "WHERE schema_name = :s LIMIT 1"
        ),
        {"s": schema_name},
    ).fetchone()
    return row is not None


def get_script_heads() -> set[str]:
    cfg = _make_alembic_config()
    script = ScriptDirectory.from_config(cfg)
    return set(script.get_heads())


def get_db_heads(connection) -> set[str]:
    try:
        context = MigrationContext.configure(connection)
        return set(context.get_current_heads())
    except Exception as e:
        logger.warning("BOOTSTRAP | stage=read_heads | %s", e)
        return set()


def run_alembic_upgrade_head() -> None:
    """Apply all pending migrations (real upgrade — never stamp)."""
    cfg = _make_alembic_config()
    logger.info("BOOTSTRAP | stage=alembic_upgrade | starting alembic upgrade head")
    command.upgrade(cfg, "head")
    logger.info("BOOTSTRAP | stage=alembic_upgrade | completed")


def _resolve_auto_upgrade(explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    if settings.alembic_auto_upgrade:
        return True
    # Development convenience: real upgrade on empty/behind DBs (never stamp).
    env = str(settings.app_env).strip().lower()
    if env in {"development", "dev", "local"}:
        logger.info(
            "BOOTSTRAP | stage=policy | app_env=%s → alembic auto-upgrade enabled by default",
            env,
        )
        return True
    return False


def check_or_upgrade_schema(*, auto_upgrade: bool | None = None) -> dict:
    """Validate Alembic lineage; optionally upgrade when behind/fresh.

    Parameters
    ----------
    auto_upgrade:
        When None, uses settings / development defaults.
        When True, runs ``alembic upgrade head`` if current != heads.
        Never uses ``stamp head`` on an empty database.

    Returns
    -------
    dict with keys: fresh, expected_heads, current_heads, upgraded
    """
    do_upgrade = _resolve_auto_upgrade(auto_upgrade)

    logger.info("=" * 70)
    logger.info("BOOTSTRAP | stage=start | production-safe database bootstrap")
    logger.info("BOOTSTRAP | stage=connectivity | checking database")

    expected = get_script_heads()
    fresh = True
    current: set[str] = set()
    upgraded = False

    with _connect_with_retry() as connection:
        logger.info("BOOTSTRAP | stage=connectivity | ok")
        fresh = is_fresh_database(connection)
        current = set() if fresh else get_db_heads(connection)

        logger.info(
            "BOOTSTRAP | stage=detect | fresh_database=%s | current=%s | expected=%s | auto_upgrade=%s",
            fresh,
            sorted(current),
            sorted(expected),
            do_upgrade,
        )
        if fresh:
            logger.info(
                "BOOTSTRAP | stage=detect | brand-new database "
                "(no alembic_version / no revisions)"
            )

        if expected == current:
            if connection.dialect.name == "postgresql" and not schema_exists(
                connection, "market_data"
            ):
                logger.warning(
                    "BOOTSTRAP | stage=schema_verify | revision at head but "
                    "schema market_data missing — partitions will skip until fixed"
                )
            logger.info(
                "BOOTSTRAP | stage=alembic_ok | already at head | current=%s",
                sorted(current),
            )
            logger.info("BOOTSTRAP | stage=complete | database ready for app services")
            logger.info("=" * 70)
            return {
                "fresh": fresh,
                "expected_heads": expected,
                "current_heads": current,
                "upgraded": False,
            }

        if not do_upgrade:
            msg = (
                f"\nSCHEMA VALIDATION FAILED\n"
                f"Database Revision: {sorted(current)}\n"
                f"Expected Revision: {sorted(expected)}\n"
                f"Fresh database: {fresh}\n\n"
                f"Refusing startup.\n\n"
                f"RECOVERY:\n"
                f"  - Apply schema:  alembic -c backend/alembic.ini upgrade head\n"
                f"    or:            python backend/scripts/run_migrations.py\n"
                f"  - Or set ALEMBIC_AUTO_UPGRADE=true for automatic upgrade at boot\n"
                f"  - Do NOT use 'alembic stamp head' on an empty database\n"
            )
            logger.critical(msg)
            raise RuntimeError(msg)

        if fresh:
            logger.info(
                "BOOTSTRAP | stage=migrate | empty DB — running alembic upgrade head "
                "(NOT stamp head)"
            )
        else:
            logger.info(
                "BOOTSTRAP | stage=migrate | behind head — running alembic upgrade head"
            )

    # Upgrade uses its own connections (outside the validation connection).
    run_alembic_upgrade_head()
    upgraded = True

    with sync_engine.connect() as verify_conn:
        current = get_db_heads(verify_conn)
        fresh = is_fresh_database(verify_conn)
        if expected != current:
            msg = (
                f"\nSCHEMA VALIDATION FAILED after upgrade\n"
                f"Database Revision: {sorted(current)}\n"
                f"Expected Revision: {sorted(expected)}\n"
            )
            logger.critical(msg)
            raise RuntimeError(msg)
        if verify_conn.dialect.name == "postgresql":
            if not schema_exists(verify_conn, "market_data"):
                raise RuntimeError(
                    "Migrations completed but schema 'market_data' is missing. "
                    "Check migration bb33b6e44683_market_data_cache_schema."
                )
            logger.info("BOOTSTRAP | stage=schema_verify | schema market_data present")

    logger.info(
        "BOOTSTRAP | stage=alembic_ok | current=%s | upgraded=%s",
        sorted(current),
        upgraded,
    )
    logger.info("BOOTSTRAP | stage=complete | database ready for app services")
    logger.info("=" * 70)
    return {
        "fresh": fresh,
        "expected_heads": expected,
        "current_heads": current,
        "upgraded": upgraded,
    }


def check_alembic_head() -> None:
    """Backward-compatible gate: validate (and auto-upgrade when configured)."""
    check_or_upgrade_schema(auto_upgrade=None)
