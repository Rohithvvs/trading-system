# PHASE E ASYNC BOUNDARY AUDIT

## 1. Orchestrator Agent Concurrency Violations

**Occurrences:**
*   `backend/app/agents/orchestrator_agent.py` (Line 90): `asyncio.run(prefetch_all())`
*   `backend/app/agents/orchestrator_agent.py` (Line 125): `items = asyncio.run(run_remaining_agents())`
*   `backend/app/agents/orchestrator_agent.py` (Line 487): `stock_id = asyncio.run(self._get_or_create_stock(symbol))`
*   `backend/app/agents/orchestrator_agent.py` (Lines 559, 561): `asyncio.run(_run_agents_concurrently())`
*   `backend/app/agents/orchestrator_agent.py` (Line 595): `asyncio.run(self._persist_analysis(...))`

**Analysis:**
*   **Call Chain:** FastAPI Route -> Orchestrator Thread Pool -> `asyncio.run(coroutine)` -> AsyncPG
*   **Execution Frequency:** High (Executes repeatedly during scanner and screener operations).
*   **Production Risk:** Creates transient event loops inside worker threads. Circumvents the global `AsyncSessionLocal` connection pool limits and leads to `RuntimeError: asyncio.run() cannot be called from a running event loop` if the orchestrator thread shares context with the main thread. 
*   **Determination:** Architectural Debt (Agents should be fully `async` native).
*   **Classification:** **UNSAFE**

---

## 2. FYERS Sync-Fallback Wrapper

**Occurrences:**
*   `backend/app/services/fyers_service.py` (Line 45): `return asyncio.run_coroutine_threadsafe(coro, main_loop).result()`
*   `backend/app/services/fyers_service.py` (Line 48): `return _SYNC_EXECUTOR.submit(asyncio.run, coro).result()`

**Analysis:**
*   **Call Chain:** Synchronous logic -> `_run_sync_fallback` -> Main Event Loop -> HTTP Request
*   **Execution Frequency:** High (Triggered on token refresh or when sync endpoints request market data).
*   **Production Risk:** Calling `.result()` on a threadsafe future blocks the invoking thread. If the invoking thread is part of a pool that the main event loop is awaiting, an unrecoverable circular deadlock occurs.
*   **Determination:** Unsafe Pattern
*   **Classification:** **UNSAFE**

---

## 3. Market Data Bulk Ingestion

**Occurrences:**
*   `backend/app/services/market_data_service.py` (Line 170): `asyncio.run_coroutine_threadsafe(self._upsert_chunk(...), main_loop)`
*   `backend/app/services/market_data_service.py` (Line 173): `asyncio.run(self._upsert_chunk(...))`

**Analysis:**
*   **Call Chain:** Historical data generator -> Thread -> `_upsert_chunk` -> Database Insert
*   **Execution Frequency:** Medium (Triggered during backfills and daily candle hydration).
*   **Production Risk:** Using `asyncio.run` inside a bulk loop creates massive overhead and connection pool exhaustion. `run_coroutine_threadsafe` without bounds can overwhelm the main loop with thousands of database insert tasks.
*   **Determination:** Architectural Debt
*   **Classification:** **UNSAFE**

---

## 4. Market Engine WebSocket Callbacks

**Occurrences:**
*   `backend/app/services/market_engine_service.py` (Line 41): `asyncio.run_coroutine_threadsafe(self._on_tick(symbol, price), self._loop)`
*   `backend/app/services/market_engine_service.py` (Line 45): `asyncio.run_coroutine_threadsafe(self._on_feed_error(message), self._loop)`
*   `backend/app/services/market_engine_service.py` (Line 49): `asyncio.run_coroutine_threadsafe(self._on_connection_change(connected), self._loop)`

**Analysis:**
*   **Call Chain:** FYERS WebSocket Client (C-Extension / Sync Thread) -> Callback Event -> `run_coroutine_threadsafe` -> Main Event Loop
*   **Execution Frequency:** Extremely High (Potentially thousands of ticks per second during market open).
*   **Production Risk:** This pushes tasks to the main event loop queue unboundedly. While a necessary pattern, the lack of `asyncio.Queue` backpressure means a burst of market data could cause severe memory leaks or event loop starvation, crashing the API.
*   **Determination:** Required Bridge
*   **Classification:** **QUESTIONABLE**

---

## 5. Paper Trading Synchronous Price Fetch

**Occurrences:**
*   `backend/app/services/paper_trading_service.py` (Line 1078): `future = asyncio.run_coroutine_threadsafe(self.fyers_service.fetch_ltp(symbol), main_event_loop)`

**Analysis:**
*   **Call Chain:** Order Processing -> `fetch_ltp` -> Event Loop -> HTTP Fetch
*   **Execution Frequency:** High (Whenever an order requires immediate price validation outside of the cache).
*   **Production Risk:** Blocks the order execution thread while waiting for a remote HTTP call scheduled on the main event loop. Directly impacts order execution latency and risks the same circular deadlocks observed in `fyers_service.py`.
*   **Determination:** Architectural Debt / Unsafe Pattern
*   **Classification:** **UNSAFE**

---

## FINAL CONCLUSION

**BLOCKED_WITH_FINDINGS**

The system exhibits pervasive async/sync boundary violations. The widespread use of `asyncio.run` inside threads and `.result()` blocking calls on `run_coroutine_threadsafe` introduces massive risks of thread starvation, unrecoverable deadlocks, and connection pool exhaustion. The codebase is heavily burdened with Architectural Debt, using these unsafe primitives as workarounds instead of natively propagating `async/await` up the call stack. The application cannot safely process real-time market data or concurrent trading load until these boundaries are refactored to be fully asynchronous.
