import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from ..db.session import AsyncSessionLocal

logger = logging.getLogger("app.partition_manager")

async def verify_and_create_partitions():
    """
    Called at application startup.
    Verifies that the current and next partitions exist for all resolutions.
    Auto-creates them if they do not exist.
    """
    now = datetime.now(timezone.utc)
    # We want to check this month/year and the next month/year
    
    # 1D is partitioned YEARLY
    current_year = now.year
    
    partitions_to_create = []
    
    for y in range(current_year - 3, current_year + 2):
        partitions_to_create.append({
            "parent": "candles_1d",
            "name": f"candles_1d_y{y}",
            "from_val": f"'{y}-01-01 00:00:00+00'",
            "to_val": f"'{y + 1}-01-01 00:00:00+00'"
        })
    
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
            
            partitions_to_create.append({
                "parent": f"candles_{res}",
                "name": f"candles_{res}_y{t_year}_m{t_month:02d}",
                "from_val": f"'{t_year}-{t_month:02d}-01 00:00:00+00'",
                "to_val": f"'{n_year}-{n_month:02d}-01 00:00:00+00'"
            })
        
    async with AsyncSessionLocal() as db:
        if db.bind and db.bind.dialect.name != "postgresql":
            logger.info("Skipping partition creation since dialect is not PostgreSQL.")
            return
        
        for p in partitions_to_create:
            # Check if partition exists
            res = await db.execute(
                text("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'market_data' AND c.relname = :name"),
                {"name": p["name"]}
            )
            exists = res.scalar() is not None
            
            if not exists:
                logger.info(f"Auto-creating missing partition: {p['name']}")
                create_stmt = f"CREATE TABLE IF NOT EXISTS market_data.{p['name']} PARTITION OF market_data.{p['parent']} FOR VALUES FROM ({p['from_val']}) TO ({p['to_val']})"
                try:
                    await db.execute(text(create_stmt))
                    await db.commit()
                    logger.info(f"Successfully created partition: {p['name']}")
                except Exception as e:
                    logger.error(f"Failed to create partition {p['name']}: {e}")
                    raise
            else:
                logger.debug(f"Partition {p['name']} already exists.")
