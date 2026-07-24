"""Timezone-safe datetime helpers — unit tests for scheduler-critical paths."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.datetime_utils import (
    UTC,
    age_minutes,
    ensure_utc,
    ist_now,
    minutes_between,
    parse_utc,
    to_iso_utc,
    to_ist,
    utc_now,
)


def test_utc_now_is_aware_utc():
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ensure_utc_naive_assumed_utc():
    naive = datetime(2026, 3, 15, 10, 30, 0)
    aware = ensure_utc(naive)
    assert aware is not None
    assert aware.tzinfo == UTC
    assert aware.year == 2026 and aware.hour == 10


def test_ensure_utc_converts_offset():
    # 15:30 IST == 10:00 UTC
    ist = datetime(2026, 3, 15, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    utc = ensure_utc(ist)
    assert utc is not None
    assert utc.hour == 10
    assert utc.minute == 0
    assert utc.utcoffset() == timedelta(0)


def test_ensure_utc_none():
    assert ensure_utc(None) is None


def test_parse_utc_iso_z():
    dt = parse_utc("2026-03-15T10:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 10


def test_parse_utc_iso_offset():
    dt = parse_utc("2026-03-15T15:30:00+05:30")
    assert dt is not None
    assert dt.hour == 10  # normalized to UTC


def test_parse_utc_naive_iso_treated_as_utc():
    dt = parse_utc("2026-03-15T10:00:00")
    assert dt is not None
    assert dt.tzinfo == UTC


def test_minutes_between_aware_and_naive():
    """Regression: aware - naive must not TypeError."""
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
    earlier_naive = datetime(2026, 3, 15, 11, 0, 0)  # no tzinfo
    mins = minutes_between(now, earlier_naive)
    assert mins == pytest.approx(60.0)


def test_minutes_between_does_not_strip_tz():
    """Regression for SCAN_ENVIRONMENT bug: never strip tzinfo before subtract."""
    last_scan = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
    now = datetime(2026, 3, 15, 10, 45, 0, tzinfo=UTC)
    # Previous bug: now - last_scan.replace(tzinfo=None) raised TypeError
    mins = minutes_between(now, last_scan)
    assert mins == pytest.approx(45.0)


def test_age_minutes_from_token_saved():
    saved = utc_now() - timedelta(minutes=37)
    age = age_minutes(saved)
    assert 36.0 <= age <= 38.0


def test_age_minutes_missing_token():
    assert age_minutes(None) == 0.0


def test_to_iso_utc_roundtrip():
    original = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
    iso = to_iso_utc(original)
    assert iso is not None
    back = parse_utc(iso)
    assert back == original


def test_ist_display_conversion():
    utc = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
    local = to_ist(utc)
    assert local is not None
    assert local.hour == 15  # IST = UTC+5:30
    assert local.minute == 30


def test_ist_now_is_aware():
    local = ist_now()
    assert local.tzinfo is not None
    assert local.utcoffset() == timedelta(hours=5, minutes=30)


def test_scheduler_token_age_formula():
    """Mirrors automated_screening_job token_age calculation."""
    token_saved = datetime(2026, 3, 15, 3, 30, 0)  # naive DB row
    now = datetime(2026, 3, 15, 4, 0, 0, tzinfo=UTC)
    age = age_minutes(ensure_utc(token_saved), now=now)
    assert age == pytest.approx(30.0)


def test_no_unboundlocal_pattern_simulation():
    """Document the fixed pattern: never re-import datetime inside a function
    that uses `from datetime import datetime` at module scope.
    """
    # This is the correct usage (class from module-level import / helpers)
    assert isinstance(utc_now(), datetime)
    assert (utc_now() - ensure_utc(datetime(2020, 1, 1))).total_seconds() > 0
