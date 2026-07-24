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


def _as_symbol_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(s) for s in value if s]
    return []


def _normalize_scan_payload(payload: dict) -> dict:
    """Ensure ScreenerResponse dumps expose an ``items`` list for logging / legacy.

    Historical scan_store code expected ``payload["items"]`` with ``matched`` /
    ``signal``. ScreenerResponse.model_dump() uses ``all_analyzed_stocks``,
    ``matches``, ``buy_candidate_symbols``, etc. — so counts always read as 0.
    """
    if not isinstance(payload, dict):
        return payload

    buy = set(_as_symbol_list(payload.get("buy_candidate_symbols")))
    watch = set(_as_symbol_list(payload.get("watch_candidate_symbols")))
    shortlisted = set(_as_symbol_list(payload.get("shortlisted_symbols")))

    existing_items = payload.get("items")
    if isinstance(existing_items, list) and existing_items:
        # Already has items (tests / older writers) — still refresh signal tags
        normalized_items = []
        for row in existing_items:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "")
            signal = row.get("signal")
            if sym in buy:
                signal = "BUY"
            elif sym in watch:
                signal = "WATCH"
            elif not signal:
                signal = "REJECT"
            matched = bool(row.get("matched")) or sym in shortlisted or sym in buy or sym in watch
            normalized_items.append({**row, "signal": signal, "matched": matched})
        out = dict(payload)
        out["items"] = normalized_items
        return out

    stocks = payload.get("all_analyzed_stocks") or payload.get("matches") or []
    items: list[dict] = []
    seen: set[str] = set()

    def _append_stock(row: dict) -> None:
        sym = str(row.get("symbol") or "")
        if not sym or sym in seen:
            return
        seen.add(sym)
        if sym in buy:
            signal = "BUY"
            matched = True
        elif sym in watch:
            signal = "WATCH"
            matched = True
        elif sym in shortlisted or row.get("matched"):
            signal = str(row.get("technical_signal") or "WATCH").upper()
            matched = True
        else:
            signal = str(row.get("technical_signal") or "REJECT").upper()
            matched = False
        items.append({
            **row,
            "symbol": sym,
            "matched": matched,
            "signal": signal,
        })

    for row in stocks:
        if isinstance(row, dict):
            _append_stock(row)

    # Ensure BUY/WATCH symbols appear even if not in all_analyzed_stocks dump
    analysis = payload.get("analysis") or {}
    analysis_items = analysis.get("items") if isinstance(analysis, dict) else None
    if isinstance(analysis_items, list):
        for aitem in analysis_items:
            if not isinstance(aitem, dict):
                continue
            sym = str(aitem.get("symbol") or "")
            if not sym or sym in seen:
                continue
            action = str((aitem.get("recommendation") or {}).get("action") or "").upper()
            if action not in {"BUY", "WATCH"}:
                if sym in buy:
                    action = "BUY"
                elif sym in watch:
                    action = "WATCH"
                else:
                    action = "REJECT"
            score = (aitem.get("recommendation") or {}).get("score")
            items.append({
                "symbol": sym,
                "matched": action in {"BUY", "WATCH"} or sym in shortlisted,
                "signal": action,
                "screener_score": score,
                "technical_signal": action,
            })
            seen.add(sym)

    for sym in list(buy) + list(watch) + list(shortlisted):
        if sym in seen:
            continue
        signal = "BUY" if sym in buy else ("WATCH" if sym in watch else "WATCH")
        items.append({
            "symbol": sym,
            "matched": True,
            "signal": signal,
            "technical_signal": signal,
        })
        seen.add(sym)

    out = dict(payload)
    out["items"] = items
    return out


def _count_scan_items(payload: dict) -> tuple[int, int, int, int]:
    """Return (total, shortlisted, buy, watch) for logging."""
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []
    buy_set = set(_as_symbol_list(payload.get("buy_candidate_symbols")))
    watch_set = set(_as_symbol_list(payload.get("watch_candidate_symbols")))
    shortlisted_set = set(_as_symbol_list(payload.get("shortlisted_symbols")))

    if buy_set or watch_set or shortlisted_set:
        buy_count = len(buy_set)
        watch_count = len(watch_set)
        shortlisted_count = len(shortlisted_set) or (buy_count + watch_count)
        total = len(items) if items else int(payload.get("scanned_symbols") or 0)
        return total, shortlisted_count, buy_count, watch_count

    shortlisted = [s for s in items if isinstance(s, dict) and s.get("matched") is True]
    buy_count = len([
        s for s in shortlisted
        if str(s.get("signal") or "").upper() in {"BULLISH", "BUY"}
    ])
    watch_count = len([
        s for s in shortlisted
        if str(s.get("signal") or "").upper() in {"NEUTRAL", "WATCH"}
    ])
    return len(items), len(shortlisted), buy_count, watch_count


async def save_latest_scan(payload: dict) -> None:
    """Save new scan result replacing the old one atomically.

    Postgres uses ``market_data.scan_results`` (JSONB).
    SQLite uses a local ``scan_results`` table (TEXT JSON) so tests and local
    runs do not depend on PostgreSQL schemas.
    """
    normalized = _normalize_scan_payload(payload if isinstance(payload, dict) else {})
    jsonb_payload = orjson.dumps(normalized).decode("utf-8")

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

    total, shortlisted_count, buy_count, watch_count = _count_scan_items(normalized)
    rejected = max(total - shortlisted_count, 0)
    size_kb = round(len(jsonb_payload) / 1024, 1)

    logger.info("%s", "=" * 60)
    logger.info("PG SAVE SUCCESS")
    logger.info("  Duration     : %.2f ms", duration_ms)
    logger.info("  Size         : %s KB", size_kb)
    logger.info("  Total stored : %s stocks", total)
    logger.info("  Shortlisted  : %s  (BUY=%s | WATCH=%s)", shortlisted_count, buy_count, watch_count)
    logger.info("  Rejected     : %s", rejected)
    logger.info(
        "  Lists        : shortlisted=%s buy=%s watch=%s analysis_items=%s",
        len(_as_symbol_list(normalized.get("shortlisted_symbols"))),
        len(_as_symbol_list(normalized.get("buy_candidate_symbols"))),
        len(_as_symbol_list(normalized.get("watch_candidate_symbols"))),
        len(((normalized.get("analysis") or {}) if isinstance(normalized.get("analysis"), dict) else {}).get("items") or []),
    )
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

        data = _normalize_scan_payload(data)

        computed_at_val = row["computed_at"]
        saved_at = (
            computed_at_val.isoformat()
            if hasattr(computed_at_val, "isoformat")
            else str(computed_at_val)
        )

        data["scanned_at"] = saved_at
        data["last_scan_completed_at"] = saved_at
        total, shortlisted_count, buy_count, watch_count = _count_scan_items(data)

        logger.info("%s", "=" * 60)
        logger.info("PG LOAD SUCCESS")
        logger.info("  Saved at     : %s", saved_at)
        logger.info("  Total loaded : %s stocks", total)
        logger.info("  Shortlisted  : %s  (BUY=%s | WATCH=%s)", shortlisted_count, buy_count, watch_count)
        logger.info("%s", "=" * 60)
        return data

    logger.info("PG LOAD | status=empty | No scan saved yet")
    return None
