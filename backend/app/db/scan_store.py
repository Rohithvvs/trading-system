import orjson
import json
import logging
from typing import Any
from sqlalchemy import text
from .session import AsyncSessionLocal

logger = logging.getLogger("scan.db")

import time

async def save_latest_scan(payload: dict) -> None:
    """Save new scan result replacing the old one atomically."""
    # Convert payload to json string/bytes using orjson
    jsonb_payload = orjson.dumps(payload).decode("utf-8")
    
    start_time = time.monotonic()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO market_data.scan_results (id, payload, computed_at)
                VALUES (1, CAST(:payload AS JSONB), NOW())
                ON CONFLICT (id) DO UPDATE SET 
                    payload = EXCLUDED.payload,
                    computed_at = EXCLUDED.computed_at
            """),
            {"payload": jsonb_payload}
        )
        await db.commit()
    duration_ms = (time.monotonic() - start_time) * 1000

    # Count total stocks stored
    items = payload.get("items", [])
    shortlisted = [s for s in items if s.get("matched") is True]
    rejected = [s for s in items if s.get("matched") is False]
    buy_count = len([s for s in shortlisted if s.get("signal") in ("bullish", "BUY")])
    watch_count = len([s for s in shortlisted if s.get("signal") in ("neutral", "WATCH")])
    size_kb = round(len(jsonb_payload) / 1024, 1)

    logger.info("%s", "=" * 60)
    logger.info("PG SAVE SUCCESS")
    logger.info("  Duration     : %.2f ms", duration_ms)
    logger.info("  Size         : %s KB", size_kb)
    logger.info("  Total stored : %s stocks", len(items))
    logger.info("  Shortlisted  : %s  (BUY=%s | WATCH=%s)", len(shortlisted), buy_count, watch_count)
    logger.info("  Rejected     : %s", len(rejected))
    logger.info("%s", "=" * 60)

async def get_last_scan_time() -> str | None:
    """Return only the timestamp of the latest scan, or None if no scan exists."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT computed_at FROM market_data.scan_results WHERE id = 1")
        )
        row = res.scalar()
    if row:
        # handle ISO format if row is a string or datetime
        return row.isoformat() if hasattr(row, 'isoformat') else str(row)
    return None

async def load_latest_scan() -> dict | None:
    """Return the latest scan payload or None if not yet run."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT payload, computed_at FROM market_data.scan_results WHERE id = 1")
        )
        row = res.mappings().first()

    if row:
        # payload is likely already parsed as dict by asyncpg due to jsonb, but if it's string, parse it.
        data = row["payload"]
        if isinstance(data, str):
            data = orjson.loads(data)
        
        computed_at_val = row["computed_at"]
        saved_at = computed_at_val.isoformat() if hasattr(computed_at_val, 'isoformat') else str(computed_at_val)
        
        # Inject the saved_at timestamp into the payload for the frontend
        data["scanned_at"] = saved_at
        items = data.get("items", [])
        shortlisted = [s for s in items if s.get("matched") is True]
        rejected = [s for s in items if s.get("matched") is False]

        logger.info("%s", "=" * 60)
        logger.info("PG LOAD SUCCESS")
        logger.info("  Saved at     : %s", saved_at)
        logger.info("  Total loaded : %s stocks", len(items))
        logger.info("  Shortlisted  : %s", len(shortlisted))
        logger.info("  Rejected     : %s", len(rejected))
        logger.info("%s", "=" * 60)
        return data
    else:
        logger.info("PG LOAD | status=empty | No scan saved yet")
        return None
