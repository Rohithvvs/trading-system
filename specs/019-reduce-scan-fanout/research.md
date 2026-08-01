# Research & Technical Decisions: Reduce Scan-Result Fan-out (Sprint 3)

## 1. Feature Flag Implementation Strategy

### Decision
Utilize the centralized settings / environment configuration module (`app.config.settings`) to resolve `SCAN_RESULT_MINIMAL_WRITES`. The flag will be evaluated per scan execution cycle.

### Rationale
* Avoids adding external state service overhead during scan cycle initialization.
* Ensures atomic flag evaluation per scan cycle: once a scan cycle starts, it uses the evaluated flag state for the duration of that run, avoiding split-write anomalies mid-execution.
* Supports dynamic runtime override via environment variables without requiring code re-deployments.

### Alternatives Considered
* **Database-backed Feature Flag Table**: Rejected due to adding DB query roundtrips on every scan start, counteracting the goal of reducing DB IOPS.
* **In-memory Dynamic Poller**: Rejected as unnecessary overhead for a operational migration flag.

---

## 2. Canonical Latest Storage Selection

### Decision
`latest_scan_results` is selected as the primary canonical data store for live scan state.

### Rationale
* Already has a unique constraint on `symbol` (`uq_latest_scan_results_symbol`) optimized for `INSERT ... ON CONFLICT (symbol) DO UPDATE` batch upserts.
* Directly serves active trading dashboard components and live candidate list endpoints.
* Low memory footprint compared to storing monolithic JSONB envelopes or full snapshot hierarchies per scan execution.

### Alternatives Considered
* **`market_data.scan_results` as Canonical Source**: Rejected because storing full JSON payloads per scan cycle causes high write amplification and table bloat during high-frequency scans.
* **`scan_snapshots` / `scan_snapshot_records`**: Rejected because normalized snapshot hierarchies require multi-table transaction locks and parent-child join queries.

---

## 3. History Persistence Trigger & Interface

### Decision
Pass `save_history: bool` parameter from `ScanExecutionService` to `PersistenceService`. History writes to `market_data.scan_results` occur ONLY when `save_history=true` OR during scheduled milestone cron runs.

### Rationale
* Decouples intra-day real-time scanning (which only needs `latest_scan_results`) from historical archive needs.
* Allows scheduled EOD processes to explicitly request history persistence without impacting intra-day scan throughput.

### Alternatives Considered
* **Time-based Automatic Throttle in DB Layer**: Rejected because it introduces implicit logic in persistence services, making behavior harder to reason about and test.

---

## 4. Virtual Read Derivation for Legacy Endpoints

### Decision
Endpoints reading candidate lists (`scanned_candidates` or `scan_snapshot_records`) will project their responses dynamically from `latest_scan_results` when `SCAN_RESULT_MINIMAL_WRITES=ON`.

### Rationale
* Preserves 100% API response contract compatibility for legacy callers.
* Avoids keeping redundant physical tables updated.
* In-memory/DB projections from `latest_scan_results` are faster than joining snapshot records tables.

### Alternatives Considered
* **Database Views**: Rejected to avoid database migration scripts or schema changes in Sprint 3.
