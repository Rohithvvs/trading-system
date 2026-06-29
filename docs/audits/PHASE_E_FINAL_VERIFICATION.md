# PHASE E FINAL CRITICAL VERIFICATION

## 1. Transaction Boundary Verification

**Trace:** `place_order` → `_get_or_create_account` → `_try_fill_order` → position updates → ledger updates

*   **Transaction Start:**
    The transaction implicitly starts when `self.db` performs the first query inside `_get_or_create_account(for_update=True)`:
    ```python
    account = self.db.scalar(query)
    ```
*   **Transaction Commit:**
    Occurs at the end of `place_order` (lines 276-277 of `paper_trading_service.py`):
    ```python
        # Commit the order + position + account + transactions + notifications as one atomic unit
        try:
            self.db.commit()
    ```
*   **Transaction Rollback:**
    Occurs in the exception block immediately following the commit attempt (lines 278-281) and also during `IntegrityError` from an earlier `flush()` (lines 195-196):
    ```python
        except Exception:
            # Rollback to ensure the session is not left in a broken state
            try:
                self.db.rollback()
    ```

## 2. Row Lock Verification

**Usages of `with_for_update()`:**
1.  `backend/app/services/margin_engine.py` (lines 24, 47, 69, 95):
    ```python
    stmt = select(LiveAccount).where(LiveAccount.id == account_id).with_for_update()
    ```
2.  `backend/app/services/paper_trading_service.py` (line 425):
    ```python
    query = query.with_for_update()
    ```
3.  `backend/app/services/paper_trading_service.py` (line 886):
    ```python
    query = query.with_for_update()
    ```

**Determinations:**
*   **Account lock scope:** The account is locked aggressively at the beginning of flows like `place_order`, `auto_exit`, and `margin_engine` functions using `with_for_update()`.
*   **Position lock scope:** The position is locked explicitly only during `auto_exit()`. It is **NOT** locked explicitly in `_try_fill_order` or `place_order`.
*   **Order lock scope:** There are no row-level locks on orders.

**Answer: Can two concurrent fills modify the same position?**
**No, practically.** While `_try_fill_order` lacks a direct `.with_for_update()` on the `PaperPosition` query, the parent `PaperTradingAccount` is locked at the very beginning of the `place_order` transaction (`account = self._get_or_create_account(for_update=True)`). Because all positions belong to a specific account, this coarse-grained account lock acts as a serialization barrier for any concurrent operations affecting that account's positions in the same session. However, this is an inefficient locking pattern (locking the whole account for a single symbol's position fill) and could lead to lock contention, but it successfully prevents duplicate fills race conditions.

## 3. Async Boundary Verification

**Occurrences:**

1.  **File:** `backend/app/agents/orchestrator_agent.py`
    *   **Lines:** 90, 125, 487, 559, 561, 595
    *   **Purpose:** Attempting to bridge async code into sync functions or synchronous thread pools.
    *   **Execution Path:** Agent executions inside threads calling back into async code.
    *   **Classification:** **UNSAFE**
    *   **Justification:** Calling `asyncio.run()` inside a thread while the main event loop is running can cause fatal deadlocks, thread pool exhaustion, or `RuntimeError: asyncio.run() cannot be called from a running event loop`.

2.  **File:** `backend/app/services/fyers_service.py`
    *   **Lines:** 45, 48
    *   **Purpose:** `run_coroutine_threadsafe(coro, main_loop)` and `_SYNC_EXECUTOR.submit(asyncio.run, coro)`. Used to execute async token refresh or API logic from synchronous methods.
    *   **Execution Path:** Token expiration -> sync wrapper -> async execution.
    *   **Classification:** **UNSAFE**
    *   **Justification:** Mixing `run_coroutine_threadsafe` and `asyncio.run` through custom executors leads to hidden deadlocks. If the main loop awaits a synchronous function that in turn blocks waiting for `run_coroutine_threadsafe`, the event loop is blocked indefinitely.

3.  **File:** `backend/app/services/market_data_service.py`
    *   **Lines:** 170, 173
    *   **Purpose:** `asyncio.run_coroutine_threadsafe` and `asyncio.run` for upserting chunks of data.
    *   **Execution Path:** Background processing of downloaded market data chunks.
    *   **Classification:** **UNSAFE**
    *   **Justification:** Bypasses proper async scheduling, risking loop blockage and `RuntimeError`.

4.  **File:** `backend/app/services/market_engine_service.py`
    *   **Lines:** 41, 45, 49
    *   **Purpose:** `asyncio.run_coroutine_threadsafe` to dispatch websocket events (`_on_tick`, `_on_feed_error`) from the sync websocket callback thread.
    *   **Execution Path:** Websocket thread -> main event loop.
    *   **Classification:** **QUESTIONABLE**
    *   **Justification:** This is the standard way to bridge a synchronous thread (like a websocket client callback) to the asyncio event loop. However, without a bounded queue, a high volume of ticks can crash the event loop by submitting too many concurrent tasks.

5.  **File:** `backend/app/services/paper_trading_service.py`
    *   **Line:** 1078
    *   **Purpose:** `asyncio.run_coroutine_threadsafe(self.fyers_service.fetch_ltp(symbol), main_event_loop)`
    *   **Execution Path:** Sync order processing -> fetch live price.
    *   **Classification:** **UNSAFE**
    *   **Justification:** Sync order processing blocking to wait for an async HTTP request via threadsafe futures causes severe bottlenecking and thread locking.

## Final Status

**BLOCKED_WITH_FINDINGS**
