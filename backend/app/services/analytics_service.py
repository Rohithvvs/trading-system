from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, date

from sqlalchemy import select

from ..db.session import SessionLocal
from ..models.analysis import AnalysisHistory, StrategyPerformanceLog
from ..models.stock import WatchedStock
from ..services.fyers_service import FyersService
from ..utils import get_logger


class AnalyticsService:
    def __init__(self) -> None:
        self.logger = get_logger("app.analytics")
        self.fyers = FyersService()

    async def track_strategy_drift(self) -> None:
        """
        Background worker that retrieves historical recommendations (5, 10, 20 days old)
        and calculates the realized alpha to track strategy performance and drift.
        """
        self.logger.info("Starting Strategy Drift & Performance Tracker...")
        now = datetime.utcnow().date()
        
        target_days = [5, 10, 20]

        with SessionLocal() as db:
            for days in target_days:
                # Find the target date
                target_date = now - timedelta(days=days)
                start_dt = datetime.combine(target_date, datetime.min.time())
                end_dt = datetime.combine(target_date, datetime.max.time())
                
                # Fetch BUY recommendations strictly from that specific historical day
                stmt = select(AnalysisHistory, WatchedStock.symbol).join(WatchedStock).where(
                    AnalysisHistory.recommendation == "BUY",
                    AnalysisHistory.created_at >= start_dt,
                    AnalysisHistory.created_at <= end_dt
                )
                records = db.execute(stmt).all()
                
                if not records:
                    continue

                self.logger.info("Found %d historical BUY recommendations from %d days ago.", len(records), days)

                sem = asyncio.Semaphore(5)
                
                async def fetch_and_log(history: AnalysisHistory, symbol: str, lookback_days: int):
                    async with sem:
                        try:
                            # 1. Fetch current price
                            current_price = await asyncio.to_thread(self.fyers.fetch_ltp, symbol)
                            if not current_price:
                                return
                                
                            # 2. Extract Entry Price
                            # Since we didn't store the exact exact execution price in AnalysisHistory, 
                            # we fetch the closing price of the candle on the day the recommendation was made.
                            candles = await asyncio.to_thread(self.fyers.fetch_ohlcv, symbol, "swing", "1d", lookback_days + 5)
                            if not candles:
                                return
                            
                            # Find the candle that matches the screened_date
                            target_date_str = history.created_at.strftime("%Y-%m-%d")
                            entry_candle = next((c for c in candles if c.timestamp.strftime("%Y-%m-%d") == target_date_str), None)
                            
                            # Fallback to the oldest candle if exact date match fails due to weekends/holidays
                            if not entry_candle:
                                entry_candle = candles[0]
                                
                            entry_price = entry_candle.close
                            if entry_price <= 0:
                                return
                                
                            alpha = ((current_price - entry_price) / entry_price) * 100
                            
                            # 3. Determine Dominant Agent (Heuristic based on stored scores)
                            dominant_agent = "Technical Catalyst"
                            if history.sentiment_score > 0.5:
                                dominant_agent = "News/Sentiment Catalyst"
                            elif history.backtest_score > 15:
                                dominant_agent = "Backtest Flow"
                                
                            # 4. Upsert into strategy_performance_log
                            log_entry = db.scalar(
                                select(StrategyPerformanceLog).where(
                                    StrategyPerformanceLog.symbol == symbol,
                                    StrategyPerformanceLog.screened_date >= start_dt,
                                    StrategyPerformanceLog.screened_date <= end_dt
                                )
                            )
                            if not log_entry:
                                log_entry = StrategyPerformanceLog(
                                    symbol=symbol,
                                    screened_date=history.created_at,
                                    initial_score=history.technical_score, 
                                    dominant_agent=dominant_agent
                                )
                                db.add(log_entry)
                            
                            if lookback_days == 5:
                                log_entry.realized_return_5d = round(alpha, 2)
                            elif lookback_days == 10:
                                log_entry.realized_return_10d = round(alpha, 2)
                            elif lookback_days == 20:
                                log_entry.realized_return_20d = round(alpha, 2)
                                
                        except Exception as e:
                            self.logger.error("Failed to process strategy drift for %s: %s", symbol, e)

                # Execute concurrent FYERS fetches for this specific day batch
                await asyncio.gather(*(fetch_and_log(h, s, days) for h, s in records))
                
            db.commit()
            self.logger.info("Strategy Drift Tracker completed successfully.")
