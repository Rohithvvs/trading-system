# B + C + E FINAL AUDIT REPORT

## 1. Alembic Recovery Audit
* **Severity:** Low
* **Root Cause:** Migration graph contains minor disconnected history artifacts from previous SQLite models.
* **Impact:** No immediate production impact, but could complicate future downgrades.
* **Evidence:** Manual inspection of `alembic/versions`.
* **Recommended Remediation:** Rebasing migration history to a single PostgreSQL head and removing SQLite-specific branches.

## 2. Cache Consolidation Audit
* **Severity:** Medium
* **Root Cause:** Dual usage of application-memory dict caches and PostgreSQL `ltp_cache` tables without strict invalidation boundaries.
* **Impact:** Potential for stale data delivery if the in-memory cache desynchronizes from the database.
* **Evidence:** `paper_trading.py` and `market_data_service.py` exhibit overlapping cache layers.
* **Recommended Remediation:** Consolidate to a single cache backend (Redis) or strictly use PostgreSQL with pub/sub cache invalidation.

## 3. PostgreSQL Cutover Audit
* **Severity:** Critical
* **Root Cause:** Incomplete removal of SQLite transaction logging.
* **Impact:** Split-brain database scenario. Trades are executing, but ledger entries are being written to SQLite instead of PostgreSQL, corrupting the central source of truth.
* **Evidence:** `backend/app/services/paper_trading_service.py` Lines 233, 273, 677, 977 explicitly execute SQLite insertions for transactions (`Failed to write BUY transaction to SQLite`).
* **Recommended Remediation:** Purge all `sqlite3` driver usage and routing. Migrate all transaction and ledger queries to `AsyncSessionLocal` against PostgreSQL.

## 4. Async Concurrency Audit
* **Severity:** Critical
* **Root Cause:** Direct invocation of synchronous blocking event loop runners inside an already executing asynchronous context.
* **Impact:** Event loop blocking, deadlocks, and complete thread starvation during high market volatility.
* **Evidence:** Multiple instances of `asyncio.run()` found in `orchestrator_agent.py` and `market_data_service.py`. `fyers_service.py` utilizes unsafe `asyncio.run_coroutine_threadsafe` combinations.
* **Recommended Remediation:** Remove all `asyncio.run()` calls from the application runtime. Use `await` for coroutines naturally and leverage `asyncio.to_thread` only for strictly synchronous, non-IO bound external libraries.

## 5. Session & Connection Audit
* **Severity:** High
* **Root Cause:** Simultaneous usage of synchronous `SessionLocal` and asynchronous `AsyncSessionLocal`.
* **Impact:** Thread-pool exhaustion and potential database connection starvation, as synchronous sessions block worker threads holding database locks.
* **Evidence:** `backend/app/main.py` explicitly imports and uses `SessionLocal` context managers deep within async routing paths.
* **Recommended Remediation:** Completely deprecate and remove `SessionLocal` and `sync_engine`. Standardize entirely on `AsyncSessionLocal`.

## 6. Pool Forensics Audit
* **Severity:** High
* **Root Cause:** Synchronous operations executing while holding an async database transaction open.
* **Impact:** Elevated `idle in transaction` metrics, leading to rapid connection pool exhaustion under load.
* **Evidence:** Mixing `SessionLocal` within async endpoints.
* **Recommended Remediation:** Ensure transactions are committed or rolled back immediately after database operations complete, prior to executing long-running business logic or network calls.

## 7. Scanner Forensics Audit
* **Severity:** High
* **Root Cause:** Lack of distributed locking around the scanner execution scheduler.
* **Impact:** The same market symbols are scanned concurrently by different workers, creating redundant load and duplicate signals.
* **Evidence:** Threadsafe coroutine dispatches in `market_engine_service.py` without deduplication or symbol-level locking.
* **Recommended Remediation:** Implement a distributed lock (e.g., PostgreSQL advisory locks or Redis distributed locks) per symbol timeframe.

## 8. Market Data Persistence Audit
* **Severity:** Low
* **Root Cause:** Candles are persisting as expected, though bulk inserts occasionally trigger minor contention.
* **Impact:** Negligible performance hit during end-of-day backfills.
* **Evidence:** `test_backfill.py` and `market_data_service.py` operate successfully but without optimized `COPY` bulk operations.
* **Recommended Remediation:** Optimize bulk candle ingestion using AsyncPG's `copy_records_to_table`.

## 9. PostgreSQL Partition Audit
* **Severity:** Medium
* **Root Cause:** `market_data.candles` is configured for partitioning, but partition creation is not fully automated via Alembic triggers.
* **Impact:** Data will eventually spill into the default partition, causing massive query performance degradation over time.
* **Evidence:** Alembic history does not contain automated partition-generation functions for future months/years.
* **Recommended Remediation:** Implement `pg_cron` or a dedicated application lifecycle hook to preemptively create time-based partitions.

## 10. FYERS Integration Audit
* **Severity:** Medium
* **Root Cause:** Token refresh logic utilizes blocking network requests.
* **Impact:** Event loop latency spikes during access token regeneration.
* **Evidence:** `fyers_service.py` executes synchronous HTTP fallback logic.
* **Recommended Remediation:** Refactor the auth/token refresh flow to utilize `aiohttp` or `httpx` for fully asynchronous network requests.

## 11. WebSocket Audit
* **Severity:** Medium
* **Root Cause:** Connection state changes aggressively spawn unmanaged background tasks.
* **Impact:** Potential memory leaks and duplicate tick processing during network flapping.
* **Evidence:** `market_engine_service.py` spawns `_on_tick` via `run_coroutine_threadsafe` without bounding the task queue.
* **Recommended Remediation:** Implement bounded asyncio queues and dedicated consumer worker loops for processing websocket ticks.

## 12. Order Engine Audit
* **Severity:** Critical
* **Root Cause:** Funds checking and order creation are not wrapped in a strict serializable transaction or `SELECT ... FOR UPDATE` lock.
* **Impact:** Concurrency vulnerabilities allow race conditions where rapid, identical webhook callbacks could result in double fills or negative account balances.
* **Evidence:** `paper_trading_service.py` queries balance state without applying row-level read locks prior to position updates.
* **Recommended Remediation:** Apply `with_for_update()` on account balance queries during the `Funds Check` and `Fill Engine` execution phases.

## 13. Accounting Audit
* **Severity:** Critical
* **Root Cause:** Direct continuation of the PostgreSQL Cutover failure.
* **Impact:** The accounting equation `Starting Cash = Current Cash + Reserved Cash + Open Position Value + Realized PnL + Unrealized PnL + Transaction Ledger` cannot be satisfied.
* **Evidence:** SQLite ledger writes mean PostgreSQL balance tables are silently drifting.
* **Recommended Remediation:** Remediate Phase E PostgreSQL cutover. Ensure all transactions and balances live strictly in PostgreSQL.

## 14. Accounting Forensics Audit
* **Severity:** Critical
* **Root Cause:** Missing transaction rows in the primary database.
* **Impact:** 100% reconciliation is impossible. 
* **Evidence:** SQLite transaction log drift detected via code analysis (`paper_trading_service.py`).
* **Recommended Remediation:** Write a one-time migration script to extract SQLite ledger entries and replay them into PostgreSQL, then disable SQLite forever.

---

## 15. Phase F Readiness Evaluation

**STATUS:**  
**BLOCKED_WITH_FINDINGS**

**REASONING:**  
The system possesses multiple **Critical** and **High** severity vulnerabilities. The continued presence of SQLite (`paper_trading_service.py`), combined with severe concurrency violations (`asyncio.run` inside event loops) and lack of database row-level locking for the Order Engine, guarantees that the application will suffer data corruption, ledger drift, and deadlocks if subjected to real-world production load. The system is unequivocally not ready for Phase F. All Critical and High findings must be remediated prior to proceeding.
