import logging
import time
import asyncio
import pytz
import os
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select, func, text
from ..db.session import engine, AsyncSessionLocal
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
        self.circuit_breaker_failures = 0
        self.circuit_breaker_tripped_until = None

    def _is_trading_day(self, dt: datetime) -> bool:
        """Check if a given day is a weekend. A robust NSE holiday calendar can be integrated here."""
        return dt.weekday() < 5  # 0-4 are Mon-Fri

    async def detect_gaps(self, symbol: str, timeframe: str = '1D', min_gap_days: int = 3) -> list[dict]:
        # PostgreSQL syntax for gap detection
        query = text("""
        WITH lag_cte AS (
            SELECT symbol, resolution, timestamp, 
                   LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_timestamp
            FROM historical_candles
            WHERE symbol = :symbol AND resolution = :resolution
        )
        SELECT symbol, prev_timestamp, timestamp, 
               EXTRACT(DAY FROM (timestamp - prev_timestamp)) as days_diff
        FROM lag_cte
        WHERE EXTRACT(DAY FROM (timestamp - prev_timestamp)) > :min_gap
        ORDER BY days_diff DESC;
        """)
        
        gaps = []
        try:
            async with AsyncSessionLocal() as db:
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

    async def _parse_gap_timestamp(self, ts_str: str) -> datetime:
        # Parse timestamp strings
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
            # Clean up old repair cache in PostgreSQL
            try:
                async with AsyncSessionLocal() as db:
                    res = await db.execute(text("DELETE FROM empty_gaps WHERE expires_at < CURRENT_TIMESTAMP RETURNING symbol"))
                    deleted_rows = len(res.fetchall())
                    await db.commit()
                    if deleted_rows > 0:
                        logger.info(f"empty_gaps_cleanup_event", extra={"deleted_rows": deleted_rows})
            except Exception as e:
                logger.error(f"Failed to cleanup empty_gaps: {e}")

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

                    # Empty Repair Cache Check via PostgreSQL
                    try:
                        async with AsyncSessionLocal() as db:
                            res = await db.execute(
                                text("SELECT 1 FROM empty_gaps WHERE symbol = :s AND gap_date = :gd"),
                                {"s": symbol, "gd": gap_start_date}
                            )
                            is_cached = res.scalar() is not None
                    except Exception:
                        is_cached = False
                    
                    if is_cached:
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
                        # 0 rows returned - known empty gap (e.g. unexpected holiday). Cache for 24h.
                        expires_at = now_ist + timedelta(hours=24)
                        try:
                            async with AsyncSessionLocal() as db:
                                await db.execute(
                                    text("""
                                        INSERT INTO empty_gaps (symbol, gap_date, expires_at)
                                        VALUES (:s, :gd, :ea)
                                        ON CONFLICT (symbol, gap_date) DO UPDATE SET expires_at = EXCLUDED.expires_at
                                    """),
                                    {"s": symbol, "gd": gap_start_date, "ea": expires_at}
                                )
                                await db.commit()
                        except Exception as e:
                            logger.error(f"Failed to save empty gap for {symbol}: {e}")
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
