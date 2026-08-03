"""Regime strategy priority tables (RE-001 Doc 02 / US4)."""

from __future__ import annotations

# Primary families
PRIMARY_FAMILIES = (
    "Trend Following",
    "Pullback Continuation",
    "Breakout Continuation",
    "Momentum Continuation",
)

# Priority order by regime (first = highest priority)
REGIME_PRIMARY_PRIORITY: dict[str, list[str]] = {
    "Bull": [
        "Trend Following",
        "Pullback Continuation",
        "Momentum Continuation",
        "Breakout Continuation",
    ],
    "Sideways": [
        "Breakout Continuation",
        "Trend Following",
        "Momentum Continuation",
        "Pullback Continuation",
    ],
    "Bear": [
        "Trend Following",  # only exceptional RS leaders activate
        "Momentum Continuation",
        "Breakout Continuation",
        "Pullback Continuation",
    ],
}

SIDEWAYS_STRICT_PULLBACK = True
BEAR_MINIMAL_PARTICIPATION = True
