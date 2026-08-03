"""Map platform market regime / permission signals to RE-001 buckets."""

from __future__ import annotations

from typing import Any


def map_market_regime(
    market_regime: Any | None = None,
    *,
    market_state: str | None = None,
    trend_state: str | None = None,
    new_entry_allowed: bool | None = None,
    feat004_regime: str | None = None,
) -> str:
    """Return Bull | Sideways | Bear | UNKNOWN."""
    state = market_state
    trend = trend_state
    entry_ok = new_entry_allowed
    f4 = feat004_regime

    if market_regime is not None:
        state = state or getattr(market_regime, "market_state", None) or (
            market_regime.get("market_state") if isinstance(market_regime, dict) else None
        )
        trend = trend or getattr(market_regime, "trend_state", None) or (
            market_regime.get("trend_state") if isinstance(market_regime, dict) else None
        )
        if entry_ok is None:
            entry_ok = getattr(market_regime, "new_entry_allowed", None)
            if entry_ok is None and isinstance(market_regime, dict):
                entry_ok = market_regime.get("new_entry_allowed")

    s = str(state or "").strip().upper()
    t = str(trend or "").strip().upper()
    f = str(f4 or "").strip().upper()

    if not s and not t and not f and entry_ok is None:
        return "UNKNOWN"

    # Explicit unfavorable / defensive
    if s in {"DEFENSIVE", "HIGHRISK", "HIGH_RISK", "BEAR", "BEARISH"}:
        return "Bear"
    if f in {"DEF", "DEFENSIVE", "ABS", "ABSTAIN"}:
        return "Bear"
    if entry_ok is False:
        return "Bear"
    if t in {"BEARISH"}:
        return "Bear"

    # Favorable / bullish
    if s in {"FAVORABLE", "BULL", "BULLISH"}:
        return "Bull"
    if f in {"FAV", "FAVORABLE"}:
        return "Bull"
    if t in {"BULLISH"} and entry_ok is not False:
        return "Bull"

    # Cautious / mixed / neutral
    if s in {"CAUTIOUS", "NEUTRAL", "MIXED", "SIDEWAYS"}:
        return "Sideways"
    if f in {"CAU", "CAUTIOUS", "NEU", "NEUTRAL"}:
        return "Sideways"

    if s or t or f:
        return "Sideways"
    return "UNKNOWN"


def is_regime_usable(bucket: str) -> bool:
    return bucket in {"Bull", "Sideways", "Bear"}
