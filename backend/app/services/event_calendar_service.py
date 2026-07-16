import pytz
import pandas as pd
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.event_calendar import EventCalendar, EventCalendarCoverage, EventIngestionRun
from ..utils import get_logger

logger = get_logger("app.event_calendar")

class EventCalendarService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    def _to_ist_datetime(self, val) -> datetime:
        """
        Normalize any datetime representation to a naive datetime in Asia/Kolkata timezone.
        """
        if val is None:
            return None
        if isinstance(val, str):
            val = pd.to_datetime(val)
        
        has_tz = False
        if hasattr(val, "tzinfo") and val.tzinfo is not None:
            has_tz = True
        elif hasattr(val, "tz") and val.tz is not None:
            has_tz = True

        tz_kolkata = pytz.timezone("Asia/Kolkata")
        if has_tz:
            if hasattr(val, "tz_convert"):
                val_ist = val.tz_convert(tz_kolkata)
            else:
                val_ist = val.astimezone(tz_kolkata)
            return val_ist.replace(tzinfo=None)
        else:
            # Assume it's naive local (Asia/Kolkata)
            return val

    async def create_ingestion_run(self, source: str) -> EventIngestionRun:
        run = EventIngestionRun(
            source=source,
            started_at=datetime.now(timezone.utc),
            status="RUNNING"
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def complete_ingestion_run(
        self,
        run: EventIngestionRun,
        status: str,
        seen: int,
        inserted: int,
        updated: int,
        skipped: int,
        errors: int,
        notes: str = None
    ) -> None:
        run.completed_at = datetime.now(timezone.utc)
        run.status = status
        run.records_seen = seen
        run.inserted_count = inserted
        run.updated_count = updated
        run.skipped_count = skipped
        run.error_count = errors
        run.notes = notes
        await self.db.commit()

    async def ingest_event(
        self,
        symbol: str | None,
        event_scope: str,
        event_type: str,
        severity: str,
        source: str,
        source_priority: int,
        event_date: datetime,
        title: str,
        event_time: str = None,
        announced_at: datetime = None,
        summary: str = None,
        raw_reference: str = None,
        is_confirmed: bool = True
    ) -> str:
        """
        Ingest a single event into the calendar with priority-conflict resolution.
        Returns: 'INSERTED', 'UPDATED', 'SKIPPED' (priority conflict), or 'ERROR'.
        """
        norm_event_date = self._to_ist_datetime(event_date)
        norm_announced_at = self._to_ist_datetime(announced_at) if announced_at else norm_event_date

        sym_key = symbol if symbol else "MACRO"
        
        # Check if an event with same logical key exists: same date, same symbol/macro, same event_type
        # Deterministic Key: (symbol or MACRO) + event_date + event_type
        stmt = select(EventCalendar).where(
            and_(
                EventCalendar.symbol == symbol,
                EventCalendar.event_date == norm_event_date,
                EventCalendar.event_type == event_type
            )
        )
        existing = (await self.db.scalars(stmt)).first()

        if existing:
            # Conflict Resolution: Never overwrite higher priority source with lower priority source.
            # Lower priority number = higher precedence (1 = highest, 5 = lowest).
            if source_priority <= existing.source_priority:
                # Update existing
                existing.severity = severity
                existing.source = source
                existing.source_priority = source_priority
                existing.event_time = event_time
                existing.announced_at = norm_announced_at
                existing.title = title
                existing.summary = summary
                existing.raw_reference = raw_reference
                existing.is_confirmed = is_confirmed
                await self.db.commit()
                return "UPDATED"
            else:
                # Skip lower priority update
                logger.info(
                    "Ingestion SKIPPED due to priority conflict | symbol=%s | date=%s | incoming_priority=%d | existing_priority=%d",
                    sym_key, norm_event_date.date(), source_priority, existing.source_priority
                )
                return "SKIPPED"
        else:
            # Insert new
            new_event = EventCalendar(
                symbol=symbol,
                event_scope=event_scope,
                event_type=event_type,
                severity=severity,
                source=source,
                source_priority=source_priority,
                event_date=norm_event_date,
                event_time=event_time,
                announced_at=norm_announced_at,
                title=title,
                summary=summary,
                raw_reference=raw_reference,
                is_confirmed=is_confirmed
            )
            self.db.add(new_event)
            await self.db.commit()
            return "INSERTED"

    async def log_coverage(
        self,
        source: str,
        scope: str,
        symbols_checked: int,
        records_loaded: int,
        coverage_status: str,
        freshness_status: str,
        warnings: str = None
    ) -> None:
        coverage = EventCalendarCoverage(
            coverage_date=datetime.now(timezone.utc),
            source=source,
            scope=scope,
            symbols_checked=symbols_checked,
            records_loaded=records_loaded,
            coverage_status=coverage_status,
            freshness_status=freshness_status,
            warnings=warnings
        )
        self.db.add(coverage)
        await self.db.commit()

    # Query interfaces (Pure database read-only queries with look-ahead protection)
    
    async def get_upcoming_events(
        self,
        symbol: str,
        scan_date: datetime,
        days_ahead: int = 15
    ) -> list[EventCalendar]:
        """
        Get upcoming company-specific or sector/market-wide events relative to scan_date.
        
        ANTI-LOOK-AHEAD BIAS: We only return events where announced_at <= scan_date.
        """
        norm_scan_date = self._to_ist_datetime(scan_date)
        end_date = norm_scan_date + timedelta(days=days_ahead)

        stmt = select(EventCalendar).where(
            and_(
                or_(
                    EventCalendar.symbol == symbol,
                    EventCalendar.event_scope.in_(["MARKET", "GLOBAL"])
                ),
                EventCalendar.event_date >= norm_scan_date,
                EventCalendar.event_date <= end_date,
                EventCalendar.announced_at <= norm_scan_date  # Anti-look-ahead guard
            )
        ).order_by(EventCalendar.event_date.asc())

        results = (await self.db.scalars(stmt)).all()
        return list(results)

    async def get_market_events_range(
        self,
        start_date: datetime,
        end_date: datetime,
        scan_date: datetime
    ) -> list[EventCalendar]:
        """
        Get market-wide and global events inside a date range.
        
        ANTI-LOOK-AHEAD BIAS: announced_at <= scan_date.
        """
        norm_start = self._to_ist_datetime(start_date)
        norm_end = self._to_ist_datetime(end_date)
        norm_scan = self._to_ist_datetime(scan_date)

        stmt = select(EventCalendar).where(
            and_(
                EventCalendar.event_scope.in_(["MARKET", "GLOBAL"]),
                EventCalendar.event_date >= norm_start,
                EventCalendar.event_date <= norm_end,
                EventCalendar.announced_at <= norm_scan
            )
        ).order_by(EventCalendar.event_date.asc())

        results = (await self.db.scalars(stmt)).all()
        return list(results)

    async def get_latest_coverage(self, source: str = None) -> list[EventCalendarCoverage]:
        stmt = select(EventCalendarCoverage)
        if source:
            stmt = stmt.where(EventCalendarCoverage.source == source)
        stmt = stmt.order_by(EventCalendarCoverage.coverage_date.desc())
        
        results = (await self.db.scalars(stmt)).all()
        return list(results)

    # Ingestion adapter stubs (TEMPORARY_ASSUMPTION / NOT_YET_IMPLEMENTED)
    
    async def run_mock_ingestion_feed(self) -> dict:
        """
        Idempotent mock ingestion run populating standard corporate actions and RBI policy announcements
        to verify data engineering capabilities.
        """
        run = await self.create_ingestion_run("NSE_MOCK_FEED")
        seen = 0
        inserted = 0
        updated = 0
        skipped = 0
        errors = 0

        # Define 4 mock events
        mock_data = [
            # Event 1: NSE official dividend filing (High Priority)
            {
                "symbol": "TCS",
                "scope": "COMPANY",
                "type": "DIVIDEND",
                "severity": "MEDIUM",
                "source": "NSE_OFFICIAL",
                "priority": 1,
                "date": datetime(2026, 7, 15, 10, 0),
                "ann": datetime(2026, 7, 10, 16, 0),
                "title": "Interim Dividend Announcement",
                "summary": "TCS announced interim dividend of INR 10 per share."
            },
            # Event 2: RBI Interest rate decision (High Priority Macro)
            {
                "symbol": None,
                "scope": "MARKET",
                "type": "INTEREST_RATE",
                "severity": "CRITICAL",
                "source": "RBI_OFFICIAL",
                "priority": 1,
                "date": datetime(2026, 7, 20, 11, 0),
                "ann": datetime(2026, 7, 20, 11, 0),
                "title": "RBI Monetary Policy Committee decision",
                "summary": "RBI announced interest rate decision."
            },
            # Event 3: Third-party dividend info for TCS (Low Priority, should be skipped if TCS dividend exists)
            {
                "symbol": "TCS",
                "scope": "COMPANY",
                "type": "DIVIDEND",
                "severity": "LOW",
                "source": "THIRD_PARTY",
                "priority": 5, # low priority
                "date": datetime(2026, 7, 15, 10, 0),
                "ann": datetime(2026, 7, 11, 9, 0),
                "title": "TCS Dividend Info",
                "summary": "Convenience feed information about TCS dividend."
            },
            # Event 4: Global GDP release (Macro)
            {
                "symbol": None,
                "scope": "GLOBAL",
                "type": "GDP",
                "severity": "HIGH",
                "source": "GOVT_OFFICIAL",
                "priority": 3,
                "date": datetime(2026, 7, 25, 17, 30),
                "ann": datetime(2026, 7, 25, 17, 30),
                "title": "Global GDP Release",
                "summary": "Official economic calendar GDP numbers."
            }
        ]

        try:
            for item in mock_data:
                seen += 1
                status = await self.ingest_event(
                    symbol=item["symbol"],
                    event_scope=item["scope"],
                    event_type=item["type"],
                    severity=item["severity"],
                    source=item["source"],
                    source_priority=item["priority"],
                    event_date=item["date"],
                    title=item["title"],
                    announced_at=item["ann"],
                    summary=item["summary"]
                )
                if status == "INSERTED":
                    inserted += 1
                elif status == "UPDATED":
                    updated += 1
                elif status == "SKIPPED":
                    skipped += 1
                else:
                    errors += 1

            # Log coverage audit
            await self.log_coverage(
                source="NSE_MOCK_FEED",
                scope="MIXED",
                symbols_checked=1,
                records_loaded=inserted + updated,
                coverage_status="COMPLETE",
                freshness_status="FRESH"
            )

            await self.complete_ingestion_run(run, "COMPLETED", seen, inserted, updated, skipped, errors, "Mock ingestion feed completed successfully.")
        except Exception as e:
            errors += 1
            await self.complete_ingestion_run(run, "FAILED", seen, inserted, updated, skipped, errors, f"Failure in mock ingestion: {e}")
            raise e

        # Note stubs for live downloading (NOT_YET_IMPLEMENTED)
        logger.info("TEMPORARY_ASSUMPTION: Live corporate filings scraper is NOT_YET_IMPLEMENTED.")
        return {
            "status": "COMPLETED",
            "seen": seen,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": errors
        }
