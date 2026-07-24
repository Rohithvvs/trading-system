"""
Canonical UTC datetime helpers for the backend.

Strategy
--------
* All backend storage and comparisons use **timezone-aware UTC**.
* Wall-clock "now" is always ``datetime.now(timezone.utc)`` — never
  ``datetime.utcnow()`` (naive) or bare ``datetime.now()`` (local).
* Naive datetimes from DB drivers / ISO strings without offsets are treated
  as UTC (legacy rows) via ``ensure_utc``.
* Local timezones (e.g. Asia/Kolkata / IST) are used only for display or
  market-session logic — never for duration arithmetic against UTC stamps.

Do not ``import datetime`` as a module alias inside functions that also use
``from datetime import datetime`` at module scope; that shadows the class and
causes UnboundLocalError.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")

DateTimeLike = Union[datetime, str, date, None]


def utc_now(*_args: object, **_kwargs: object) -> datetime:
    """Current time as a timezone-aware UTC datetime.

    Accepts optional unused args so this callable is safe as a SQLAlchemy
    ``Column(default=utc_now)`` / ``onupdate=utc_now`` target (SQLAlchemy may
    invoke defaults with an ExecutionContext).
    """
    return datetime.now(UTC)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to timezone-aware UTC.

    * ``None`` → ``None``
    * naive → assumed UTC (``replace(tzinfo=UTC)``)
    * aware → converted with ``astimezone(UTC)``
    """
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        raise TypeError(f"ensure_utc expected datetime, got {type(dt)!r}")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_utc(value: DateTimeLike) -> Optional[datetime]:
    """Parse ISO strings / datetimes / dates into aware UTC.

    Accepts:
    * ``datetime`` — normalized via ``ensure_utc``
    * ``date`` (not datetime) — midnight UTC that day
    * ISO-8601 ``str`` (handles trailing ``Z``)
    * ``None`` → ``None``
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # fromisoformat does not accept trailing Z in older Python; normalize.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return ensure_utc(datetime.fromisoformat(text))
    raise TypeError(f"parse_utc cannot parse {type(value)!r}")


def minutes_between(later: datetime, earlier: datetime) -> float:
    """Elapsed minutes between two datetimes (UTC-normalized).

    Both sides are forced to aware UTC before subtraction so naive/aware
    mixtures never raise TypeError.
    """
    later_utc = ensure_utc(later)
    earlier_utc = ensure_utc(earlier)
    if later_utc is None or earlier_utc is None:
        raise ValueError("minutes_between requires two non-None datetimes")
    return (later_utc - earlier_utc).total_seconds() / 60.0


def age_minutes(since: Optional[datetime], *, now: Optional[datetime] = None) -> float:
    """Minutes elapsed from ``since`` until ``now`` (default: utc_now).

    Returns ``0.0`` when ``since`` is missing.
    """
    if since is None:
        return 0.0
    return minutes_between(now or utc_now(), since)


def to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serialize a datetime as ISO-8601 in UTC (or None)."""
    normalized = ensure_utc(dt)
    if normalized is None:
        return None
    return normalized.isoformat()


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a datetime to Asia/Kolkata for display / session checks."""
    normalized = ensure_utc(dt)
    if normalized is None:
        return None
    return normalized.astimezone(IST)


def ist_now() -> datetime:
    """Current wall clock in Asia/Kolkata (aware)."""
    return utc_now().astimezone(IST)


__all__ = [
    "UTC",
    "IST",
    "utc_now",
    "ensure_utc",
    "parse_utc",
    "minutes_between",
    "age_minutes",
    "to_iso_utc",
    "to_ist",
    "ist_now",
    "timedelta",
    "datetime",
    "timezone",
]
