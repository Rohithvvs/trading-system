"""ohlcv_store.py — DEPRECATED. Use candle_store.py instead."""

import warnings

from .candle_store import (
    init_db,
    store_candles,
    save_candles,
    load_candles,
    is_cache_fresh,
    get_last_stored_date,
    get_candle_count,
    update_ltp,
    get_ltp,
    get_all_cached_symbols,
)

warnings.warn(
    "ohlcv_store is deprecated. Import from candle_store instead.",
    DeprecationWarning,
    stacklevel=2,
)
