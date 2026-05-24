"""ohlcv_store.py — DEPRECATED. Use candle_store.py instead."""

import warnings


warnings.warn(
    "ohlcv_store is deprecated. Import from candle_store instead.",
    DeprecationWarning,
    stacklevel=2,
)
