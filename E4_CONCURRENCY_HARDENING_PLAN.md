# PHASE E.4 CONCURRENCY HARDENING PLAN

## Objective
Eliminate thread pool starvation, request queue buildup, account lock bottlenecks, and connection pool pressure **without performing a full async rewrite**.

---

## Analysis of Bottlenecks

### 1. AnyIO Thread Pool & SessionLocal Usage
*   **Root Cause:** FastAPI executes synchronous `def` routes in the Starlette AnyIO thread pool (default size: 40). `Depends(get_sync_db)` checks out a `SessionLocal` connection for the duration of the request. When >30 concurrent requests arrive, the sync connection pool (30) is exhausted. The remaining threads block indefinitely in the SQLAlchemy pool queue, leaving 0 threads available to process the actual routes or other incoming requests.
*   **Impact:** Complete thread pool starvation and 100% request timeouts under burst load.
*   **Estimated Gain:** Immediate resolution of 10-second client timeouts; predictable degradation instead of total lockup.
*   **Implementation Complexity:** Low.

### 2. Account Row Locking (`_get_or_create_account`)
*   **Root Cause:** `place_order` applies a Python-level `threading.Lock` (`_account_creation_lock`) and a PostgreSQL `FOR UPDATE` row lock on the user's primary account at the very beginning of the request. The request then proceeds to make network calls to FYERS while holding these locks.
*   **Impact:** Strict linear serialization of all trading requests. 50 concurrent orders execute 1 by 1. The 50th order must wait for 49 previous network calls to complete, guaranteeing a client timeout.
*   **Estimated Gain:** 50x-100x increase in order placement throughput.
*   **Implementation Complexity:** Medium.

### 3. Market Data Fetch Path (`fetch_ltp` via `run_coroutine_threadsafe`)
*   **Root Cause:** Synchronous execution paths halt entirely via `.result(timeout=5)` to retrieve prices from the async main event loop. Because this occurs *while* holding the PostgreSQL `FOR UPDATE` lock, network latency directly dictates database contention.
*   **Impact:** Amplifies the duration of database locks by orders of magnitude (milliseconds vs. seconds).
*   **Estimated Gain:** Massive reduction in database lock contention and idle-in-transaction buildup.
*   **Implementation Complexity:** Low (Moving the fetch outside the lock boundary).

### 4. Scanner Execution Model
*   **Root Cause:** Lack of symbol-level deduplication. Multiple background workers or cron triggers can dispatch overlapping scans for the same symbols concurrently, compounding the thread pool and connection pool pressure.
*   **Impact:** Redundant API calls, redundant database writes, and artificial load generation.
*   **Estimated Gain:** 50%+ reduction in background CPU and I/O utilization during peak hours.
*   **Implementation Complexity:** Low.

---

## Implementation Phases

### E4.1 Quick Wins (Configuration Tuning)
*   **Action 1:** Synchronize the AnyIO thread pool and SQLAlchemy connection pool capacities.
    *   Set FastAPI `anyio` thread limiter to 100 workers.
    *   Set `sync_engine` pool size to `pool_size=80`, `max_overflow=20` (Total 100).
    *   Ensure 1:1 parity so an AnyIO thread never blocks waiting for a DB connection.
*   **Action 2:** Reduce the `.result(timeout=5)` in `_price_snapshot` to `timeout=2` to fail-fast during extreme FYERS API degradation.

### E4.2 Pool Hardening (Graceful Degradation)
*   **Action 1:** Implement a custom FastAPI middleware or dependency that uses an `asyncio.Semaphore` or token bucket to limit concurrent `/orders` requests. 
*   **Action 2:** If the concurrent request limit is breached, immediately return HTTP 429 (Too Many Requests) rather than queueing the request and starving the thread pool.

### E4.3 Lock Scope Optimization (The Core Fix)
*   **Action 1:** Remove the global Python `_account_creation_lock` from `_get_or_create_account`. It is an anti-pattern that defeats PostgreSQL's native concurrency controls.
*   **Action 2:** Shrink the `FOR UPDATE` lock scope. 
    *   Load the account *without* `for_update=True` at the start of `place_order`.
    *   Fetch the live price (`_price_snapshot`) and perform initial stateless validation.
    *   *Only* right before deducting cash and inserting the position (inside `_try_fill_order`), execute a fresh `SELECT ... FOR UPDATE` on the account, perform the math, and commit immediately.

### E4.4 Scanner Throughput Optimization
*   **Action 1:** Introduce a lightweight deduplication cache (using Python `dict` with TTL or an in-memory set) inside the scanner dispatcher.
*   **Action 2:** If `SCAN_IN_PROGRESS: {symbol}` exists, immediately drop or skip redundant scan requests.

### E4.5 Final Validation
*   **Action 1:** Re-run the Phase E Runtime Validation script (`runtime_validation.py`).
*   **Action 2:** Assert that 50 concurrent `MARKET BUY` orders complete with 0 timeouts and 0 thread starvation warnings.
*   **Action 3:** Validate that idle-in-transaction PostgreSQL metrics remain at 0 during scanner bursts.
