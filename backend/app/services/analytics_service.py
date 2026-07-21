from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.analysis import AnalysisHistory, StrategyPerformanceLog
from ..models.stock import WatchedStock
from ..schemas import AnalysisMode
from ..services.fyers_service import FyersService
from ..utils import get_logger


class AnalyticsService:
    def __init__(self) -> None:
        self.logger = get_logger("app.analytics")
        self.fyers = FyersService()

    async def initialize(self) -> None:
        """Async initialization if needed in the future."""
        pass

    async def track_strategy_drift(self, db: AsyncSession) -> None:
        """
        Background worker that retrieves historical recommendations (5, 10, 20 days old)
        and calculates the realized alpha to track strategy performance and drift.
        """
        self.logger.info("Starting Strategy Drift & Performance Tracker...")
        now = datetime.now(timezone.utc).date()
        
        target_days = [5, 10, 20]

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
            res = await db.execute(stmt)
            records = res.all()
            
            if not records:
                continue

            self.logger.info("Found %d historical BUY recommendations from %d days ago.", len(records), days)

            sem = asyncio.Semaphore(5)
            
            async def fetch_data(history: AnalysisHistory, symbol: str, lookback_days: int):
                async with sem:
                    try:
                        # 1. Fetch current price
                        current_price = await self.fyers.fetch_ltp(symbol)
                        if not current_price:
                            return None
                            
                        # 2. Extract Entry Price
                        candles = await self.fyers.fetch_ohlcv(symbol, AnalysisMode.swing, "1d", lookback_days + 5)
                        if not candles:
                            return None
                        
                        target_date_str = history.created_at.strftime("%Y-%m-%d")
                        entry_candle = next((c for c in candles if c.timestamp.strftime("%Y-%m-%d") == target_date_str), None)
                        
                        if not entry_candle:
                            entry_candle = candles[0]
                            
                        entry_price = entry_candle.close
                        if entry_price <= 0:
                            return None
                            
                        alpha = ((current_price - entry_price) / entry_price) * 100
                        
                        dominant_agent = "Technical Catalyst"
                        if history.sentiment_score > 0.5:
                            dominant_agent = "News/Sentiment Catalyst"
                        elif history.backtest_score > 15:
                            dominant_agent = "Backtest Flow"
                            
                        return {
                            "symbol": symbol,
                            "history": history,
                            "alpha": alpha,
                            "dominant_agent": dominant_agent
                        }
                    except Exception as e:
                        self.logger.error("Failed to process strategy drift for %s: %s", symbol, e)
                        return None

            # Execute concurrent FYERS fetches OUTSIDE active transaction usage
            fetched_results = await asyncio.gather(*(fetch_data(h, s, days) for h, s in records))
            
            # Now sequentially persist into DB to prevent concurrent session access
            for res_data in fetched_results:
                if not res_data:
                    continue
                symbol = res_data["symbol"]
                history = res_data["history"]
                alpha = res_data["alpha"]
                dominant_agent = res_data["dominant_agent"]
                
                log_stmt = select(StrategyPerformanceLog).where(
                    StrategyPerformanceLog.symbol == symbol,
                    StrategyPerformanceLog.screened_date >= start_dt,
                    StrategyPerformanceLog.screened_date <= end_dt
                )
                log_entry = (await db.execute(log_stmt)).scalar_one_or_none()
                if not log_entry:
                    log_entry = StrategyPerformanceLog(
                        symbol=symbol,
                        screened_date=history.created_at,
                        initial_score=history.technical_score, 
                        dominant_agent=dominant_agent
                    )
                    db.add(log_entry)
                
                if days == 5:
                    log_entry.realized_return_5d = round(alpha, 2)
                elif days == 10:
                    log_entry.realized_return_10d = round(alpha, 2)
                elif days == 20:
                    log_entry.realized_return_20d = round(alpha, 2)

        self.logger.info("Strategy Drift Tracker DB operations complete.")


    async def query_by_situation_tags(
        self,
        db: AsyncSession,
        tags: list[str],
        recommendation: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100
    ) -> list[AnalysisHistory]:
        """Query historical recommendations filtered by situation tags (all tags must match).

        Optional filters (FR-007): recommendation action and created_at date range.
        """
        from sqlalchemy.orm import selectinload
        stmt = select(AnalysisHistory).options(selectinload(AnalysisHistory.stock))
        
        dialect_name = db.bind.dialect.name if db.bind else "postgresql"
        conditions = []
        if recommendation:
            conditions.append(AnalysisHistory.recommendation == recommendation)
        if start_date is not None:
            conditions.append(AnalysisHistory.created_at >= start_date)
        if end_date is not None:
            conditions.append(AnalysisHistory.created_at <= end_date)
            
        if dialect_name == "postgresql":
            if tags:
                conditions.append(AnalysisHistory.situation_tags.contains(tags))
            stmt = stmt.where(*conditions).order_by(AnalysisHistory.created_at.desc()).limit(limit)
            return list((await db.scalars(stmt)).all())

        # SQLite stores ChoiceArray as JSON text. Use quoted-token LIKE to avoid
        # substring false matches (e.g. TAG matching TAG_EXTRA), then exact-filter.
        if tags:
            for tag in tags:
                # JSON dumps list elements as "TAG"; quoted match is tag-boundary safe.
                conditions.append(AnalysisHistory.situation_tags.like(f'%"{tag}"%'))

        stmt = stmt.where(*conditions).order_by(AnalysisHistory.created_at.desc()).limit(limit * 5 if tags else limit)
        candidates = list((await db.scalars(stmt)).all())
        if not tags:
            return candidates[:limit]

        required = set(tags)
        exact = [
            row for row in candidates
            if required.issubset(set(row.situation_tags or []))
        ]
        return exact[:limit]

