import json
import sqlite3
from pathlib import Path
import logging


DB_PATH = Path(__file__).parent / "scan_result.db"

logger = logging.getLogger("scan.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS latest_scan (
            id INTEGER PRIMARY KEY,
            payload TEXT NOT NULL,
            saved_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


def save_latest_scan(payload: dict) -> None:
    """Delete old result and save new one. Always keeps only 1 row."""
    conn = _connect()
    conn.execute("DELETE FROM latest_scan")
    conn.execute(
        "INSERT INTO latest_scan (payload) VALUES (?)",
        (json.dumps(payload),),
    )
    conn.commit()
    conn.close()

    # Count total stocks stored
    items = payload.get("items", [])
    shortlisted = [s for s in items if s.get("matched") is True]
    rejected = [s for s in items if s.get("matched") is False]
    buy_count = len([s for s in shortlisted if s.get("signal") in ("bullish", "BUY")])
    watch_count = len([s for s in shortlisted if s.get("signal") in ("neutral", "WATCH")])
    size_kb = round(len(json.dumps(payload)) / 1024, 1)

    logger.info("%s", "=" * 60)
    logger.info("DB SAVE SUCCESS")
    logger.info("  Path         : %s", DB_PATH)
    logger.info("  Size         : %s KB", size_kb)
    logger.info("  Total stored : %s stocks", len(items))
    logger.info("  Shortlisted  : %s  (BUY=%s | WATCH=%s)", len(shortlisted), buy_count, watch_count)
    logger.info("  Rejected     : %s", len(rejected))
    logger.info("%s", "=" * 60)


def load_latest_scan() -> dict | None:
    """Return the latest scan payload or None if not yet run."""
    conn = _connect()
    row = conn.execute(
        "SELECT payload, saved_at FROM latest_scan ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        payload_str, saved_at = row[0], row[1]
        data = json.loads(payload_str)
        items = data.get("items", [])
        shortlisted = [s for s in items if s.get("matched") is True]
        rejected = [s for s in items if s.get("matched") is False]

        logger.info("%s", "=" * 60)
        logger.info("DB LOAD SUCCESS")
        logger.info("  Saved at     : %s", saved_at)
        logger.info("  Total loaded : %s stocks", len(items))
        logger.info("  Shortlisted  : %s", len(shortlisted))
        logger.info("  Rejected     : %s", len(rejected))
        logger.info("%s", "=" * 60)
        return data
    else:
        logger.info("DB LOAD | status=empty | No scan saved yet — run scanner first")
        return None
