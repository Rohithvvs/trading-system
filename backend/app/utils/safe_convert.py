"""Safe numeric conversion utilities to prevent NaN/None crashes in production.

The root cause of the 'cannot convert float NaN to integer' production error:
FYERS API, yfinance, or database records can return NaN/None/inf for volume
or price fields. Calling int() on NaN raises ValueError. These helpers
log the bad value and return a safe default instead of crashing the scan.
"""
from __future__ import annotations

import math
import logging

logger = logging.getLogger("app.safe_convert")


def safe_int(value, default: int = 0, symbol: str = "", field: str = "") -> int:
    """Convert *value* to int safely. Returns *default* on NaN, None, or inf.

    Never raises. Logs the bad value for production diagnostics.
    """
    if value is None:
        logger.warning("SAFE_CONVERT | None→int | symbol=%s | field=%s | default=%s", symbol, field, default)
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        logger.warning("SAFE_CONVERT | unconvertible→int | symbol=%s | field=%s | value=%s", symbol, field, value)
        return default
    if math.isnan(f) or math.isinf(f):
        logger.warning("SAFE_CONVERT | NaN/inf→int | symbol=%s | field=%s | value=%s | default=%s", symbol, field, value, default)
        return default
    return int(f)


def safe_float(value, default: float = 0.0, symbol: str = "", field: str = "") -> float:
    """Convert *value* to float safely. Returns *default* on None.

    NaN and inf are returned as-is (they are valid float values that
    indicator libraries can handle), but None returns the default.
    """
    if value is None:
        logger.warning("SAFE_CONVERT | None→float | symbol=%s | field=%s | default=%s", symbol, field, default)
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        logger.warning("SAFE_CONVERT | unconvertible→float | symbol=%s | field=%s | value=%s", symbol, field, value)
        return default
    return f


def sanitize_volume(value, symbol: str = "") -> int:
    """Convert a raw volume value (possibly NaN/None/Decimal) to a safe int.

    Designed specifically for the volume column where NaN from FYERS or
    yfinance causes 'cannot convert float NaN to integer' in production.
    """
    return safe_int(value, default=0, symbol=symbol, field="volume")


def sanitize_ohlcv_row(row, symbol: str = "") -> dict:
    """Sanitize a raw OHLCV dict (from FYERS API or yfinance) before use.

    Returns a clean dict with safe numeric types. Logs any bad values.
    """
    return {
        "open": safe_float(row.get("open") or row.get("Open"), symbol=symbol, field="open"),
        "high": safe_float(row.get("high") or row.get("High"), symbol=symbol, field="high"),
        "low": safe_float(row.get("low") or row.get("Low"), symbol=symbol, field="low"),
        "close": safe_float(row.get("close") or row.get("Close"), symbol=symbol, field="close"),
        "volume": sanitize_volume(row.get("volume") or row.get("Volume"), symbol=symbol),
    }
