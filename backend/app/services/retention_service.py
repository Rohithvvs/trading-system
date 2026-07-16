from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market_data import HistoricalCandle, ScanSnapshot
from ..models.paper_trading import ExecutionEvent, ReplaySession
from ..models.system_log import SystemLog


class RetentionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def cleanup(self, *, logs_days: int = 30, events_days: int = 365, candles_days: int = 1825, replay_days: int = 90, snapshots_days: int = 30) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        targets = [
            ("logs", delete(SystemLog).where(SystemLog.timestamp < now - timedelta(days=logs_days))),
            ("events", delete(ExecutionEvent).where(ExecutionEvent.created_at < now - timedelta(days=events_days))),
            ("candles", delete(HistoricalCandle).where(HistoricalCandle.timestamp < now - timedelta(days=candles_days))),
            ("replays", delete(ReplaySession).where(ReplaySession.created_at < now - timedelta(days=replay_days))),
            ("snapshots", delete(ScanSnapshot).where(ScanSnapshot.scan_timestamp < now - timedelta(days=snapshots_days))),
        ]
        deleted: dict[str, int] = {}
        for name, stmt in targets:
            result = await self.db.execute(stmt.execution_options(synchronize_session=False))
            deleted[name] = int(result.rowcount or 0)
        await self.db.commit()
        return deleted

