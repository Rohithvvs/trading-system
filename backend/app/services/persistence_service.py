from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from typing import List, Dict, Any
from ..models.market_data import HistoricalCandle, LatestScanResult

class PersistenceService:
    def __init__(self, db: Session):
        self.db = db

    def save_latest_scan_results(self, scan_results: List[Dict[str, Any]]) -> None:
        """
        Phase 2: INSERT ... ON CONFLICT DO UPDATE strategy for scan results.
        Ensures Zero-Downtime UI by constantly upserting current active state.
        """
        if not scan_results:
            return
            
        try:
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
            self.db.execute(upsert_stmt)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def upsert_historical_candles(self, candles: List[Dict[str, Any]]) -> None:
        """
        Phase 2: INSERT ... ON CONFLICT DO NOTHING
        Prevents duplicate data if the scanner runs twice for the same timeframe.
        """
        if not candles:
            return
            
        try:
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
            
            self.db.execute(upsert_stmt)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e
    def _insert(self, model):
        return pg_insert(model) if self.db.bind and self.db.bind.dialect.name == "postgresql" else sqlite_insert(model)
