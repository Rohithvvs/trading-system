"""Candle Validation Engine for Authoritative Candle Store (Sprint 4).

Centralized validation logic for OHLCV candle arrays:
- Normalizes resolution strings into canonical formats.
- Enforces OHLC price consistency (High >= max(Open, Close), Low <= min(Open, Close)).
- Ensures timestamp monotonicity (strictly increasing).
- Validates non-negative volume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import logging

from ..schemas.analysis import OHLCVPoint

logger = logging.getLogger(__name__)

# Canonical resolution mappings
RESOLUTION_MAP = {
    "d": "1D",
    "1d": "1D",
    "day": "1D",
    "daily": "1D",
    "1": "1m",
    "1m": "1m",
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
    "30": "30m",
    "30m": "30m",
    "60": "60m",
    "60m": "60m",
    "1h": "60m",
}


def normalize_resolution(resolution: str) -> str:
    """Normalize resolution strings into canonical form (e.g. '1D', '5m', '15m')."""
    if not resolution:
        return "1D"
    cleaned = resolution.strip().lower()
    return RESOLUTION_MAP.get(cleaned, resolution.strip())


def validate_ohlcv_point(point: OHLCVPoint | dict[str, Any]) -> OHLCVPoint:
    """Validate a single OHLCV candle point and return a clean OHLCVPoint instance.

    Raises ValueError when timestamp is missing/invalid (audit L1).
    """
    if isinstance(point, dict):
        ts = point.get("timestamp") or point.get("date")
        if ts is None:
            raise ValueError("OHLCV point missing timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if not isinstance(ts, datetime):
            raise ValueError(f"OHLCV timestamp has unsupported type: {type(ts)!r}")
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        p_open = Decimal(str(point.get("open", 0)))
        p_high = Decimal(str(point.get("high", 0)))
        p_low = Decimal(str(point.get("low", 0)))
        p_close = Decimal(str(point.get("close", 0)))
        p_vol = Decimal(str(point.get("volume", 0)))
        validated = OHLCVPoint(
            timestamp=ts,
            open=p_open,
            high=p_high,
            low=p_low,
            close=p_close,
            volume=p_vol,
        )
    else:
        validated = point
        if validated.timestamp is None:
            raise ValueError("OHLCV point missing timestamp")
        if validated.timestamp.tzinfo is None:
            validated = validated.model_copy(
                update={"timestamp": validated.timestamp.replace(tzinfo=timezone.utc)}
            )

    # OHLC Logic validation
    max_oc = max(validated.open, validated.close)
    min_oc = min(validated.open, validated.close)

    if validated.high < max_oc:
        logger.warning(
            "Candle High (%.4f) less than max(Open, Close) (%.4f) at %s; adjusting High",
            validated.high,
            max_oc,
            validated.timestamp,
        )
        validated = validated.model_copy(update={"high": max_oc})

    if validated.low > min_oc:
        logger.warning(
            "Candle Low (%.4f) greater than min(Open, Close) (%.4f) at %s; adjusting Low",
            validated.low,
            min_oc,
            validated.timestamp,
        )
        validated = validated.model_copy(update={"low": min_oc})

    if validated.volume < Decimal(0):
        validated = validated.model_copy(update={"volume": Decimal(0)})

    return validated


def validate_candle_series(candles: list[OHLCVPoint | dict[str, Any]]) -> list[OHLCVPoint]:
    """Validate and sort a list of OHLCV candles, enforcing timestamp monotonicity.

    Invalid points are skipped (logged) rather than failing the whole series.
    Duplicate timestamps keep the last occurrence (O(n) via map, then sort).
    """
    if not candles:
        return []

    validated_list: list[OHLCVPoint] = []
    for c in candles:
        try:
            validated_list.append(validate_ohlcv_point(c))
        except Exception as exc:
            logger.warning("Skipping invalid OHLCV point during series validation: %s", exc)

    # Single-pass dedupe preserving last value per timestamp
    by_ts: dict[datetime, OHLCVPoint] = {}
    for c in validated_list:
        by_ts[c.timestamp] = c

    return sorted(by_ts.values(), key=lambda c: c.timestamp)
