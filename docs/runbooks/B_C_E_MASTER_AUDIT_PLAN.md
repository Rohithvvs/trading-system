# B + C + E MASTER AUDIT PLAN

## ROLE ALIGNMENT
* Principal Trading Systems Architect
* PostgreSQL Reliability Engineer
* Async Python Concurrency Auditor
* Production Incident Investigator
* Market Data Architecture Reviewer
* Financial Systems Auditor

*Notice: This document represents a PLANNING PHASE ONLY. No code, configuration, or database modifications are to be executed during this phase.*

---

## 1. PHASE B AUDIT PLAN: ALEMBIC RECOVERY

### 1.1 What Must Be Audited
* Alembic current state vs. actual PostgreSQL schema
* Alembic migration heads and history graph
* Identification of orphan or duplicate migrations
* Database schema drift
* Downgrade integrity
* Database bootstrap capability from an empty state
* Verification that every PostgreSQL table, index, constraint, and partition is represented in the migration history

### 1.2 Commands to Run
* `alembic current`
* `alembic heads`
* `alembic history --indicate-current`
* `alembic check` (to detect drift between models and schema)
* `alembic upgrade head` (against an isolated, empty PostgreSQL database test instance)
* `alembic downgrade base` (against an isolated PostgreSQL database test instance)

### 1.3 Files to Inspect
* `alembic.ini`
* `alembic/env.py`
* `alembic/versions/*.py`
* All SQLAlchemy `models.py` definitions

### 1.4 Migration Risks
* Schema drift: SQLAlchemy models not matching active database tables.
* Broken downgrade scripts resulting in irreversible migrations.
* Multiple Alembic heads or disconnected migration histories.
* Manual schema alterations not captured within Alembic.

### 1.5 Evidence Collection Strategy
* Capture terminal outputs of all `alembic` commands.
* Collect the empty diff from schema drift detection tools.
* Document the successful execution logs of an empty database bootstrap up to `head` and down to `base`.
* Export PostgreSQL metadata queries mapping all tables/indexes to their defining Alembic migrations.

### 1.6 Acceptance Criteria
* [ ] A single, continuous Alembic head exists.
* [ ] `alembic current` explicitly matches the active head.
* [ ] Zero schema drift detected between SQLAlchemy models and the PostgreSQL database.
* [ ] Bootstrapping from an empty DB succeeds without errors up to head and back down to base.
* [ ] 100% of tables, indexes, constraints, and partitions are accounted for in the migration history.

---

## 2. PHASE C AUDIT PLAN: CACHE CONSOLIDATION

### 2.1 Active and Legacy Cache Layers
* **Active cache layers:** Application memory cache, PostgreSQL cache tables.
* **Legacy cache layers:** Validate complete removal of standalone Redis or file-based legacy caches (unless specifically scoped).
* **PostgreSQL cache usage:** `market_data.ltp_cache`, `market_data.candles`.
* **Redis usage:** Verify current status (deprecated vs. active).
* **Memory cache usage:** Singletons or LRU caches in application memory.
* **Scanner cache behavior:** How the scanner requests, stores, and reuses data.

**Cache Flow Audit Path:**
`Scanner` -> `Memory Cache` -> `PostgreSQL` -> `FYERS` -> `YFinance`

### 2.2 Evidence Collection Strategy
* Analyze application logs for cache hit rates and miss rates over a defined period.
* Review network traffic and API request logs to FYERS/YFinance for duplicate downloads.
* Assess candle reuse frequency.
* Evaluate risks of stale data.
* Measure cache warm-up time and persistence mechanisms.

### 2.3 Key Determinations
* Are candles being effectively reused?
* Are candles being unnecessarily downloaded from external APIs?
* Is the overall cache architecture correct and optimal for the system load?

### 2.4 Acceptance Criteria
* [ ] Cache hit rate meets or exceeds expected thresholds (e.g., > 95% for active scanner symbols).
* [ ] Zero duplicate downloads detected for identical candle/timeframe combinations.
* [ ] Stale data invalidation is functioning correctly without serving outdated market data.
* [ ] Cache warm-up executes successfully without exhausting API rate limits.
* [ ] Cache layers persist data appropriately across system restarts.

---

## 3. PHASE E AUDIT PLAN: POSTGRESQL CUTOVER

### 3.1 Verification Scope
* Complete removal of SQLite runtime references.
* Absence of any SQLite `.db` or `.sqlite` files in the runtime environment.
* Verification of a 100% PostgreSQL-only runtime.
* AsyncPG driver and pool health.
* Transaction and session boundary health.
* Stability of core components: Scanner, Paper Trading, Dashboard.

### 3.2 Lifecycle Verification
* **Connection lifecycle:** Pool acquisition and release patterns.
* **Session lifecycle:** Proper scoping of `AsyncSession`.
* **Rollback lifecycle:** Error handling guarantees a rollback.
* **Transaction lifecycle:** Commits are explicit without uncontrolled autocommits.

### 3.3 Evidence Collection Strategy
* Search the codebase for lingering `sqlite:///` connection strings or driver imports.
* Monitor `pg_stat_activity` to verify stable connection counts under load.
* Review application logs for PostgreSQL initialization, session creation, and transaction terminations.

### 3.4 Acceptance Criteria
* [ ] Zero SQLite references in the active codebase or environment variables.
* [ ] No new SQLite files are created during full system operation.
* [ ] PostgreSQL connection pool maintains stable active/idle connection counts without exhaustion.
* [ ] Transactions correctly rollback on failure (no partial commits observed).
* [ ] Scanner, Dashboard, and Paper Trading operate entirely error-free against PostgreSQL.

---

## 4. ASYNC CONCURRENCY AUDIT PLAN

### 4.1 Audit Scope
For every occurrence of the following, collect file, line, purpose, risk, and a safe/unsafe classification:
* `asyncio.run`
* `asyncio.to_thread`
* `asyncio.create_task`
* `asyncio.gather`
* `run_coroutine_threadsafe`
* `ThreadPoolExecutor`
* `ProcessPoolExecutor`

### 4.2 Evidence Collection Strategy
* Perform an AST or regex-based sweep of the codebase for the above primitives.
* Create a risk registry documenting each instance with the required metadata.
* Analyze application logs and execution flows for undetected unawaited coroutines or task leaks.

### 4.3 Detection Targets
* Unawaited coroutines (`RuntimeWarning: coroutine was never awaited`).
* Event loop violations (blocking synchronous calls inside async functions).
* Thread starvation / Thread pool exhaustion.
* Background task leaks (tasks created, not awaited, not cancelled, and not tracked).
* Scheduler duplication (e.g., multiple schedule dispatchers running concurrently).

---

## 5. SESSION & CONNECTION AUDIT PLAN

### 5.1 Audit Scope
Verify the proper lifecycle across:
* `AsyncSessionLocal`
* `SessionLocal`
* `get_db`
* `get_sync_db`

### 5.2 Verification Points
* `close()` is always executed (e.g., via context manager).
* `rollback()` is reliably called on exceptions.
* `commit()` is explicit and intentional.
* Exception handling around database operations is robust.

### 5.3 Detection Targets
* Session leaks (sessions not explicitly closed).
* Transaction leaks (transactions left open holding locks).
* Idle transactions (`IDLE IN TRANSACTION`) degrading database performance.
* Connection pool exhaustion (timeouts waiting for a connection).
* Dangling database connections.

---

## 6. ACCOUNTING AUDIT PLAN

### 6.1 Verification Formula
The following equation must reconcile perfectly at all times:
`Starting Cash = Current Cash + Reserved Cash + Open Position Value + Realized PnL + Unrealized PnL + Transaction Ledger`

### 6.2 Audit Scope
* Orders
* Positions
* Trades
* Transactions
* Balances

### 6.3 Evidence Collection Strategy
* Query the accounting tables and execute the verification formula across all active and historical accounts.
* Inspect ledger entries for consistency with external/paper fill events.

### 6.4 Detection Targets
* Balance drift (the formula does not sum correctly).
* Missing transactions in the ledger.
* Duplicate transactions for a single event.
* Partial commits (e.g., order filled but balance not updated).

---

## 7. MARKET DATA PERSISTENCE AUDIT PLAN

### 7.1 Audit Scope
* `market_data.candles`
* `market_data.ltp_cache`
* `market_data.scan_results`

### 7.2 Verification Points
* **Persistence:** Data is reliably written to disk.
* **Growth:** Rate of data ingestion matches expectations.
* **Retention:** Data is kept only as long as required.
* **Cleanup:** Purge mechanisms for old data exist and function.
* **Partitions:** Table partitions are correctly managed by time/symbol.
* **Indexing:** Queries are highly optimized and hitting intended indexes.

### 7.3 Determinations
* Projected database growth over 1, 3, and 6 months.
* Storage risks (disk exhaustion).
* Performance risks (table bloat, missing indexes).

---

## 8. FYERS INTEGRATION AUDIT

### 8.1 Audit Scope
* Token lifecycle (generation, validation)
* Token refresh process
* Token storage and retrieval
* Websocket connectivity and stability
* Quote retrieval mechanisms
* Candle retrieval mechanisms
* Fallback routing (e.g., YFinance)

### 8.2 Verification Points
* Valid token execution path.
* Expired token detection and handling path.
* Invalid token error path.
* Network timeout handling path.
* Retry behavior on transient failures.

### 8.3 Evidence Collection Strategy
* Collect success rates of API calls over a standard trading window.
* Document network timeout rates and patterns.
* Measure fallback rates (how often the system routes to YFinance instead of FYERS).

### 8.4 Determinations
* Exactly how often is the YFinance fallback being utilized?
* Are FYERS API failures being hidden by the fallback layer without raising alerts?
* Is there any scenario where stale prices or quotes can be returned to the scanner or paper trader?

### 8.5 Acceptance Criteria
* [ ] Zero silent failures during API interactions.
* [ ] Zero occurrences of stale quotes being served.
* [ ] No hidden fallback loops (fallback usage must be explicitly logged and alerted).

---

## 9. WEBSOCKET AUDIT

### 9.1 Audit Scope
* Websocket manager architecture
* Websocket connection lifecycle
* Reconnect handling logic
* Disconnect handling logic
* Subscription management and tracking

### 9.2 Verification Points
* Successful reconnect after simulated network failure.
* Successful reconnect after server-side FYERS disconnect.
* Prevention of duplicate symbol subscriptions.
* Prevention of stale tick data delivery during recovery.

### 9.3 Evidence Collection Strategy
* Monitor and record reconnect counts over a continuous 48-hour period.
* Track dropped message counts during network instability.
* Log the total active subscription count versus expected symbols.

### 9.4 Detection Targets
* Duplicate websocket connections spawned simultaneously.
* Duplicate subscriptions to the same symbol across connections.
* Orphan subscriptions (subscriptions persisting for removed symbols).
* Memory leaks directly associated with websocket message queues.

### 9.5 Acceptance Criteria
* [ ] A single active, stable websocket connection exists per worker.
* [ ] Zero duplicate subscriptions occur across the application.
* [ ] Automatic recovery succeeds without manual intervention.
* [ ] Zero memory growth is observed in the websocket manager over time.

---

## 10. ORDER ENGINE AUDIT

### 10.1 Audit Scope
* MARKET orders lifecycle
* LIMIT orders lifecycle
* Order modification logic
* Order cancellation logic
* Order rejection handling
* Complete order fill lifecycle

### 10.2 Verification Path
Order lifecycle must be mapped step-by-step:
`Order Request` -> `Validation` -> `Funds Check` -> `Order Creation` -> `Fill Engine` -> `Position Update` -> `Ledger Update`

### 10.3 Detection Targets
* Duplicate executions (e.g., race conditions causing double fills).
* Stuck pending orders (orders not transitioning out of 'PENDING' state).
* Orphan orders (orders without a valid parent or associated account).
* Missing fills (fills received from broker but dropped internally).
* Negative balances caused by bypassed funds checks.
* Double fills resulting from webhook/polling duplication.
* Concurrency race conditions in the Fill Engine.

### 10.4 Acceptance Criteria
* [ ] Zero duplicate execution events across all logs.
* [ ] Zero orphan orders in the database.
* [ ] Zero negative account balances possible during high concurrency.
* [ ] Zero double fills regardless of network duplication.

---

## 11. POOL FORENSICS AUDIT

### 11.1 Collection Strategy
Collect `pg_stat_activity` snapshots every 30 seconds during:
* Scanner execution
* Dashboard load
* Order placement
* Stress testing

### 11.2 Tracked Metrics
* active
* idle
* idle in transaction
* waiting
* blocked

### 11.3 Detection Targets
* Pool exhaustion
* Connection starvation
* Transaction leaks
* Connection leaks

### 11.4 Acceptance Criteria
* [ ] `idle in transaction` = 0
* [ ] Pool exhaustion occurrences = 0
* [ ] Connection leaks = 0
* [ ] Blocked sessions = 0

---

## 12. SCANNER FORENSICS AUDIT

### 12.1 Verification Path
`Frontend` -> `Route` -> `Agent` -> `Screener` -> `MarketDataService` -> `Cache` -> `FYERS` -> `Persistence`

### 12.2 Collection Strategy
* Execution duration
* Cache hit ratio
* Symbols scanned
* Failures
* Retries

### 12.3 Detection Targets
* Duplicate scans
* Stuck scans
* Coroutine leaks
* Thread starvation
* Scheduler duplication

### 12.4 Acceptance Criteria
* [ ] Scanner completes successfully.
* [ ] No unawaited coroutine warnings in logs.
* [ ] No duplicate scheduler execution.

---

## 13. ACCOUNTING FORENSICS

### 13.1 Verification Path
For every filled order verify the following records exist:
`Order` -> `Position` -> `Trade` -> `Transaction` -> `Account Balance`

### 13.2 Detection Targets
* Missing trade rows
* Missing transaction rows
* Balance drift
* Partial commits

### 13.3 Acceptance Criteria
* [ ] 100% reconciliation across all accounts.
* [ ] Zero missing records across the entire ledger.

---

## 14. POSTGRES PARTITION AUDIT

### 14.1 Audit Scope
* `market_data.candles`

### 14.2 Verification Points
* Partition creation logic
* Partition routing logic
* Partition pruning (query performance)

### 14.3 Collection Strategy
* Row count per partition
* Partition growth trends

### 14.4 Detection Targets
* Missing partitions causing insert failures
* Default partition usage (spillover)
* Orphan rows in unmanaged partitions

### 14.5 Acceptance Criteria
* [ ] 100% routing success to target partitions.

---

## 15. PHASE F READINESS GATE

**READY_FOR_PHASE_F ONLY IF PASS:**

* Phase B Audit
* Phase C Audit
* Phase E Audit
* Async Audit
* Session Audit
* Pool Audit
* Accounting Audit
* Accounting Forensics
* Market Data Audit
* Scanner Audit
* FYERS Audit
* WebSocket Audit
* Order Engine Audit
* Partition Audit

**ADDITIONAL CONDITIONS:**
* No Critical Findings
* No High Severity Findings

**Otherwise:**
* **BLOCKED_WITH_FINDINGS**

---

## 16. EXECUTION EFFORT & RISK PRIORITIZATION

### Estimated Effort
* **Phase B (Alembic Recovery):** 1-2 Days
* **Phase C (Cache Consolidation):** 1-2 Days
* **Phase E (PostgreSQL Cutover):** 1-2 Days
* **Async Concurrency:** 2-3 Days
* **Session & Connection:** 1-2 Days
* **Accounting Reconciliation:** 1-2 Days
* **Market Data Persistence:** 1 Day
* **FYERS Integration:** 1-2 Days
* **Websocket Audit:** 1-2 Days
* **Order Engine Audit:** 2-3 Days
* **Forensics (Pool, Scanner, Accounting):** 2-3 Days
* **Postgres Partition Audit:** 1 Day
* **Total Estimated Effort:** 15-25 Days

### Risk Prioritization (Highest to Lowest)
1. **Order Engine Audit:** Direct risk of unintended positions and severe financial loss.
2. **Accounting Forensics:** Direct financial impact / data corruption.
3. **Pool Forensics / Session Leaks:** System-wide catastrophic outages.
4. **Websocket Audit:** Unhandled disconnects halt real-time data and missed trading signals.
5. **Scanner Forensics:** Impacts market analysis and trade generation.
6. **Async Concurrency Violations:** Silent failures, deadlocks, and missed fills.
7. **FYERS Integration:** Stale quotes lead to inaccurate trading decisions.
8. **Phase E (PostgreSQL Health):** Core foundational layer for all data operations.
9. **Phase B (Alembic State):** Prevents safe, continuous future deployments.
10. **Postgres Partition Audit:** Database growth management and query performance.
11. **Market Data Persistence:** Long-term storage scalability risk.
12. **Phase C (Cache Consolidation):** Performance bottlenecks and API rate limits.
