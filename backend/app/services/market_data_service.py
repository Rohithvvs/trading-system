import pandas as pd
from datetime import datetime, timezone
import time
import random
import asyncio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from ..db.session import engine, AsyncSessionLocal
from ..models.market_data import HistoricalCandle
from ..utils import get_logger, safe_int

logger = get_logger("app.market_data")

class MarketDataService:
    async def get_latest_candle_time(self, symbol: str, timeframe: str) -> datetime | None:
        async with AsyncSessionLocal() as db:
            stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
            result = (await db.execute(stmt)).scalar_one_or_none()
            return result

    async def get_candle_count(self, symbol: str, timeframe: str) -> int:
        async with AsyncSessionLocal() as db:
            stmt = select(func.count(HistoricalCandle.timestamp)).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            )
            result = (await db.execute(stmt)).scalar()
            return result or 0

    async def validate_candle_continuity(self, symbol: str, timeframe: str, expected_count: int):
        from .cache_state import CacheState, CacheHealthContext
        count = await self.get_candle_count(symbol, timeframe)
        latest = await self.get_latest_candle_time(symbol, timeframe)
        
        if count == 0 or not latest:
            return CacheHealthContext(
                symbol=symbol, timeframe=timeframe, cached_rows=0, required_rows=expected_count,
                continuity_gap_count=0, cache_state=CacheState.EMPTY, is_valid_for_indicators=False
            )
            
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        latest_no_tz = latest.replace(tzinfo=None) if latest.tzinfo else latest
        staleness_minutes = (now - latest_no_tz).total_seconds() / 60.0
        
        is_fresh = False
        if timeframe == '1m' and staleness_minutes <= 5: is_fresh = True
        elif timeframe == '5m' and staleness_minutes <= 15: is_fresh = True
        elif timeframe == '15m' and staleness_minutes <= 30: is_fresh = True
        elif timeframe == '1D' and staleness_minutes <= 2880: is_fresh = True
            
        is_complete = count >= expected_count
        # Expensive gap/duplicate scans only when history is complete enough to be usable.
        # Incomplete caches are already invalid for indicators — skip full-table reads.
        gap_count = 0
        if is_complete:
            async with AsyncSessionLocal() as db:
                dup_stmt = select(HistoricalCandle.timestamp).where(
                    HistoricalCandle.symbol == symbol, HistoricalCandle.resolution == timeframe
                ).group_by(HistoricalCandle.timestamp).having(func.count(HistoricalCandle.timestamp) > 1)
                duplicates = (await db.execute(dup_stmt)).fetchall()

                if duplicates:
                    logger.error("corrupted_cache_duplicates", extra={"symbol": symbol, "resolution": timeframe})
                    return CacheHealthContext(
                        symbol=symbol, timeframe=timeframe, cached_rows=count, required_rows=expected_count,
                        continuity_gap_count=len(duplicates), cache_state=CacheState.CORRUPTED, is_valid_for_indicators=False
                    )

            # Sample-based gap check: only inspect index spacing, still one load, but only for complete caches.
            df = await self.load_full_history(symbol, timeframe)
            if df is not None and not df.empty:
                df = df.sort_index()
                diffs = df.index.to_series().diff()
                if timeframe == '1D':
                    gaps = diffs[diffs > pd.Timedelta(days=5)]
                    gap_count = len(gaps)
                    if gap_count > 0:
                        logger.error("corrupted_candle_ranges", extra={"symbol": symbol, "timeframe": timeframe, "gap_count": gap_count})

        if gap_count > 0:
            state = CacheState.CORRUPTED
            is_complete = False
        elif is_fresh and is_complete:
            state = CacheState.FRESH_COMPLETE
        elif is_fresh and not is_complete:
            state = CacheState.FRESH_INCOMPLETE
        elif not is_fresh and is_complete:
            state = CacheState.STALE_COMPLETE
        else:
            state = CacheState.STALE_INCOMPLETE
            
        if not is_complete and state != CacheState.CORRUPTED:
            logger.warning("insufficient_indicator_history", extra={
                "symbol": symbol, "timeframe": timeframe, "cached_rows": count, "required_rows": expected_count, "cache_state": state.value
            })
            
        return CacheHealthContext(
            symbol=symbol, timeframe=timeframe, cached_rows=count, required_rows=expected_count,
            continuity_gap_count=gap_count, cache_state=state, is_valid_for_indicators=is_complete
        )

    def check_stale_candles(self, symbol: str, timeframe: str, latest_timestamp: datetime | None):
        if not latest_timestamp:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if latest_timestamp.tzinfo is not None:
            latest_timestamp = latest_timestamp.replace(tzinfo=None)
            
        staleness_minutes = (now - latest_timestamp).total_seconds() / 60.0

        is_stale = False
        if timeframe == '1m' and staleness_minutes > 5:
            is_stale = True
        elif timeframe == '5m' and staleness_minutes > 15:
            is_stale = True
        elif timeframe == '15m' and staleness_minutes > 30:
            is_stale = True
        elif timeframe == '1D' and staleness_minutes > 2880:  # 2 days
            is_stale = True

        if is_stale:
            logger.warning(
                "stale_candle_detected",
                extra={
                    "symbol": symbol,
                    "resolution": timeframe,
                    "latest_timestamp": latest_timestamp.isoformat(),
                    "staleness_minutes": staleness_minutes,
                }
            )

    async def upsert_candles(self, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        """
        Upserts candles into the database efficiently in chunks.
        """
        if candles_df.empty:
            return

        # 1. Prepare Records
        records = []
        for timestamp, row in candles_df.iterrows():
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if getattr(timestamp, "tzinfo", None) is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                
            records.append({
                "symbol": symbol,
                "resolution": timeframe,
                "timestamp": timestamp,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": safe_int(row["volume"], symbol=symbol, field="volume")
            })

        # 3. PostgreSQL Batching: Chunk the batches to 900
        MAX_CHUNK_SIZE = 900
        for i in range(0, len(records), MAX_CHUNK_SIZE):
            chunk = records[i:i + MAX_CHUNK_SIZE]
            await self._upsert_chunk(symbol, timeframe, chunk)

    async def _upsert_chunk(self, symbol: str, timeframe: str, chunk_records: list[dict]):
        batch_size = len(chunk_records)
        new_timestamps = {r["timestamp"] for r in chunk_records}
        
        # 2. Retry Safety: Exponential Backoff & Jitter
        max_retries = 5
        base_delay = 0.5

        for attempt in range(1, max_retries + 1):
            start_time = time.monotonic()
            try:
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        # Observability: count duplicates
                        existing_stmt = select(HistoricalCandle.timestamp).where(
                            HistoricalCandle.symbol == symbol,
                            HistoricalCandle.resolution == timeframe,
                            HistoricalCandle.timestamp.in_(new_timestamps)
                        )
                        existing_ts = set((await db.scalars(existing_stmt)).all())
                        duplicate_count = len(existing_ts)
                        updated_count = duplicate_count
                        inserted_count = batch_size - duplicate_count

                        stmt = pg_insert(HistoricalCandle).values(chunk_records)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["symbol", "resolution", "timestamp"],
                            set_={
                                "open": stmt.excluded.open,
                                "high": stmt.excluded.high,
                                "low": stmt.excluded.low,
                                "close": stmt.excluded.close,
                                "volume": stmt.excluded.volume,
                                "updated_at": func.now(),
                            },
                        )
                        await db.execute(stmt)
                    
                    # Post-Commit Verification
                    # Post-Commit Verification must run outside the begin() block
                    async with AsyncSessionLocal() as verify_db:
                        verify_stmt = select(HistoricalCandle.timestamp).where(
                            HistoricalCandle.symbol == symbol,
                            HistoricalCandle.resolution == timeframe
                        ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
                        verified_ts = (await verify_db.execute(verify_stmt)).scalar_one_or_none()
                    if not verified_ts:
                        logger.error("silent_rollback_detected", extra={"symbol": symbol, "resolution": timeframe})
                    
                    elapsed_ms = (time.monotonic() - start_time) * 1000
                    
                    logger.info(
                        "pg_chunked_batch_executed",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "inserted_count": inserted_count,
                            "updated_count": updated_count,
                            "duplicate_count": duplicate_count,
                            "batch_size": batch_size,
                            "elapsed_ms": elapsed_ms,
                            "retry_attempt": attempt,
                        }
                    )
                    return
            except OperationalError as e:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                is_locked = "database is locked" in str(e) or "database table is locked" in str(e)
                
                if attempt < max_retries and is_locked:
                    sleep_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "database_lock_retry",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "lock_wait_ms": elapsed_ms,
                            "sleep_time_s": sleep_time
                        }
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.exception(
                        "candle_upsert_failed",
                        extra={
                            "symbol": symbol,
                            "resolution": timeframe,
                            "attempt": attempt,
                            "elapsed_ms": elapsed_ms,
                            "batch_size": batch_size,
                            "error": str(e)
                        }
                    )
                    logger.warning("database_rollback", extra={"symbol": symbol, "resolution": timeframe})
                    raise e
            except Exception as e:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.error(
                    "candle_upsert_failed",
                    extra={
                        "symbol": symbol,
                        "resolution": timeframe,
                        "attempt": attempt,
                        "elapsed_ms": elapsed_ms,
                        "error": str(e)
                    }
                )
                logger.warning("database_rollback", extra={"symbol": symbol, "resolution": timeframe})
                raise e

    async def load_full_history(self, symbol: str, timeframe: str) -> pd.DataFrame:
        query = select(
            HistoricalCandle.timestamp.label("date"),
            HistoricalCandle.open,
            HistoricalCandle.high,
            HistoricalCandle.low,
            HistoricalCandle.close,
            HistoricalCandle.volume
        ).where(
            HistoricalCandle.symbol == symbol,
            HistoricalCandle.resolution == timeframe
        ).order_by(HistoricalCandle.timestamp.asc())
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(query)
            df = pd.DataFrame(result.all(), columns=result.keys())
        if not df.empty:
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            # Cast Decimal columns to native Python types for Pandas arithmetic compatibility
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    df[col] = df[col].astype(float)
            if "volume" in df.columns:
                df["volume"] = df["volume"].apply(lambda v: safe_int(v, symbol=symbol, field="volume"))
        return df

    @staticmethod
    def symbol_lookup_variants(symbol: str) -> list[str]:
        """All plausible stored forms for a universe symbol (handles NSE: / -EQ drift)."""
        from ..utils.symbol import canonical_symbol

        raw = (symbol or "").strip()
        if not raw:
            return []
        can = canonical_symbol(raw)
        variants = [
            raw,
            raw.upper(),
            can,
            f"{can}-EQ",
            f"NSE:{can}-EQ",
            f"NSE:{can}",
        ]
        # Preserve order, drop empties/dupes
        seen: set[str] = set()
        out: list[str] = []
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out

    async def get_candle_meta_batch(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> dict[str, tuple[int, datetime | None, str | None]]:
        """
        Return {universe_symbol: (row_count, latest_timestamp, stored_db_symbol)} for a universe.

        Resolves symbol-format drift (RELIANCE vs RELIANCE-EQ vs NSE:RELIANCE-EQ) so a warm
        cache is not treated as a miss and forced through FYERS.  The 3rd element is the
        actual stored symbol name, which callers can use directly without a second meta query.
        """
        if not symbols:
            return {}

        meta: dict[str, tuple[int, datetime | None, str | None]] = {
            symbol: (0, None, None) for symbol in symbols
        }
        # Map every DB variant -> original universe symbol(s)
        variant_to_universe: dict[str, list[str]] = {}
        all_variants: list[str] = []
        for symbol in symbols:
            for v in self.symbol_lookup_variants(symbol):
                variant_to_universe.setdefault(v, []).append(symbol)
                all_variants.append(v)
        # unique variants for the query
        unique_variants = list(dict.fromkeys(all_variants))

        chunk_size = 300
        db_meta: dict[str, tuple[int, datetime | None]] = {}
        db_symbol_names: dict[str, str] = {}
        for i in range(0, len(unique_variants), chunk_size):
            chunk = unique_variants[i : i + chunk_size]
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(
                        HistoricalCandle.symbol,
                        func.count(HistoricalCandle.timestamp),
                        func.max(HistoricalCandle.timestamp),
                    )
                    .where(
                        HistoricalCandle.symbol.in_(chunk),
                        HistoricalCandle.resolution == timeframe,
                    )
                    .group_by(HistoricalCandle.symbol)
                )
                rows = (await db.execute(stmt)).all()
            for symbol, count, latest in rows:
                db_meta[symbol] = (int(count or 0), latest)
                db_symbol_names[symbol] = symbol

        # Prefer the variant with the richest history for each universe symbol
        for db_symbol, (count, latest) in db_meta.items():
            for universe_symbol in variant_to_universe.get(db_symbol, []):
                prev_count, _, _ = meta[universe_symbol]
                if count > prev_count:
                    meta[universe_symbol] = (count, latest, db_symbol)
        return meta

    async def resolve_stored_symbol_map(
        self,
        symbols: list[str],
        timeframe: str,
        meta_result: dict[str, tuple[int, datetime | None, str | None]] | None = None,
    ) -> dict[str, str]:
        """
        Map universe symbol -> best matching stored HistoricalCandle.symbol (if any).
        When meta_result from get_candle_meta_batch is provided, the stored symbol
        name is extracted from it directly — no additional query needed.
        """
        if not symbols:
            return {}
        if meta_result is not None:
            return {
                sym: db_sym
                for sym, (_, _, db_sym) in meta_result.items()
                if db_sym is not None
            }
        variant_to_universe: dict[str, list[str]] = {}
        unique_variants: list[str] = []
        for symbol in symbols:
            for v in self.symbol_lookup_variants(symbol):
                variant_to_universe.setdefault(v, []).append(symbol)
                if v not in variant_to_universe or True:
                    unique_variants.append(v)
        unique_variants = list(dict.fromkeys(unique_variants))

        best: dict[str, tuple[str, int]] = {}  # universe -> (db_symbol, count)
        chunk_size = 300
        for i in range(0, len(unique_variants), chunk_size):
            chunk = unique_variants[i : i + chunk_size]
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(
                        HistoricalCandle.symbol,
                        func.count(HistoricalCandle.timestamp),
                    )
                    .where(
                        HistoricalCandle.symbol.in_(chunk),
                        HistoricalCandle.resolution == timeframe,
                    )
                    .group_by(HistoricalCandle.symbol)
                )
                rows = (await db.execute(stmt)).all()
            for db_symbol, count in rows:
                for universe_symbol in variant_to_universe.get(db_symbol, []):
                    prev = best.get(universe_symbol)
                    if prev is None or int(count or 0) > prev[1]:
                        best[universe_symbol] = (db_symbol, int(count or 0))
        return {u: db_sym for u, (db_sym, _) in best.items()}

    async def load_histories_batch(
        self,
        symbols: list[str],
        timeframe: str,
        stored_symbol_map: dict[str, str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Load full daily histories for many symbols with chunked IN queries.
        Avoids per-symbol session open/close during large scans.

        If stored_symbol_map is provided, loads by DB symbol and returns frames keyed
        by the original universe symbol.
        """
        if not symbols:
            return {}

        stored_symbol_map = stored_symbol_map or {s: s for s in symbols}
        # universe -> db symbol (only those that map)
        universe_to_db = {u: stored_symbol_map.get(u, u) for u in symbols}
        db_to_universe: dict[str, list[str]] = {}
        for u, db_s in universe_to_db.items():
            db_to_universe.setdefault(db_s, []).append(u)

        db_symbols = list(db_to_universe.keys())
        frames: dict[str, pd.DataFrame] = {symbol: pd.DataFrame() for symbol in symbols}
        chunk_size = 80
        for i in range(0, len(db_symbols), chunk_size):
            chunk = db_symbols[i : i + chunk_size]
            query = (
                select(
                    HistoricalCandle.symbol,
                    HistoricalCandle.timestamp.label("date"),
                    HistoricalCandle.open,
                    HistoricalCandle.high,
                    HistoricalCandle.low,
                    HistoricalCandle.close,
                    HistoricalCandle.volume,
                )
                .where(
                    HistoricalCandle.symbol.in_(chunk),
                    HistoricalCandle.resolution == timeframe,
                )
                .order_by(HistoricalCandle.symbol.asc(), HistoricalCandle.timestamp.asc())
            )
            async with AsyncSessionLocal() as db:
                result = await db.execute(query)
                rows = result.all()

            by_db: dict[str, list[dict]] = {symbol: [] for symbol in chunk}
            for row in rows:
                by_db[row.symbol].append(
                    {
                        "date": row.date,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                    }
                )

            for db_symbol, symbol_rows in by_db.items():
                if not symbol_rows:
                    continue
                df = pd.DataFrame(symbol_rows)
                df.set_index("date", inplace=True)
                df.sort_index(inplace=True)
                for col in ("open", "high", "low", "close"):
                    df[col] = df[col].astype(float)
                if "volume" in df.columns:
                    df["volume"] = df["volume"].apply(lambda v: safe_int(v, symbol=db_symbol, field="volume"))
                for universe_symbol in db_to_universe.get(db_symbol, [db_symbol]):
                    frames[universe_symbol] = df
        return frames

    async def upsert_candles_multi(
        self,
        updates: list[tuple[str, str, pd.DataFrame]],
    ) -> int:
        """
        Upsert candle frames for many symbols. Returns number of symbols written.
        Uses parallel per-symbol upserts bounded by a semaphore.
        """
        if not updates:
            return 0
        upsert_sem = asyncio.Semaphore(10)

        async def _upsert_one(symbol: str, timeframe: str, df: pd.DataFrame) -> int:
            if df is None or df.empty:
                return 0
            async with upsert_sem:
                await self.upsert_candles(symbol, timeframe, df)
            return 1

        results = await asyncio.gather(
            *(_upsert_one(sym, tf, d) for sym, tf, d in updates)
        )
        return sum(results)

    @staticmethod
    def is_daily_cache_fresh_enough(
        count: int,
        latest: datetime | None,
        required_history: int,
        max_staleness_minutes: float = 2880.0,
    ) -> bool:
        """True when DB history is complete enough for swing indicators and not stale (>2d for 1D)."""
        if count < required_history or latest is None:
            return False
        latest_no_tz = latest.replace(tzinfo=None) if getattr(latest, "tzinfo", None) else latest
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        staleness_minutes = (now - latest_no_tz).total_seconds() / 60.0
        return staleness_minutes <= max_staleness_minutes
