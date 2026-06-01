import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import text
from ..db.session import AsyncSessionLocal

logger = logging.getLogger("candle_store")

async def get_last_stored_date(symbol: str, resolution: str = "1D") -> str | None:
    """Return the most recent date string stored for a symbol, or None."""
    async with AsyncSessionLocal() as db:
        stmt = text("SELECT MAX(date) FROM market_data.candles WHERE symbol = :s AND resolution = :r")
        res = await db.execute(stmt, {"s": symbol, "r": resolution})
        row = res.scalar()
        if not row:
            return None
        if isinstance(row, str):
            return row.split(' ')[0] # Extract just the date part YYYY-MM-DD
        return row.strftime("%Y-%m-%d")
    return None

async def get_last_stored_timestamp(symbol: str, resolution: str = "1D") -> str | None:
    """Return the most recent fetched_at timestamp stored for a symbol, or None."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT MAX(fetched_at) FROM market_data.candles WHERE symbol = :s AND resolution = :r"),
            {"s": symbol, "r": resolution}
        )
        row = res.scalar()
    if row:
        return row.isoformat()
    return None

async def store_candles(symbol: str, df: pd.DataFrame, resolution: str = "1D"):
    """
    Insert or replace candles for a symbol.
    df must have columns: date (YYYY-MM-DD string), open, high, low, close, volume
    """
    if df is None or df.empty:
        return

    fetched_at = datetime.now(timezone.utc)
    
    # Convert df to list of dicts for executemany
    rows = []
    for _, row in df.iterrows():
        # Ensure date is parsed to handle datetime correctly for Postgres TIMESTAMPTZ
        # If it's just '2025-01-01', it will become '2025-01-01 00:00:00+00:00'
        # if it's already a datetime, just pass it.
        dt_val = row["date"]
        if isinstance(dt_val, str):
            dt_val = datetime.fromisoformat(dt_val).replace(tzinfo=timezone.utc)
        
        rows.append({
            "s": symbol,
            "r": resolution,
            "d": dt_val,
            "o": float(row["open"]),
            "h": float(row["high"]),
            "l": float(row["low"]),
            "c": float(row["close"]),
            "v": int(row["volume"]),
            "f": fetched_at
        })

    async with AsyncSessionLocal() as db:
        # We use INSERT ... ON CONFLICT DO UPDATE for idempotency.
        # The primary key is (symbol, resolution, date)
        query = text(f"""
            INSERT INTO market_data.candles
                (symbol, resolution, date, open, high, low, close, volume, fetched_at)
            VALUES 
                (:s, :r, :d, :o, :h, :l, :c, :v, :f)
            ON CONFLICT (symbol, resolution, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                fetched_at = EXCLUDED.fetched_at
        """)
        await db.execute(query, rows)
        await db.commit()

async def load_candles(symbol: str, from_date: str | datetime | None = None, resolution: str = "1D"):
    """Load cached candles for a symbol. Returns pandas DataFrame or list[dict]."""
    async with AsyncSessionLocal() as db:
        if from_date:
            if isinstance(from_date, str):
                from_date = datetime.fromisoformat(from_date)
            res = await db.execute(
                text("SELECT date, open, high, low, close, volume FROM market_data.candles WHERE symbol = :s AND resolution = :r AND date >= :fd ORDER BY date ASC"),
                {"s": symbol, "r": resolution, "fd": from_date}
            )
            rows = res.mappings().all()
            return [
                {
                    "date": row["date"].split(' ')[0] if isinstance(row["date"], str) else row["date"].strftime("%Y-%m-%d"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"])
                }
                for row in rows
            ]
        else:
            res = await db.execute(
                text("SELECT date, open, high, low, close, volume FROM market_data.candles WHERE symbol = :s AND resolution = :r ORDER BY date ASC"),
                {"s": symbol, "r": resolution}
            )
            rows = res.mappings().all()
            data = [
                {
                    "date": row["date"].split(' ')[0] if isinstance(row["date"], str) else row["date"].strftime("%Y-%m-%d"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                }
                for row in rows
            ]
            return pd.DataFrame(data)

async def save_candles(symbol: str, candles: list[dict], resolution: str = "1D"):
    if not candles:
        return True
    try:
        df = pd.DataFrame(candles)
        if "date" not in df.columns:
            return
        await store_candles(symbol, df, resolution)
    except Exception as e:
        logger.error(f"Failed to save candles: {e}")
        return

async def get_candle_count(symbol: str, resolution: str = "1D") -> int:
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT COUNT(*) FROM market_data.candles WHERE symbol = :s AND resolution = :r"),
            {"s": symbol, "r": resolution}
        )
        return int(res.scalar() or 0)

async def update_ltp(symbol: str, ltp: float) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f"""
                INSERT INTO market_data.ltp_cache (symbol, ltp, updated_at)
                VALUES (:s, :ltp, CURRENT_TIMESTAMP)
                ON CONFLICT (symbol) DO UPDATE SET ltp = EXCLUDED.ltp, updated_at = EXCLUDED.updated_at
            """),
            {"s": symbol, "ltp": float(ltp)}
        )
        await db.commit()

async def get_ltp(symbol: str) -> float | None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT ltp FROM market_data.ltp_cache WHERE symbol = :s"),
            {"s": symbol}
        )
        row = res.scalar()
        if row is not None:
            return float(row)
        return None

def get_last_trading_day() -> str:
    today = date.today()
    weekday = today.weekday()
    if weekday == 5:
        return str(today - timedelta(days=1))
    elif weekday == 6:
        return str(today - timedelta(days=2))
    else:
        return str(today)

def get_latest_completed_market_session_date(reference_date: date | None = None) -> str:
    today = reference_date or date.today()
    weekday = today.weekday()
    if weekday == 5:
        return str(today - timedelta(days=1))
    if weekday == 6:
        return str(today - timedelta(days=2))
    return str(today)

async def has_completed_daily_session(symbol: str, reference_date: date | None = None) -> bool:
    latest_cached = await get_last_stored_date(symbol, "1D")
    if latest_cached is None:
        return False
    latest_completed = get_latest_completed_market_session_date(reference_date)
    return latest_cached >= latest_completed

async def is_cache_fresh(symbol: str, max_age_minutes: int = 30) -> bool:
    return await is_cache_fresh_with_age(symbol, max_age_minutes)

async def is_cache_fresh_with_age(symbol: str, max_age_minutes: int = 30) -> bool:
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                text("SELECT MAX(fetched_at) FROM market_data.candles WHERE symbol = :s"),
                {"s": symbol}
            )
            row = res.scalar()
            if not row:
                return False
            
            last_fetched = row
            if last_fetched.tzinfo is None:
                last_fetched = last_fetched.replace(tzinfo=timezone.utc)
            
            age_minutes = (datetime.now(timezone.utc) - last_fetched).total_seconds() / 60
            return age_minutes < max_age_minutes
    except Exception:
        return False

async def get_all_cached_symbols() -> list[str]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT DISTINCT symbol FROM market_data.candles"))
        return [row[0] for row in res.fetchall()]

async def load_all_cached_candles(symbols: list[str], resolution: str = "1D") -> dict[str, pd.DataFrame]:
    if not symbols:
        return {}
    
    # We use a batched IN clause
    async with AsyncSessionLocal() as db:
        # PostgreSQL syntax for IN clause with array or unnest
        # For safety and to avoid massive prepared statements, we can use = ANY(:syms)
        res = await db.execute(
            text(f"""
                SELECT symbol, date, open, high, low, close, volume 
                FROM market_data.candles 
                WHERE symbol = ANY(:syms) AND resolution = :r 
                ORDER BY date ASC
            """),
            {"syms": symbols, "r": resolution}
        )
        rows = res.mappings().all()

    data = {symbol: [] for symbol in symbols}
    for row in rows:
        data[row["symbol"]].append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        })

    return {
        symbol: pd.DataFrame(r) if r else pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        for symbol, r in data.items()
    }
