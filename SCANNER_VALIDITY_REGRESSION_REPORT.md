# Scanner Data Validity Regression Audit

## Problem Statement
The dashboard reports:
* **Total scanned:** 755
* **Data valid:** 1

Historically, the scanner produced hundreds of valid symbols.

## Elimination Trace

**755 symbols**
↓
**755 symbols initiated data fetch**
*(754 symbols crashed during incremental fetching in the thread pool and returned `[]`)*
↓
**1 candle validation success**
*(754 symbols rejected: `len(candles) < 220`. The 754 symbols had 0 candles returned because the data fetch crashed.)*
↓
**1 indicator success**
*(0 rejected at this stage)*
↓
**1 strategy candidates**
*(0 rejected at this stage)*

---

## Root Cause Analysis

### Final Status
**ROOT_CAUSE_IDENTIFIED**

### Identify
1. **Symbols failing data fetch:** 754 symbols failed silently during incremental fetching.
2. **Symbols failing candle count validation:** 754 symbols (the same ones that failed fetch) were rejected here because their candle count was 0 (well below the `MINIMUM_SWING_CANDLES` of 220).
3. **Symbols failing OHLCV validation:** 0 (failed at the previous step).
4. **Symbols failing persistence retrieval:** 754 symbols failed to persist/retrieve because of a cross-loop database engine crash.
5. **Symbols failing indicator warmup requirements:** 0
6. **Symbols failing strategy rules:** 0

### Detailed Explanation of the Regression
The regression is caused by a **cross-event-loop database engine crash** in the `fetch_incremental_ohlcv` pipeline.

1. `ScreenerService` uses `asyncio.get_running_loop().run_in_executor()` to run `fetch_incremental_ohlcv` in a background thread pool to parallelize network I/O.
2. Inside `fetch_incremental_ohlcv`, the script calls `candle_store.get_candle_count(symbol, '1D')` and `candle_store.store_candles()` using a helper function `_run_sync()`.
3. `_run_sync()` uses `asyncio.run(coro)`, which spawns a **new** event loop for the thread.
4. `candle_store` attempts to use `AsyncSessionLocal()`, which relies on the global SQLAlchemy `asyncpg` engine.
5. Because the `asyncpg` engine was initialized on the **main** application event loop, accessing it from the new thread-specific event loop causes a severe crash:
   ```
   RuntimeError: Task <Task pending> got Future <Future pending> attached to a different loop
   ```
6. The crash cascades to the `yfinance` fallback, which also attempts to use `store_candles()` and fails for the exact same reason.
7. The unhandled network/DB exceptions are caught by `ScreenerService.process_symbol()`, which gracefully logs the error and returns an empty list `[]` for the symbol's candles.
8. The validation pipeline then rejects all 754 symbols because `len([]) < 220`.

Only 1 symbol successfully bypassed this (likely a heartbeat symbol or one that was perfectly fresh and did not trigger the incremental network fetch).
