from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Any
from ..db.session import get_db
from ..services.event_calendar_service import EventCalendarService

router = APIRouter(prefix="/api/events", tags=["Event Risk Calendar"])

@router.post("/ingest/mock", response_model=dict)
async def ingest_mock_events(db: AsyncSession = Depends(get_db)) -> Any:
    """
    Run the idempotent mock ingestion run to populate standard corporate actions
    and macro events.
    """
    service = EventCalendarService(db)
    result = await service.run_mock_ingestion_feed()
    return result

@router.get("/upcoming", response_model=list)
async def get_upcoming_events(
    symbol: str,
    scan_date: str,
    days_ahead: int = 15,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Query upcoming company-specific or market-wide macro events relative to a scan date.
    Employs look-ahead bias protection.
    """
    try:
        scan_dt = datetime.fromisoformat(scan_date.replace("Z", "+00:00"))
    except ValueError:
        try:
            scan_dt = datetime.strptime(scan_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scan_date format. Use ISO-8601 or YYYY-MM-DD.")
            
    service = EventCalendarService(db)
    events = await service.get_upcoming_events(symbol=symbol, scan_date=scan_dt, days_ahead=days_ahead)
    return [
        {
            "id": e.id,
            "symbol": e.symbol,
            "event_scope": e.event_scope,
            "event_type": e.event_type,
            "severity": e.severity,
            "source": e.source,
            "event_date": e.event_date.isoformat() if e.event_date else None,
            "announced_at": e.announced_at.isoformat() if e.announced_at else None,
            "title": e.title,
            "summary": e.summary,
            "is_confirmed": e.is_confirmed
        }
        for e in events
    ]

@router.get("/coverage", response_model=list)
async def get_coverage_audit(source: str | None = None, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Get latest data coverage and freshness auditing stats.
    """
    service = EventCalendarService(db)
    coverage = await service.get_latest_coverage(source=source)
    return [
        {
            "id": c.id,
            "coverage_date": c.coverage_date.isoformat() if c.coverage_date else None,
            "source": c.source,
            "scope": c.scope,
            "symbols_checked": c.symbols_checked,
            "records_loaded": c.records_loaded,
            "coverage_status": c.coverage_status,
            "freshness_status": c.freshness_status,
            "warnings": c.warnings
        }
        for c in coverage
    ]
