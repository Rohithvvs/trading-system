import pandas as pd
from datetime import datetime, timezone
import time
import random
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from ..db.session import SessionLocal, engine
from ..models.market_data import HistoricalCandle
from ..utils import get_logger

logger = get_logger("app.market_data")

class MarketDataService:
    def get_latest_candle_time(self, symbol: str, timeframe: str) -> datetime | None:
        with SessionLocal() as db:
            stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
            result = db.execute(stmt).scalar_one_or_none()
            return result

    def get_candle_count(self, symbol: str, timeframe: str) -> int:
        with SessionLocal() as db:
            stmt = select(func.count(HistoricalCandle.timestamp)).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == timeframe
            )
            result = db.execute(stmt).scalar()
            return result or 0

    def validate_candle_continuity(self, symbol: str, timeframe: str, expected_count: int):
        from .cache_state import CacheState, CacheHealthContext
        count = self.get_candle_count(symbol, timeframe)
        latest = self.get_latest_candle_time(symbol, timeframe)
        
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
            
        gap_count = 0
        with SessionLocal() as db:
            dup_stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol, HistoricalCandle.resolution == timeframe
            ).group_by(HistoricalCandle.timestamp).having(func.count(HistoricalCandle.timestamp) > 1)
            duplicates = db.execute(dup_stmt).fetchall()
            
            if duplicates:
                logger.error("corrupted_cache_duplicates", extra={"symbol": symbol, "resolution": timeframe})
                return CacheHealthContext(
                    symbol=symbol, timeframe=timeframe, cached_rows=count, required_rows=expected_count,
                    continuity_gap_count=len(duplicates), cache_state=CacheState.CORRUPTED, is_valid_for_indicators=False
                )
                
            df = self.load_full_history(symbol, timeframe)
            if df is not None and not df.empty:
                df = df.sort_index()
                diffs = df.index.to_series().diff()
                if timeframe == '1D':
                    gaps = diffs[diffs > pd.Timedelta(days=5)]
                    gap_count = len(gaps)
                    if gap_count > 0:
                        logger.error("corrupted_candle_ranges", extra={"symbol": symbol, "timeframe": timeframe, "gap_count": gap_count})
                        
        is_complete = count >= expected_count
        
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

    def upsert_candles(self, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        if candles_df is None or candles_df.empty:
            return

        # 1. Reduce Transaction Window: Transform dataframe outside session
        records = []
        for index, row in candles_df.iterrows():
            dt = index
            if hasattr(dt, "to_pydatetime"):
                dt = dt.to_pydatetime()
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
                
            records.append({
                "symbol": symbol,
                "resolution": timeframe,
                "timestamp": dt,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"])
            })

        # 3. SQLite Parameter Explosion Fix: Chunk the batches to 900
        MAX_CHUNK_SIZE = 900
        for i in range(0, len(records), MAX_CHUNK_SIZE):
            chunk = records[i:i + MAX_CHUNK_SIZE]
            self._upsert_chunk(symbol, timeframe, chunk)

    def _upsert_chunk(self, symbol: str, timeframe: str, chunk_records: list[dict]):
        batch_size = len(chunk_records)
        new_timestamps = {r["timestamp"] for r in chunk_records}
        
        # 2. Retry Safety: Exponential Backoff & Jitter
        max_retries = 5
        base_delay = 0.5

        for attempt in range(1, max_retries + 1):
            start_time = time.monotonic()
            try:
                with SessionLocal() as db:
                    # Observability: count duplicates
                    existing_stmt = select(HistoricalCandle.timestamp).where(
                        HistoricalCandle.symbol == symbol,
                        HistoricalCandle.resolution == timeframe,
                        HistoricalCandle.timestamp.in_(new_timestamps)
                    )
                    existing_ts = set(db.scalars(existing_stmt).all())
                    duplicate_count = len(existing_ts)
                    updated_count = duplicate_count
                    inserted_count = batch_size - duplicate_count

                    insert_fn = pg_insert if db.bind and db.bind.dialect.name == "postgresql" else sqlite_insert
                    stmt = insert_fn(HistoricalCandle).values(chunk_records)
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
                    db.execute(stmt)
                    db.commit()
                    
                    # Post-Commit Verification
                    verify_stmt = select(HistoricalCandle.timestamp).where(
                        HistoricalCandle.symbol == symbol,
                        HistoricalCandle.resolution == timeframe
                    ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
                    verified_ts = db.execute(verify_stmt).scalar_one_or_none()
                    if not verified_ts:
                        logger.error("silent_rollback_detected", extra={"symbol": symbol, "resolution": timeframe})
                    
                    elapsed_ms = (time.monotonic() - start_time) * 1000
                    
                    logger.info(
                        "sqlite_chunked_batch_executed",
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
                    time.sleep(sleep_time)
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

    def load_full_history(self, symbol: str, timeframe: str) -> pd.DataFrame:
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
        
        with SessionLocal() as db:
            df = pd.read_sql_query(query, db.get_bind())
        if not df.empty:
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
        return df
