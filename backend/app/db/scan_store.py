import logging
import time
from typing import Any

import orjson
from sqlalchemy import text

from .session import AsyncSessionLocal

logger = logging.getLogger("scan.db")


async def _dialect_name(db) -> str:
    """Return the SQL dialect for the current async session bind."""
    try:
        conn = await db.connection()
        return conn.dialect.name
    except Exception:
        bind = getattr(db, "bind", None) or getattr(db, "get_bind", lambda: None)()
        if bind is not None:
            return getattr(bind.dialect, "name", "postgresql") or "postgresql"
        return "postgresql"


async def _ensure_sqlite_scan_results(db) -> None:
    """Create the SQLite-compatible scan_results singleton table if missing."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


async def save_latest_scan(payload: dict) -> None:
    """Save new scan result replacing the old one atomically.

    Postgres uses ``market_data.scan_results`` (JSONB).
    SQLite uses a local ``scan_results`` table (TEXT JSON) so tests and local
    runs do not depend on PostgreSQL schemas.
    """
    jsonb_payload = orjson.dumps(payload).decode("utf-8")

    start_time = time.monotonic()
    async with AsyncSessionLocal() as db:
        dialect = await _dialect_name(db)
        if dialect == "sqlite":
            await _ensure_sqlite_scan_results(db)
            await db.execute(
                text(
                    """
                    INSERT INTO scan_results (id, payload, computed_at)
                    VALUES (1, :payload, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        payload = excluded.payload,
                        computed_at = excluded.computed_at
                    """
                ),
                {"payload": jsonb_payload},
            )
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO market_data.scan_results (id, payload, computed_at)
                    VALUES (1, CAST(:payload AS JSONB), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        computed_at = EXCLUDED.computed_at
                    """
                ),
                {"payload": jsonb_payload},
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
        dialect = await _dialect_name(db)
        if dialect == "sqlite":
            await _ensure_sqlite_scan_results(db)
            res = await db.execute(
                text("SELECT computed_at FROM scan_results WHERE id = 1")
            )
        else:
            res = await db.execute(
                text("SELECT computed_at FROM market_data.scan_results WHERE id = 1")
            )
        row = res.scalar()
    if row:
        return row.isoformat() if hasattr(row, "isoformat") else str(row)
    return None


async def load_latest_scan() -> dict | None:
    """Return the latest scan payload or None if not yet run."""
    async with AsyncSessionLocal() as db:
        dialect = await _dialect_name(db)
        if dialect == "sqlite":
            await _ensure_sqlite_scan_results(db)
            res = await db.execute(
                text("SELECT payload, computed_at FROM scan_results WHERE id = 1")
            )
        else:
            res = await db.execute(
                text(
                    "SELECT payload, computed_at FROM market_data.scan_results WHERE id = 1"
                )
            )
        row = res.mappings().first()

    if row:
        data = row["payload"]
        if isinstance(data, str):
            data = orjson.loads(data)
        elif not isinstance(data, dict):
            # Some drivers return memoryview/bytes
            data = orjson.loads(bytes(data) if not isinstance(data, (bytes, bytearray)) else data)

        computed_at_val = row["computed_at"]
        saved_at = (
            computed_at_val.isoformat()
            if hasattr(computed_at_val, "isoformat")
            else str(computed_at_val)
        )

        data["scanned_at"] = saved_at
        data["last_scan_completed_at"] = saved_at
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

    logger.info("PG LOAD | status=empty | No scan saved yet")
    return None
