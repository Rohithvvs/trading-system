import logging
from datetime import datetime, timezone

from sqlalchemy import text

from ..db.session import AsyncSessionLocal

logger = logging.getLogger("app.partition_manager")


async def _market_data_ready(db) -> bool:
    """Return True only when market_data schema and parent candle tables exist."""
    schema = await db.execute(
        text(
            "SELECT 1 FROM information_schema.schemata "
            "WHERE schema_name = 'market_data' LIMIT 1"
        )
    )
    if schema.scalar() is None:
        logger.warning(
            "PARTITION_MANAGER | skip | schema market_data does not exist — "
            "run alembic upgrade head before partition creation"
        )
        return False

    for parent in ("candles_1d", "candles_15m", "candles_1m"):
        res = await db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'market_data' AND table_name = :t LIMIT 1"
            ),
            {"t": parent},
        )
        if res.scalar() is None:
            logger.warning(
                "PARTITION_MANAGER | skip | parent table market_data.%s missing — "
                "migrations incomplete",
                parent,
            )
            return False
    return True


async def verify_and_create_partitions():
    """
    Called at application startup *after* Alembic migrations have applied.

    Verifies that the current and next partitions exist for all resolutions.
    Auto-creates them if they do not exist.

    Safe on brand-new databases: if the market_data schema (or parent tables)
    are missing, logs and returns without raising InvalidSchemaNameError.
    """
    now = datetime.now(timezone.utc)
    # We want to check this month/year and the next month/year

    # 1D is partitioned YEARLY
    current_year = now.year

    partitions_to_create = []

    for y in range(current_year - 3, current_year + 2):
        partitions_to_create.append(
            {
                "parent": "candles_1d",
                "name": f"candles_1d_y{y}",
                "from_val": f"'{y}-01-01 00:00:00+00'",
                "to_val": f"'{y + 1}-01-01 00:00:00+00'",
            }
        )

    # Intraday is partitioned MONTHLY
    for res in ["15m", "1m"]:
        # Create partitions for the past 4 months, current month, and next month
        for m_offset in range(-4, 2):
            target_date = now.replace(day=1)
            # handle month math manually
            month_abs = target_date.month - 1 + m_offset
            t_year = target_date.year + (month_abs // 12)
            t_month = (month_abs % 12) + 1

            n_year = t_year + ((t_month) // 12)
            n_month = (t_month % 12) + 1

            partitions_to_create.append(
                {
                    "parent": f"candles_{res}",
                    "name": f"candles_{res}_y{t_year}_m{t_month:02d}",
                    "from_val": f"'{t_year}-{t_month:02d}-01 00:00:00+00'",
                    "to_val": f"'{n_year}-{n_month:02d}-01 00:00:00+00'",
                }
            )

    async with AsyncSessionLocal() as db:
        if db.bind and db.bind.dialect.name != "postgresql":
            logger.info(
                "PARTITION_MANAGER | skip | dialect is not PostgreSQL"
            )
            return

        if not await _market_data_ready(db):
            return

        logger.info(
            "PARTITION_MANAGER | stage=start | ensuring %s partitions",
            len(partitions_to_create),
        )

        for p in partitions_to_create:
            # Check if partition exists
            res = await db.execute(
                text(
                    "SELECT 1 FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'market_data' AND c.relname = :name"
                ),
                {"name": p["name"]},
            )
            exists = res.scalar() is not None

            if not exists:
                logger.info("PARTITION_MANAGER | create | %s", p["name"])
                create_stmt = (
                    f"CREATE TABLE IF NOT EXISTS market_data.{p['name']} "
                    f"PARTITION OF market_data.{p['parent']} "
                    f"FOR VALUES FROM ({p['from_val']}) TO ({p['to_val']})"
                )
                try:
                    await db.execute(text(create_stmt))
                    await db.commit()
                    logger.info("PARTITION_MANAGER | created | %s", p["name"])
                except Exception as e:
                    # Roll back failed DDL attempt so later partitions can proceed
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    logger.error(
                        "PARTITION_MANAGER | failed | %s | %s", p["name"], e
                    )
                    # Do not crash startup for a single partition race; parent
                    # schema is present so app can still serve.
                    continue
            else:
                logger.debug("PARTITION_MANAGER | exists | %s", p["name"])

        logger.info("PARTITION_MANAGER | stage=complete")
