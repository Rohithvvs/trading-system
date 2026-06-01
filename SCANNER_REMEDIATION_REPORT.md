# Scanner Remediation Report

## Objective
Implement Option C from `SCANNER_CROSS_LOOP_REMEDIATION_PLAN.md` to resolve the cross-loop DB access crash (`RuntimeError: Task got Future attached to a different loop`) while preserving the scanner's existing business logic, validation logic, and market data persistence architecture.

## Implementation Details

### 1. Refactored Network I/O to be Purely Stateless
- **File Modified:** `backend/app/services/fyers_service.py`
- **Changes Made:** Refactored `fetch_incremental_ohlcv()` to remove all dependencies on the `candle_store` and SQLAlchemy `_run_sync` DB connections. The method now evaluates the cache state (`cached_candles`) passed dynamically from the `ScreenerService` and performs a pure stateless HTTP fetch directly from the FYERS API via `run_in_executor`.
- **Result:** Thread workers are now **strictly** restricted to performing network I/O, completely eliminating the cross-event-loop boundary violation.

### 2. Upgraded Database Writes to Native Async
- **File Modified:** `backend/app/services/market_data_service.py`
- **Changes Made:** Upgraded the synchronous `upsert_candles` method to a native `async def` method. This eliminated the previous brittle `loop.create_task` and `asyncio.run(self._upsert_chunk(...))` fallback patterns which were heavily prone to leaking connection context. 
- **Result:** Database writes now securely await the underlying chunking logic within the boundaries of the primary application event loop without bridging.

### 3. Eliminated `run_in_executor` for Fast Local DB I/O
- **File Modified:** `backend/app/services/screener_service.py`
- **Changes Made:** Updated `ScreenerService` to `await md_service.upsert_candles(...)` natively on the main event loop instead of dispatching the write to `self.fyers_service._network_pool` using `run_in_executor`. 
- **Result:** Eliminates unnecessary thread-pool context switches and guarantees safe memory management with the main `asyncpg` engine pool.

## Validation Status
- The scanner execution architecture has successfully implemented strict boundaries between the async main loop (database operations) and threaded background pools (network fetch operations).
- The cross-loop `asyncpg` context leak has been resolved without requiring changes to business logic or database structure.
