# PHASE B, C, E CLOSEOUT AUDIT PLAN

## 1. OBJECTIVE

The goal of this plan is to determine whether Phase B (Alembic Recovery), Phase C (Cache Consolidation), and Phase E (PostgreSQL Cutover & Stabilization) are truly complete and ready for production before advancing to Phase F. This is a read-only audit to identify remaining risks, verify architectural integrity, and confirm completion of acceptance criteria.

---

## 2. PHASE B PLAN: ALEMBIC RECOVERY

### 2.1. Audit Scope
1. **What will be audited:** Alembic version history integrity, migration application correctness, and PostgreSQL schema alignment.
2. **Which files will be inspected:** `alembic.ini`, `alembic/env.py`, `backend/app/models/*.py`, and all scripts inside `alembic/versions/`.
3. **Which commands will be executed:**
   - `alembic current`
   - `alembic heads`
   - `alembic history --indicate-current`
   - `alembic check` (or manual diff of metadata vs runtime schema)
4. **Which migration risks will be checked:** Duplicate migration IDs, orphan files, missing dependencies, schema drift, and invalid downgrade paths.
5. **Which acceptance criteria define completion:** A single linear, intact migration graph. Ability to bootstrap a new environment from zero to `head` successfully. Perfect alignment between SQLAlchemy models and PostgreSQL database.

### 2.2. Deliverables
* **PHASE_B_AUDIT.md**

---

## 3. PHASE C PLAN: CACHE CONSOLIDATION

### 3.1. Audit Scope
1. **What cache systems exist:** Memory caches (dict/LRU), database caches (PostgreSQL tables for OHLCV), and any legacy Redis configurations.
2. **Which cache layers will be audited:** `fyers_service.py` (LTP and OHLCV caching), `candle_store.py` (if applicable), `market_data_service.py`, and the Scanner module.
3. **How scanner cache flow will be verified:** By inspecting the scanner's execution path and logs to guarantee the fallback chain operates correctly: `Scanner -> Memory Cache lookup -> DB lookup -> FYERS -> YFinance`.
4. **How PostgreSQL candle reuse will be verified:** Checking database query logs or runtime metrics during repeated scanner calls to verify DB hit rates vs network calls.
5. **How Redis usage will be verified:** Auditing the codebase for `redis` imports, connections, or configuration keys to ensure it's either fully integrated or fully deprecated.
6. **How cache duplication will be detected:** By reviewing `paper_trading_service` and `fyers_service` to ensure both aren't caching the same entities independently.

### 3.2. Deliverables
* **PHASE_C_AUDIT.md**

---

## 4. PHASE E PLAN: POSTGRESQL STABILIZATION

### 4.1. Audit Scope
1. **What PostgreSQL validations remain:** Verifying table indexes, foreign key constraints, and performance tuning configurations (e.g., `statement_timeout`).
2. **What runtime validations remain:** Guaranteeing no `sqlite3` driver imports, files, or environment variable fallbacks are present in the runtime.
3. **What transaction validations remain:** Checking for long-running `idle in transaction` states, deadlocks during concurrent trading, and correct `COMMIT`/`ROLLBACK` handling.

### 4.2. Deliverables
* **PHASE_E_AUDIT.md**

---

## 5. SECTION 1 — ASYNC CONCURRENCY AUDIT

### 5.1. Audit Scope
Verify:
1. No blocking code in active event loops.
2. No async function executed via `to_thread` incorrectly.
3. No unawaited coroutines.
4. No fire-and-forget tasks without tracking.
5. No background task leaks.
6. No event-loop starvation risks.
7. No thread-pool starvation risks.

### 5.2. Deliverables
* **ASYNC_CONCURRENCY_AUDIT.md**

---

## 6. SECTION 2 — DATABASE SESSION LIFECYCLE AUDIT

### 6.1. Audit Scope
Audit all instances of:
* `AsyncSessionLocal`
* `SessionLocal`
* `get_db`
* `get_sync_db`

Verify:
1. Every session closes.
2. Every exception path rolls back.
3. No session leaks.
4. No dangling transactions.
5. No hidden commits.
6. No nested transaction abuse.
7. No leaked connections.

For every session creation point provide:
* file
* line
* creation
* commit path
* rollback path
* close path

### 6.2. Deliverables
* **SESSION_LIFECYCLE_AUDIT.md**

---

## 7. SECTION 3 — POSTGRES CONNECTION POOL AUDIT

### 7.1. Audit Scope
Capture actual runtime values and verify:
* `pool_size`
* `max_overflow`
* `pool_timeout`
* `pool_recycle`
* `pool_pre_ping`
* `asyncpg` configuration

Audit:
1. Pool exhaustion risk.
2. Connection reuse.
3. Idle connection behavior.
4. Idle-in-transaction behavior.
5. Background worker impact.
6. Scanner impact.
7. Paper trading impact.

### 7.2. Deliverables
* **POSTGRES_POOL_AUDIT.md**

---

## 8. SECTION 4 — ACCOUNTING RECONCILIATION AUDIT

### 8.1. Audit Scope
Perform formal accounting verification using the precise formula:
`Starting Cash = Current Cash + Reserved Cash + Open Position Value + Realized PnL + Unrealized PnL + Transaction Ledger Adjustments`

Verify:
1. Every filled order.
2. Every position.
3. Every trade.
4. Every transaction row.
5. Every account balance.

Detect:
* missing ledger entries
* duplicate ledger entries
* floating-point / decimal math precision errors
* balance drift
* partial commits
* rollback inconsistencies

### 8.2. Deliverables
* **ACCOUNTING_RECONCILIATION_AUDIT.md**

---

## 9. SECTION 5 — CACHE EFFECTIVENESS AUDIT

### 9.1. Audit Scope
Verify actual cache behavior. For scanner runs determine:
`Scanner -> Memory Cache -> PostgreSQL Candle Cache -> FYERS -> YFinance`

Measure:
1. Cache hit rate.
2. Cache miss rate.
3. PostgreSQL candle reuse.
4. Repeated FYERS downloads.
5. Repeated YFinance downloads.
6. Cache warm-up behavior.
7. Cache persistence behavior.

Determine:
* Are candles unnecessarily downloaded?
* Are stored candles reused?
* Is cache architecture working?

### 9.2. Deliverables
* **CACHE_EFFECTIVENESS_AUDIT.md**

---

## 10. SECTION 6 — MARKET DATA PERSISTENCE AUDIT

### 10.1. Audit Scope
Audit tables:
* `market_data.candles`
* `market_data.ltp_cache`
* `market_data.scan_results`

Verify:
1. Data persistence.
2. Growth behavior.
3. Retention strategy.
4. Cleanup strategy.
5. Partition strategy.
6. Index strategy.

Determine:
* projected DB growth
* storage risks
* performance risks

### 10.2. Deliverables
* **MARKET_DATA_PERSISTENCE_AUDIT.md**

---

## 11. SECTION 7 — PHASE F READINESS GATE

Add final decision gate. Answer the following questions definitively based on the collective findings of all above audits:

1. Scanner stable?
2. Dashboard stable?
3. Paper trading stable?
4. PostgreSQL stable?
5. Connection pools stable?
6. No connection leaks?
7. No idle transactions?
8. Accounting reconciled?
9. Cache architecture verified?
10. Market data persistence verified?
11. Async architecture safe?
12. Ready for 7-day shadow run?

**Final status MUST be exactly one:**
`READY_FOR_PHASE_F`
or
`BLOCKED_WITH_FINDINGS`
