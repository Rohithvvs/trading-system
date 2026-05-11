import sqlite3
import os
from datetime import date, timedelta, datetime, timezone
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "candle_cache.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create required tables if they don't exist and record schema version."""
    with get_connection() as conn:
        # Schema versioning table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        # Main candles table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                symbol     TEXT NOT NULL,
                date       TEXT NOT NULL,
                open       REAL,
                high       REAL,
                low        REAL,
                close      REAL,
                volume     INTEGER,
                fetched_at TEXT,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        # Safe migration for existing DBs that don't have fetched_at yet
        try:
            conn.execute("ALTER TABLE candles ADD COLUMN fetched_at TEXT")
        except Exception:
            # Column likely already exists; ignore
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON candles(symbol)")

        # LTP cache for quick quote persistence (compat with older ohlcv_store)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ltp_cache (
                symbol TEXT PRIMARY KEY,
                ltp REAL,
                updated_at TEXT
            )
            """
        )

        # Ensure a schema_version row exists (v1)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES(1)")
        conn.commit()


def get_last_stored_date(symbol: str) -> str | None:
    """Return the most recent date string stored for a symbol, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM candles WHERE symbol = ?", (symbol,)
        ).fetchone()
    return row[0] if row and row[0] is not None else None


def get_last_stored_timestamp(symbol: str) -> str | None:
    """Return the most recent fetched_at timestamp stored for a symbol, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) FROM candles WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    return row[0] if row and row[0] is not None else None


def store_candles(symbol: str, df: pd.DataFrame):
    """
    Insert or replace candles for a symbol.
    df must have columns: date (YYYY-MM-DD string), open, high, low, close, volume
    """
    if df is None or df.empty:
        return

    from datetime import timezone as _tz
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows = [
        (
            symbol,
            str(row["date"]),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            int(row["volume"]),
            fetched_at,
        )
        for _, row in df.iterrows()
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO candles
                (symbol, date, open, high, low, close, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def load_candles(symbol: str, from_date: str | None = None):
    """Load cached candles for a symbol.

    - If `from_date` is None: returns a pandas.DataFrame with all rows (same as previous API).
    - If `from_date` is provided: returns a list[dict] compatible with older `ohlcv_store.load_candles`.
    """
    with get_connection() as conn:
        if from_date:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume FROM candles WHERE symbol = ? AND date >= ? ORDER BY date ASC",
                conn,
                params=(symbol, from_date),
            )
            return [
                {
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": int(row["volume"]),
                }
                for _, row in df.iterrows()
            ]
        else:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume FROM candles WHERE symbol = ? ORDER BY date ASC",
                conn,
                params=(symbol,),
            )
            return df


def save_candles(symbol: str, candles: list[dict]):
    """Compatibility wrapper: accept list[dict] rows and persist them into the candles table."""
    if not candles:
        return
    try:
        df = pd.DataFrame(candles)
        # Ensure 'date' column exists and is string-like
        if "date" not in df.columns:
            return
        store_candles(symbol, df)
    except Exception:
        # Best-effort: if conversion fails, skip persistence
        return


def get_candle_count(symbol: str) -> int:
    """Return number of candle rows stored for a symbol."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def update_ltp(symbol: str, ltp: float) -> None:
    """Insert or replace LTP for a symbol into `ltp_cache`."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ltp_cache (symbol, ltp, updated_at) VALUES (?, ?, datetime('now'))",
            (symbol, float(ltp)),
        )
        conn.commit()


def get_ltp(symbol: str) -> float | None:
    """Return the cached LTP for `symbol` or None if missing."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ltp FROM ltp_cache WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return None


def get_last_trading_day() -> str:
    """
    Returns today's date if it's a weekday (Mon-Fri),
    else returns the most recent Friday.
    This is a simple check — does not account for NSE holidays.
    """
    today = date.today()
    weekday = today.weekday()  # Monday=0, Sunday=6
    if weekday == 5:  # Saturday
        return str(today - timedelta(days=1))
    elif weekday == 6:  # Sunday
        return str(today - timedelta(days=2))
    else:
        return str(today)


def get_latest_completed_market_session_date(reference_date: date | None = None) -> str:
    """
    Return the latest completed weekday session using the current lightweight
    calendar rule. TODO: replace with an exchange calendar so weekday market
    holidays are handled without a provider refresh.
    """
    today = reference_date or date.today()
    weekday = today.weekday()
    if weekday == 5:
        return str(today - timedelta(days=1))
    if weekday == 6:
        return str(today - timedelta(days=2))
    return str(today)


def has_completed_daily_session(symbol: str, reference_date: date | None = None) -> bool:
    """
    Return True when cached daily candles already cover the latest completed
    weekday session. This keeps weekend/same-session reruns on the local cache
    even when the fetch timestamp itself is old.
    """
    latest_cached = get_last_stored_date(symbol)
    if latest_cached is None:
        return False
    latest_completed = get_latest_completed_market_session_date(reference_date)
    return latest_cached >= latest_completed


def is_cache_fresh(symbol: str, max_age_minutes: int = 30) -> bool:
    """
    Returns True only if the cache was fetched within the last
    `max_age_minutes`. Default: 30 minutes.
    This function is backwards-compatible: callers that pass only `symbol`
    will use the default 30-minute window.
    """
    return is_cache_fresh_with_age(symbol, max_age_minutes)


def is_cache_fresh_with_age(symbol: str, max_age_minutes: int = 30) -> bool:
    """
    Time-based freshness check. Returns True if the most recent `fetched_at`
    timestamp for `symbol` is within `max_age_minutes` of now (UTC).
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(fetched_at) FROM candles WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        if not row or not row[0]:
            return False
        last_fetched = datetime.fromisoformat(row[0])
        if last_fetched.tzinfo is None:
            last_fetched = last_fetched.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - last_fetched).total_seconds() / 60
        return age_minutes < max_age_minutes
    except Exception:
        return False


def get_all_cached_symbols() -> list[str]:
    """Return list of all symbols that have at least one cached candle."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM candles"
        ).fetchall()
    return [row[0] for row in rows]
