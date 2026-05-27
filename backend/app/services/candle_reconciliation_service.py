import logging
import time
import asyncio
import pytz
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select, func, text
from ..db.session import SessionLocal, engine
from ..models.market_data import HistoricalCandle
from .market_data_service import MarketDataService
from .fyers_service import FyersService
from .lock_service import DistributedLockService, LockAcquisitionError
from ..utils import get_logger

logger = get_logger("app.candle_reconciliation")
IST = pytz.timezone("Asia/Kolkata")

class CandleReconciliationService:
    def __init__(self):
        self.md_service = MarketDataService()
        self.fyers_service = FyersService()
        self.lock_service = DistributedLockService("reconciliation_job", ttl_seconds=3600)
        self.failed_repair_cache = {}
        self.circuit_breaker_failures = 0
        self.circuit_breaker_tripped_until = None

    def _is_trading_day(self, dt: datetime) -> bool:
        """Check if a given day is a weekend. A robust NSE holiday calendar can be integrated here."""
        return dt.weekday() < 5  # 0-4 are Mon-Fri

    def detect_gaps(self, symbol: str, timeframe: str = '1D', min_gap_days: int = 3) -> list[dict]:
        # SQLite >= 3.25 supports window functions
        query = text("""
        WITH lag_cte AS (
            SELECT symbol, resolution, timestamp, 
                   LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_timestamp
            FROM historical_candles
            WHERE symbol = :symbol AND resolution = :resolution
        )
        SELECT symbol, prev_timestamp, timestamp, 
               julianday(timestamp) - julianday(prev_timestamp) as days_diff
        FROM lag_cte
        WHERE days_diff > :min_gap
        ORDER BY days_diff DESC;
        """)
        
        gaps = []
        try:
            with SessionLocal() as db:
                result = db.execute(query, {"symbol": symbol, "resolution": timeframe, "min_gap": min_gap_days})
                for row in result:
                    gaps.append({
                        "symbol": row.symbol,
                        "gap_start": row.prev_timestamp,
                        "gap_end": row.timestamp,
                        "days_diff": row.days_diff
                    })
        except Exception as e:
            logger.error(f"Failed to detect gaps for {symbol}: {e}")
        return gaps

    def verify_historical_migration(self):
        legacy_db_path = os.path.join(os.path.dirname(__file__), "candle_cache.db")
        if not os.path.exists(legacy_db_path):
            logger.info("Legacy candle_cache.db not found. Migration not needed.")
            return True
        logger.info("Starting historical migration validation...")
        legacy_counts = {}
        try:
            conn = sqlite3.connect(legacy_db_path)
            cursor = conn.execute("SELECT symbol, COUNT(*) FROM candles GROUP BY symbol")
            for row in cursor:
                legacy_counts[row[0]] = row[1]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to read legacy candle_cache.db: {e}")
            return False

        primary_counts = {}
        with SessionLocal() as db:
            stmt = select(
                HistoricalCandle.symbol, 
                func.count(HistoricalCandle.id)
            ).where(
                HistoricalCandle.resolution == '1D'
            ).group_by(HistoricalCandle.symbol)
            result = db.execute(stmt)
            for row in result:
                primary_counts[row[0]] = row[1]

        validation_failed = False
        for symbol, legacy_count in legacy_counts.items():
            primary_count = primary_counts.get(symbol, 0)
            if primary_count < legacy_count:
                logger.warning("historical_migration_mismatch", extra={
                    "symbol": symbol, "legacy_count": legacy_count, "primary_count": primary_count, "deficit": legacy_count - primary_count
                })
                validation_failed = True

        if validation_failed:
            logger.error("Migration validation failed. Do NOT remove candle_cache.db yet.")
            return False
        logger.info("Migration validation successful. All legacy candles exist in primary DB.")
        return True

    def _parse_gap_timestamp(self, ts_str: str) -> datetime:
        # Some SQLite strings have .000000, some don't.
        if isinstance(ts_str, datetime):
            return ts_str
        try:
            if "." in ts_str:
                return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
            return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.strptime(ts_str.split()[0], "%Y-%m-%d")

    async def reconciliation_job(self, symbols: list[str]):
        """Idempotent background job to scan and repair gaps with distributed locking and circuit breakers."""
        try:
            async with self.lock_service:
                await self._run_reconciliation(symbols)
        except LockAcquisitionError:
            logger.warning("Reconciliation job already running or locked. Skipping.")

    async def _run_reconciliation(self, symbols: list[str]):
        logger.info("Starting reconciliation job for %d symbols", len(symbols))
        now_ist = datetime.now(IST)
        
        if self.circuit_breaker_tripped_until and now_ist < self.circuit_breaker_tripped_until:
            logger.warning("reconciliation_circuit_breaker_active", extra={"until": self.circuit_breaker_tripped_until.isoformat()})
            return
            
        start_time = time.monotonic()
        total_gaps = 0
        repaired_gaps = 0
        stale_symbols = 0
        failed_repairs = 0
        skipped_repairs = 0
        holiday_gaps_skipped = 0
        repairs_this_cycle = 0
        MAX_REPAIRS_PER_CYCLE = 10

        for symbol in symbols:
            # Clean up old repair cache
            keys_to_delete = [k for k, v in self.failed_repair_cache.items() if now_ist > v]
            for k in keys_to_delete:
                del self.failed_repair_cache[k]

            # 1. Stale Detection using IST
            latest = self.md_service.get_latest_candle_time(symbol, '1D')
            if latest:
                latest_naive = latest.replace(tzinfo=None) if latest.tzinfo else latest
                latest_ist = IST.localize(latest_naive) if not latest.tzinfo else latest.astimezone(IST)
                if (now_ist - latest_ist).total_seconds() > (2 * 86400):
                    stale_symbols += 1
                    
            # 2. Detect Gaps
            gaps = self.detect_gaps(symbol, '1D', min_gap_days=3)
            if not gaps:
                continue
                
            for gap in gaps:
                total_gaps += 1
                try:
                    gap_start = self._parse_gap_timestamp(gap['gap_start'])
                    gap_end = self._parse_gap_timestamp(gap['gap_end'])
                    
                    # Holiday / Weekend Protection
                    # The missing days are strictly BETWEEN gap_start and gap_end
                    gap_start_date = gap_start.date()
                    gap_end_date = gap_end.date()
                    missing_days_count = (gap_end_date - gap_start_date).days - 1
                    
                    trading_days_in_gap = 0
                    if missing_days_count > 0:
                        trading_days_in_gap = sum(1 for n in range(1, missing_days_count + 1) 
                                                  if self._is_trading_day(gap_start_date + timedelta(days=n)))
                    
                    if trading_days_in_gap == 0:
                        holiday_gaps_skipped += 1
                        logger.info("holiday_gap_skipped", extra={"symbol": symbol, "gap_start": str(gap_start), "gap_end": str(gap_end)})
                        continue

                    # Empty Repair Cache Check
                    cache_key = f"{symbol}_{gap_start.date()}_{gap_end.date()}"
                    if cache_key in self.failed_repair_cache:
                        skipped_repairs += 1
                        continue
                        
                    if repairs_this_cycle >= MAX_REPAIRS_PER_CYCLE:
                        logger.info("reconciliation_throttled", extra={"reason": "max_repairs_reached"})
                        break

                    logger.info("Repairing gap for %s from %s to %s", symbol, gap_start.date(), gap_end.date())
                    
                    client = self.fyers_service._client()
                    payload = {
                        "symbol": self.fyers_service._normalize_symbol(symbol),
                        "resolution": "1D",
                        "date_format": "1",
                        "range_from": gap_start.date().isoformat(),
                        "range_to": gap_end.date().isoformat(),
                        "cont_flag": "1",
                    }
                    
                    # Run IO in thread
                    response = await asyncio.to_thread(self.fyers_service._request_history_with_retries, client, payload, symbol)
                    candle_rows = response.get("candles", []) if isinstance(response, dict) else []
                    
                    if candle_rows:
                        from ..schemas import OHLCVPoint
                        fetched = []
                        for row in candle_rows:
                            if len(row) < 6: continue
                            fetched.append(
                                OHLCVPoint(
                                    timestamp=self.fyers_service._parse_timestamp(row[0]),
                                    open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), volume=int(row[5]),
                                )
                            )
                        if fetched:
                            df = pd.DataFrame([{
                                "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                            } for c in fetched], index=[c.timestamp for c in fetched])
                            await asyncio.to_thread(self.md_service.upsert_candles, symbol, '1D', df)
                            repaired_gaps += 1
                            repairs_this_cycle += 1
                            self.circuit_breaker_failures = 0
                    else:
                        # 0 rows returned - known empty gap (e.g. unexpected holiday). Cache for 24h.
                        self.failed_repair_cache[cache_key] = now_ist + timedelta(hours=24)
                        skipped_repairs += 1
                        
                    # Backpressure safety: Sleep between API calls
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error("Failed to repair gap for %s: %s", symbol, e)
                    failed_repairs += 1
                    self.circuit_breaker_failures += 1
                    
                    if self.circuit_breaker_failures >= 5:
                        self.circuit_breaker_tripped_until = now_ist + timedelta(minutes=15)
                        logger.error("reconciliation_circuit_breaker_tripped", extra={"failures": self.circuit_breaker_failures})
                        break

            if repairs_this_cycle >= MAX_REPAIRS_PER_CYCLE or self.circuit_breaker_failures >= 5:
                break

        elapsed = time.monotonic() - start_time
        logger.info(
            "reconciliation_run_completed",
            extra={
                "total_gaps": total_gaps,
                "repaired_gaps": repaired_gaps,
                "failed_repairs": failed_repairs,
                "skipped_repairs": skipped_repairs,
                "holiday_gaps_skipped": holiday_gaps_skipped,
                "stale_symbols": stale_symbols,
                "elapsed_seconds": round(elapsed, 2)
            }
        )
