import pytest
from datetime import datetime, timedelta
from sqlalchemy import select, delete, or_

from app.models.event_calendar import EventCalendar, EventCalendarCoverage, EventIngestionRun
from app.services.event_calendar_service import EventCalendarService

@pytest.mark.anyio
async def test_event_ingestion_idempotency_and_deduplication(db):
    # Clean up state from previous test runs
    await db.execute(delete(EventCalendar).where(EventCalendar.symbol == "RELIANCE"))
    await db.commit()

    service = EventCalendarService(db)
    
    event_date = datetime(2026, 7, 15, 10, 0)
    ann_date = datetime(2026, 7, 10, 16, 0)

    # 1. Ingest corporate action first time
    status_1 = await service.ingest_event(
        symbol="RELIANCE",
        event_scope="COMPANY",
        event_type="EARNINGS",
        severity="HIGH",
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=event_date,
        announced_at=ann_date,
        title="Q1 Earnings"
    )
    assert status_1 == "INSERTED"

    # 2. Ingest exact same event again (same key: RELIANCE + 2026-07-15 + EARNINGS) with same/lower priority
    # This should update it
    status_2 = await service.ingest_event(
        symbol="RELIANCE",
        event_scope="COMPANY",
        event_type="EARNINGS",
        severity="CRITICAL",  # update severity
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=event_date,
        announced_at=ann_date,
        title="Q1 Earnings Revised"
    )
    assert status_2 == "UPDATED"

    # Verify update
    stmt = select(EventCalendar).where(EventCalendar.symbol == "RELIANCE")
    evt = (await db.scalars(stmt)).first()
    assert evt is not None
    assert evt.severity == "CRITICAL"
    assert evt.title == "Q1 Earnings Revised"

@pytest.mark.anyio
async def test_source_priority_conflict_resolution(db):
    # Clean up state from previous test runs
    await db.execute(delete(EventCalendar))
    await db.commit()

    service = EventCalendarService(db)
    event_date = datetime(2026, 7, 20, 11, 0)

    # 1. Ingest high priority event (Priority 1 = NSE_OFFICIAL)
    status_high = await service.ingest_event(
        symbol="INFY",
        event_scope="COMPANY",
        event_type="AGM",
        severity="HIGH",
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=event_date,
        title="Official AGM Announcement"
    )
    assert status_high == "INSERTED"

    # 2. Ingest low priority event for same key (Priority 5 = THIRD_PARTY)
    # This should be skipped and NOT overwrite the Priority 1 record
    status_low = await service.ingest_event(
        symbol="INFY",
        event_scope="COMPANY",
        event_type="AGM",
        severity="LOW",
        source="THIRD_PARTY",
        source_priority=5,
        event_date=event_date,
        title="Third Party AGM Feed"
    )
    assert status_low == "SKIPPED"

    # Verify that the database record is STILL the high-priority one
    stmt = select(EventCalendar).where(EventCalendar.symbol == "INFY")
    evt = (await db.scalars(stmt)).first()
    assert evt is not None
    assert evt.source == "NSE_OFFICIAL"
    assert evt.source_priority == 1
    assert evt.title == "Official AGM Announcement"

@pytest.mark.anyio
async def test_announced_at_lookahead_protection(db):
    # Clean up state from previous test runs
    await db.execute(delete(EventCalendar))
    await db.commit()

    service = EventCalendarService(db)
    
    event_date = datetime(2026, 7, 25)
    # Announcement date is set in the future relative to scan_date
    future_announcement = datetime(2026, 7, 12, 10, 0)
    past_announcement = datetime(2026, 7, 9, 10, 0)

    # Ingest event 1 (announced in the future)
    await service.ingest_event(
        symbol="WIPRO",
        event_scope="COMPANY",
        event_type="SPLIT",
        severity="HIGH",
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=event_date,
        announced_at=future_announcement,
        title="Future Announced Stock Split"
    )

    # Ingest event 2 (announced in the past)
    await service.ingest_event(
        symbol="WIPRO",
        event_scope="COMPANY",
        event_type="BONUS",
        severity="HIGH",
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=event_date,
        announced_at=past_announcement,
        title="Past Announced Stock Bonus"
    )

    # If scan_date is 2026-07-10:
    # - We should ONLY see the PAST announcement (Bonus)
    # - The FUTURE announcement (Split) must be hidden to prevent look-ahead bias!
    scan_date = datetime(2026, 7, 10)
    upcoming_events = await service.get_upcoming_events(symbol="WIPRO", scan_date=scan_date, days_ahead=20)
    
    assert len(upcoming_events) == 1
    assert upcoming_events[0].event_type == "BONUS"
    assert upcoming_events[0].title == "Past Announced Stock Bonus"

@pytest.mark.anyio
async def test_macro_event_vs_symbol_handling(db):
    # Clean up state from previous test runs
    await db.execute(delete(EventCalendar))
    await db.commit()

    service = EventCalendarService(db)
    
    # 1. Ingest company specific event
    await service.ingest_event(
        symbol="TATASTEEL",
        event_scope="COMPANY",
        event_type="EARNINGS",
        severity="MEDIUM",
        source="NSE_OFFICIAL",
        source_priority=1,
        event_date=datetime(2026, 7, 12),
        announced_at=datetime(2026, 7, 9),
        title="Earnings Tata Steel"
    )

    # 2. Ingest macro market event (symbol is None)
    await service.ingest_event(
        symbol=None,
        event_scope="MARKET",
        event_type="GDP_DATA",
        severity="HIGH",
        source="GOVT_OFFICIAL",
        source_priority=2,
        event_date=datetime(2026, 7, 14),
        announced_at=datetime(2026, 7, 9),
        title="India GDP Release"
    )

    # Query upcoming events for TATASTEEL
    # Both the company event and the macro market event should be returned
    scan_date = datetime(2026, 7, 10)
    events = await service.get_upcoming_events(symbol="TATASTEEL", scan_date=scan_date, days_ahead=5)
    
    assert len(events) == 2
    scopes = [e.event_scope for e in events]
    assert "COMPANY" in scopes
    assert "MARKET" in scopes

@pytest.mark.anyio
async def test_coverage_and_ingestion_runs(db):
    # Clean up state from previous test runs
    await db.execute(delete(EventCalendar))
    await db.execute(delete(EventCalendarCoverage))
    await db.execute(delete(EventIngestionRun))
    await db.commit()

    service = EventCalendarService(db)
    
    # Trigger mock ingestion feed run
    result = await service.run_mock_ingestion_feed()
    assert result["status"] == "COMPLETED"
    assert result["seen"] == 4
    
    # Retrieve coverage
    coverage_list = await service.get_latest_coverage("NSE_MOCK_FEED")
    assert len(coverage_list) > 0
    assert coverage_list[0].coverage_status == "COMPLETE"
    assert coverage_list[0].freshness_status == "FRESH"
