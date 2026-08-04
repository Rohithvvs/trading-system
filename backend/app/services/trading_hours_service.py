"""
Centralized Trading Hours & Market Calendar Service.

Single source of truth for:
- Market open/close times (NSE: 9:15 AM – 3:30 PM IST)
- Weekends
- Official NSE/BSE trading holidays

Used to decide whether paper (and future live) orders execute immediately
or remain PENDING_MARKET_OPEN until the next session.

Orders may be *accepted* 24x7; execution is gated by is_market_open().
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional, Set
from zoneinfo import ZoneInfo

from ..config import settings
from ..utils import get_logger

logger = get_logger("app.trading_hours")

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 30

OPEN_TIME = time(MARKET_OPEN_HOUR, MARKET_OPEN_MIN)
CLOSE_TIME = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MIN)


class TradingHoursService:
    """Market calendar checks. Safe to instantiate multiple times (holidays cached on class)."""

    _holiday_cache: dict[str, Set[str]] = {}
    _holidays_loaded = False

    def __init__(self) -> None:
        self._load_holidays()

    def _get_holidays_file(self) -> Path:
        root = getattr(settings, "ROOT_DIR", None)
        if root is not None:
            candidate = Path(root) / "backend" / "data" / "nse_trading_holidays.json"
            if candidate.exists():
                return candidate
        # backend/app/services -> backend/data
        return Path(__file__).resolve().parents[2] / "data" / "nse_trading_holidays.json"

    def _load_holidays(self) -> None:
        if TradingHoursService._holidays_loaded:
            return
        try:
            holidays_path = self._get_holidays_file()
            if holidays_path.exists():
                with holidays_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    holidays = data.get("holidays", {})
                    TradingHoursService._holiday_cache = {
                        year: set(dates) for year, dates in holidays.items()
                    }
                    logger.info(
                        "Loaded NSE trading holidays for years: %s",
                        list(TradingHoursService._holiday_cache.keys()),
                    )
            else:
                logger.warning(
                    "NSE holidays file not found at %s. Only weekend checks will apply.",
                    holidays_path,
                )
                TradingHoursService._holiday_cache = {}
        except Exception as exc:
            logger.exception("Failed to load NSE holiday calendar: %s", exc)
            TradingHoursService._holiday_cache = {}
        finally:
            TradingHoursService._holidays_loaded = True

    def now_ist(self) -> datetime:
        return datetime.now(IST)

    def _to_ist(self, dt: Optional[datetime] = None) -> datetime:
        if dt is None:
            return self.now_ist()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(IST)
        return dt.astimezone(IST)

    def _to_ist_date(self, dt: Optional[datetime] = None) -> date:
        return self._to_ist(dt).date()

    def _to_ist_time(self, dt: Optional[datetime] = None) -> time:
        return self._to_ist(dt).time()

    def is_weekend(self, dt: Optional[datetime] = None) -> bool:
        return self._to_ist_date(dt).weekday() >= 5

    def is_nse_holiday(self, dt: Optional[datetime] = None) -> bool:
        d = self._to_ist_date(dt)
        holiday_set = TradingHoursService._holiday_cache.get(str(d.year), set())
        return d.isoformat() in holiday_set

    def is_trading_day(self, dt: Optional[datetime] = None) -> bool:
        return not (self.is_weekend(dt) or self.is_nse_holiday(dt))

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """True only during official market hours on a trading day (inclusive close)."""
        if not self.is_trading_day(dt):
            return False
        t = self._to_ist_time(dt)
        return OPEN_TIME <= t <= CLOSE_TIME

    def get_next_market_open(self, dt: Optional[datetime] = None) -> datetime:
        """Next 09:15 IST session open on a trading day (aware IST)."""
        ist_now = self._to_ist(dt)
        candidate = ist_now.replace(
            hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
        )
        # If already past today's open (or not a trading day), advance day-by-day
        if not self.is_trading_day(ist_now) or ist_now >= candidate:
            candidate = (ist_now + timedelta(days=1)).replace(
                hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
            )
        while not self.is_trading_day(candidate):
            candidate = (candidate + timedelta(days=1)).replace(
                hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
            )
        return candidate

    def get_market_status(self, dt: Optional[datetime] = None) -> dict:
        """Rich status for UI, diagnostics, and order scheduling."""
        ist_now = self._to_ist(dt)
        open_time = ist_now.replace(
            hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
        )
        close_time = ist_now.replace(
            hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0, microsecond=0
        )

        is_open = self.is_market_open(ist_now)
        is_trading = self.is_trading_day(ist_now)

        if self.is_weekend(ist_now):
            status = "WEEKEND"
            reason = "Weekend"
        elif self.is_nse_holiday(ist_now):
            status = "HOLIDAY"
            reason = "Official NSE/BSE trading holiday"
        elif not is_trading:
            status = "CLOSED"
            reason = "Non-trading day"
        elif ist_now.time() < OPEN_TIME:
            status = "PRE_OPEN"
            reason = "Before market open"
        elif ist_now.time() > CLOSE_TIME:
            status = "CLOSED"
            reason = "After market close"
        else:
            status = "OPEN"
            reason = "Market open"

        next_open = None if is_open else self.get_next_market_open(ist_now)

        return {
            "is_open": is_open,
            "is_trading_day": is_trading,
            "status": status,
            "reason": reason,
            "current_ist": ist_now.isoformat(),
            "open_time": open_time.isoformat(),
            "close_time": close_time.isoformat(),
            "next_open_ist": next_open.isoformat() if next_open else None,
            "session": status,
        }


# Convenience singleton
trading_hours = TradingHoursService()


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Module-level helper used by order/engine paths."""
    return trading_hours.is_market_open(dt)
