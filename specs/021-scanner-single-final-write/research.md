# Research & Architectural Decisions: Scanner Single Final Write (Sprint 5)

**Feature**: Scanner Single Final Write  
**Status**: Completed  
**Spec**: [spec.md](spec.md)  

---

## 1. Single Final Write Transaction Boundary

### Decision
Wrap all final write operations (`latest_scan_results` upserts and optional `market_data.scan_results` inserts) inside a single explicit SQLAlchemy / asyncpg transaction block (`async with session.begin():`).

### Rationale
* Guarantees 100% atomicity: either all scan results and history records are committed, or none are.
* Reduces database write-ahead log (WAL) synchronization flushes from multi-commit iterations to a single flush per scan execution.
* Releases connection locks in < 50ms rather than keeping connection slots active during the long analysis loop.

### Alternatives Considered
* **Savepoints / Nested Transactions**: Rejected. Adds unnecessary lock overhead and complex nested rollback logic without delivering performance gains.
* **Asynchronous Deferred Persistence Queue**: Deferred background queue (e.g. Celery / Redis queue) was rejected because live dashboard readers require immediate synchronous read consistency following scan completion.

---

## 2. In-Memory Aggregation DTO (`ScanAggregateResult`)

### Decision
Introduce a strongly typed dataclass/Pydantic structure `ScanAggregateResult` to encapsulate all symbol candidate findings, indicator metadata, and scan execution statistics during the in-memory analysis phase.

### Rationale
* Completely decouples technical indicator calculation logic from database ORM models and persistence calls.
* Allows complete unit testing of scanner calculation without needing database mocks or active DB connections.
* Provides a clean memory footprint that can be easily validated for completeness before opening a database transaction.

### Alternatives Considered
* **Direct ORM Model Instantiation during Analysis**: Instantiating SQLAlchemy ORM objects progressively during the analysis loop binds candidate records to session state, increasing memory overhead and risking accidental auto-flushes.

---

## 3. Parameterised Chunked Batching for Bulk Inserts

### Decision
Perform bulk insertions of candidate rows into `market_data.scan_results` in parameterised chunks of 500 rows within the single atomic transaction context.

### Rationale
* Prevents exceeding PostgreSQL maximum query parameter limits ($65,535 binding limit in asyncpg/psycopg) when scanning large symbol universes (e.g., 500–2,000 symbols).
* Maintains transaction atomicity while optimizing SQL query parsing and buffer memory usage.

### Alternatives Considered
* **Single Mass Insert Query**: Risks hitting parameter binding limits on very large universes.
* **Iterative Single-Row Inserts**: Significantly slower due to query parsing overhead per row.

---

## 4. Execution Timeout & Resource Governance

### Decision
Implement an explicit execution timer (default 30 seconds) around the in-memory scan calculation loop. If analysis exceeds 30 seconds, the scanner task raises a `ScanTimeoutError`, aborts without opening a DB write transaction, and emits `SCAN_TIMEOUT_ABORT` metrics.

### Rationale
* Prevents runaway or hung scan tasks from blocking background worker pools.
* Guarantees zero stale or partial writes to the database if network or API data sources stall.

---

## 5. Dynamic Feature Flag Evaluation (`SCANNER_SINGLE_FINAL_WRITE_ENABLED`)

### Decision
Evaluate `SCANNER_SINGLE_FINAL_WRITE_ENABLED` per scan cycle envelope directly from application runtime settings/environment.

### Rationale
* Enables instant, zero-downtime operational rollback to legacy persistence paths if anomalies are detected in production.
* Follows the identical fail-safe pattern implemented during Sprint 3 (`SCAN_RESULT_MINIMAL_WRITES`).
