"""
Centralized Trading Hours & Market Calendar Service.

This is the SINGLE source of truth for:
- Market open/close times (NSE: 9:15 AM – 3:30 PM IST)
- Weekends
- Official NSE/BSE trading holidays

Used to gate ALL Buy Order placement for both Paper Trading and (future) Live Trading.
No duplicate logic should exist elsewhere for buy order eligibility.

Update the holiday JSON data file annually from the official exchange calendars.
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


class MarketClosedError(Exception):
    """Raised when attempting to place a Buy order outside market hours / on holidays / weekends."""

    def __init__(self, message: str, reason: str = "MARKET_CLOSED"):
        super().__init__(message)
        self.reason = reason
        self.user_message = message


class TradingHoursService:
    """Singleton-style service for market calendar checks. Safe to instantiate multiple times."""

    _holiday_cache: dict[str, Set[str]] = {}
    _holidays_loaded = False

    def __init__(self) -> None:
        self._load_holidays()

    def _get_holidays_file(self) -> Path:
        # Prefer backend/data relative to project
        root = getattr(settings, "ROOT_DIR", Path(__file__).resolve().parents[3])
        candidate = root / "backend" / "data" / "nse_trading_holidays.json"
        if candidate.exists():
            return candidate
        # Fallback for different layouts
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
                    # Normalize to sets of 'YYYY-MM-DD'
                    TradingHoursService._holiday_cache = {
                        year: set(dates) for year, dates in holidays.items()
                    }
                    logger.info("Loaded NSE trading holidays for years: %s", list(TradingHoursService._holiday_cache.keys()))
            else:
                logger.warning("NSE holidays file not found at %s. Only weekend checks will apply.", holidays_path)
                TradingHoursService._holiday_cache = {}
        except Exception as exc:
            logger.exception("Failed to load NSE holiday calendar: %s", exc)
            TradingHoursService._holiday_cache = {}
        finally:
            TradingHoursService._holidays_loaded = True

    def now_ist(self) -> datetime:
        """Current time in IST (Asia/Kolkata)."""
        return datetime.now(IST)

    def _to_ist_date(self, dt: Optional[datetime] = None) -> date:
        if dt is None:
            dt = self.now_ist()
        if dt.tzinfo is None:
            # Assume UTC if naive, convert
            dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(IST)
        return dt.astimezone(IST).date()

    def _to_ist_time(self, dt: Optional[datetime] = None) -> time:
        if dt is None:
            dt = self.now_ist()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(IST)
        return dt.astimezone(IST).time()

    def is_weekend(self, dt: Optional[datetime] = None) -> bool:
        d = self._to_ist_date(dt)
        return d.weekday() >= 5  # Sat=5, Sun=6

    def is_nse_holiday(self, dt: Optional[datetime] = None) -> bool:
        d = self._to_ist_date(dt)
        year_str = str(d.year)
        holiday_set = TradingHoursService._holiday_cache.get(year_str, set())
        return d.isoformat() in holiday_set

    def is_trading_day(self, dt: Optional[datetime] = None) -> bool:
        """True if the day is a regular trading day (not weekend, not holiday)."""
        return not (self.is_weekend(dt) or self.is_nse_holiday(dt))

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """True only during official market hours on a trading day."""
        if not self.is_trading_day(dt):
            return False
        t = self._to_ist_time(dt)
        return OPEN_TIME <= t <= CLOSE_TIME

    def get_market_status(self, dt: Optional[datetime] = None) -> dict:
        """Return rich status for UI and diagnostics."""
        now = dt or self.now_ist()
        ist_now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        open_time = ist_now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0)
        close_time = ist_now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0, microsecond=0)

        is_open = self.is_market_open(ist_now)
        is_trading = self.is_trading_day(ist_now)

        if self.is_weekend(ist_now):
            status = "WEEKEND"
            reason = "Weekend"
        elif self.is_nse_holiday(ist_now):
            status = "HOLIDAY"
            reason = "Official NSE/BSE trading holiday"
        elif ist_now < open_time:
            status = "PRE_OPEN"
            reason = "Before market open"
        elif ist_now > close_time:
            status = "CLOSED"
            reason = "After market close"
        else:
            status = "OPEN"
            reason = "Market open"

        next_open = None
        if not is_open:
            # Compute next trading open (simple: next weekday not holiday)
            candidate = (ist_now + timedelta(days=1)).replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0)
            while not self.is_trading_day(candidate):
                candidate += timedelta(days=1)
            next_open = candidate.isoformat()

        return {
            "is_open": is_open,
            "is_trading_day": is_trading,
            "status": status,
            "reason": reason,
            "current_ist": ist_now.isoformat(),
            "open_time": open_time.isoformat(),
            "close_time": close_time.isoformat(),
            "next_open_ist": next_open,
        }

    def validate_can_place_buy_order(self, dt: Optional[datetime] = None) -> None:
        """
        Centralized guard for ALL Buy orders (Paper + Live).

        Raises MarketClosedError with user-friendly message if placement is not allowed.
        Call this at the beginning of every buy order path.
        """
        now = dt or self.now_ist()
        status = self.get_market_status(now)

        if status["is_open"]:
            return  # Allowed

        # Build exact messages per spec
        if self.is_weekend(now):
            msg = (
                "The stock market is closed today.\n"
                "Buy orders cannot be placed on weekends."
            )
            raise MarketClosedError(msg, reason="WEEKEND")
        elif self.is_nse_holiday(now):
            msg = (
                "Today is an official stock market holiday.\n"
                "Buy orders cannot be placed because the exchange is closed."
            )
            raise MarketClosedError(msg, reason="HOLIDAY")
        elif status["status"] == "PRE_OPEN":
            msg = (
                "Market has not opened yet.\n\n"
                "Buy orders can only be placed during market hours (9:15 AM – 3:30 PM IST).\n\n"
                "Please try again after the market opens."
            )
            raise MarketClosedError(msg, reason="BEFORE_OPEN")
        else:
            # After close
            msg = (
                "Market is closed.\n\n"
                "Buy orders cannot be placed after market hours.\n\n"
                "Please place your order during the next trading session."
            )
            raise MarketClosedError(msg, reason="AFTER_CLOSE")


# Convenience singleton for import sites that prefer not to instantiate
trading_hours = TradingHoursService()
