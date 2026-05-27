from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models.market_data import HistoricalCandle
from ..models.paper_trading import ExecutionEvent, ReplaySession
from ..models.system_log import SystemLog


class RetentionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def cleanup(self, *, logs_days: int = 30, events_days: int = 365, candles_days: int = 1825, replay_days: int = 90) -> dict[str, int]:
        now = datetime.utcnow()
        targets = [
            ("logs", delete(SystemLog).where(SystemLog.timestamp < now - timedelta(days=logs_days))),
            ("events", delete(ExecutionEvent).where(ExecutionEvent.created_at < now - timedelta(days=events_days))),
            ("candles", delete(HistoricalCandle).where(HistoricalCandle.timestamp < now - timedelta(days=candles_days))),
            ("replays", delete(ReplaySession).where(ReplaySession.created_at < now - timedelta(days=replay_days))),
        ]
        deleted: dict[str, int] = {}
        for name, stmt in targets:
            result = self.db.execute(stmt.execution_options(synchronize_session=False))
            deleted[name] = int(result.rowcount or 0)
        self.db.commit()
        return deleted

