# Scanner Cross-Loop Remediation Plan

## Execution Trace Analysis

The severe regression (`RuntimeError: Task got Future attached to a different loop`) in the scanner is caused by a cross-event-loop boundary violation between Python's ThreadPoolExecutor and SQLAlchemy's `asyncpg` engine.

### 1. Identified Cross-Loop Boundaries
* `ScreenerService.process_symbol` (Main Loop) -> `run_in_executor` -> `fyers_service.fetch_incremental_ohlcv` (Thread Pool)
* `ScreenerService.process_symbol` (Main Loop) -> `run_in_executor` -> `market_data_service.upsert_candles` (Thread Pool)

### 2. Identified `asyncio.run` Usages
* `fyers_service._run_sync()`: Uses `asyncio.run_coroutine_threadsafe(coro).result()` or falls back to `asyncio.run(coro)` to execute asynchronous database functions from inside synchronous thread pools.
* `market_data_service.upsert_candles()`: Uses a `try/except RuntimeError` block to catch missing event loops in thread pools, falling back to `asyncio.run(self._upsert_chunk(...))`.

### 3. Identified Thread -> `asyncpg` Access Paths
* Thread Pool -> `fetch_incremental_ohlcv` -> `_run_sync` -> `asyncio.run` -> `candle_store` DB Queries -> `asyncpg` Engine (Bound to Main Loop) -> **CRASH**
* Thread Pool -> `md_service.upsert_candles` -> `asyncio.run` -> `_upsert_chunk` -> `asyncpg` Engine (Bound to Main Loop) -> **CRASH**

### 4. Identified `AsyncSessionLocal` Usages Inside Thread Pools
The following methods initialize an `AsyncSessionLocal` context while executing inside a thread pool's local event loop, leaking the main loop's connection pool:
* `candle_store.get_candle_count()`
* `candle_store.get_last_stored_date()`
* `candle_store.store_candles()`
* `market_data_service._upsert_chunk()`

---

## Remediation Options Evaluation

### Option A: Pure Async Scanner Pipeline
**Description:** Refactor the entire `fyers_service` to use purely asynchronous HTTP clients (like `aiohttp` or `httpx`), eliminating the need for `run_in_executor` entirely.
* **Complexity:** Very High
* **Risk:** High (Requires rewriting core FYERS SDK logic and authentication flows)
* **Performance Impact:** Excellent (Maximum concurrency, no thread pool starvation)
* **Migration Effort:** Massive
* **Production Safety:** Low during migration due to the extent of core changes.

### Option B: Dedicated Sync Persistence Layer
**Description:** Introduce a strictly synchronous SQLAlchemy `SessionLocal` alongside the `AsyncSessionLocal`. Map all thread-pool database operations to the sync engine using a blocking driver (e.g., `psycopg2`).
* **Complexity:** Medium
* **Risk:** Medium (Introduces dual connection pools which may exhaust Postgres connection limits; `max_connections` pressure)
* **Performance Impact:** Moderate (Thread blocking is acceptable since it's already in an executor)
* **Migration Effort:** Moderate (Requires duplicating DB access layers into sync/async variants)
* **Production Safety:** Moderate to High (A common pattern, but carries connection limit risks).

### Option C: Move DB Operations Outside Thread Workers
**Description:** Decouple network I/O from persistence. Thread pools should **only** perform synchronous FYERS API network requests. Database queries/writes are extracted to the main event loop and awaited directly.
* **Complexity:** Medium
* **Risk:** Low (Leaves FYERS SDK untouched; preserves async db architecture)
* **Performance Impact:** Positive (Prevents thread-pool starvation by moving fast DB I/O back to the highly concurrent main loop)
* **Migration Effort:** Moderate (Requires refactoring `fetch_incremental_ohlcv` to accept `db_count` and `last_date` as parameters rather than querying them internally, and refactoring `upsert_candles` to be fully async)
* **Production Safety:** Highest (Architecturally sound, strictly enforces async/sync boundaries).

### Option D: Producer/Consumer Architecture
**Description:** Offload the scanner to a dedicated worker queue (e.g., Celery/Redis). Workers perform the blocking network fetches and push payloads to a queue consumed by an async DB writer.
* **Complexity:** Very High
* **Risk:** High (Introduces new infrastructure components and state management)
* **Performance Impact:** High throughput, but adds latency overhead
* **Migration Effort:** Massive architectural rewrite
* **Production Safety:** High (long term) but extremely risky in the short term.

---

## Recommendation

**Option C (Move DB operations outside thread workers)** is strongly recommended. 

It specifically addresses the `RuntimeError` by strictly separating domains:
1. **Main Async Loop:** Exclusively handles all DB reads/writes (`AsyncSessionLocal`) and orchestration.
2. **Thread Pool (`run_in_executor`):** Exclusively handles synchronous FYERS API network calls, taking pre-fetched DB state as input and returning raw lists of OHLCV points to the main loop for persistence.

This prevents the cross-loop engine crash without requiring dual database connection pools or a complete rewrite of the API integrations.
