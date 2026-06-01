from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import List, Dict, Any
from ..models.market_data import HistoricalCandle, LatestScanResult

class PersistenceService:
    async def __init__(self, db: AsyncSession):
        self.db = db

    async def save_latest_scan_results(self, scan_results: List[Dict[str, Any]]) -> None:
        """
        Phase 2: INSERT ... ON CONFLICT DO UPDATE strategy for scan results.
        Ensures Zero-Downtime UI by constantly upserting current active state.
        """
        if not scan_results:
            return
            
        stmt = self._insert(LatestScanResult).values(scan_results)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=['symbol'],
            set_={
                'signal_type': stmt.excluded.signal_type,
                'score': stmt.excluded.score,
                'confidence': stmt.excluded.confidence,
                'scanned_at': stmt.excluded.scanned_at,
                'updated_at': func.now()
            }
        )
        await self.db.execute(upsert_stmt)

    async def upsert_historical_candles(self, candles: List[Dict[str, Any]]) -> None:
        """
        Phase 2: INSERT ... ON CONFLICT DO UPDATE
        Prevents duplicate data if the scanner runs twice for the same timeframe.
        """
        if not candles:
            return
            
        stmt = self._insert(HistoricalCandle).values(candles)
        
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'resolution', 'timestamp'],
            set_={
                'open': stmt.excluded.open,
                'high': stmt.excluded.high,
                'low': stmt.excluded.low,
                'close': stmt.excluded.close,
                'volume': stmt.excluded.volume,
                'source': stmt.excluded.source,
                'updated_at': func.now(),
            },
        )
        
        await self.db.execute(upsert_stmt)

    def _insert(self, model):
        return pg_insert(model)
