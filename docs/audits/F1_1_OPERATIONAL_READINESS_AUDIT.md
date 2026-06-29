# F1.1 Operational Readiness Audit

## Objective
Identify potential failure paths and evaluate the systemic robustness of the application ahead of the Monday production shadow run.

## Audit Area 1: Scheduler
- **Job Validation**: Found 7 registered background cron jobs.
- **Dependencies**: No complex DAGs. Jobs run on strict cron expressions to prevent cross-job interference.
- **Singleton Protection**: Safe. Controlled by `trading-system:singleton-workers` distributed lease preventing multi-pod race conditions.
- **Missed Execution Handling**: Registered in APScheduler listener (`EVENT_JOB_MISSED`). Misfired jobs correctly skip rather than stampeding the queue when the process wakes up.

**Job Inventory Table:**
| Job ID | Cron Trigger | Description |
|---|---|---|
| `market_engine_spin_up` | Mon-Fri 08:55 | Wakes market engine |
| `pre_market_deep_scan` | Mon-Fri 09:00 | Primary screener orchestration |
| `intraday_heartbeat_1` | Mon-Fri 9-14 0,15,30,45 | Recurring interval checks |
| `intraday_heartbeat_2` | Mon-Fri 15 0,15,30 | Final hour checks |
| `market_engine_cool_down`| Mon-Fri 15:30 | Safe shutdown sequences |
| `track_strategy_drift_job` | Fri 16:00 | Performance drift calculation |
| `retention_cleanup` | Daily 02:15 | DB pruning via RetentionService |

## Audit Area 2: Scanner
- **Trace Path**: Scheduler (`main.py`) → `OrchestratorAgent.run_screener` → `ScreenerService.screen_symbols_swing` → `LatestScanService.persist_successful_scan` → PostgreSQL (`ScanSnapshot`, `ScanSnapshotRecord`) → Dashboard (`GET /scanner/latest`).
- **Validation**: Full data persistence and read sequences correctly aligned with the `ScanSnapshot` relationship. 

## Audit Area 3: FYERS
- **Token Handling**: Checked. `has_cached_token()` routes to DB correctly. `FyersAuthInvalidError` explicitly bubbled.
- **Retry Handling**: Handled via exponential backoff loop `_request_history_with_retries`. Bounded by semaphores (`_FYERS_HISTORY_SEMAPHORE`).
- **Timeout Handling**: Handled natively in FYERS fetch wrappers. Symbol-level exceptions in `screener_service.py` catch `Exception` block resolving to empty dataset `[]` rather than crashing the batch.
- **List of Failure Paths**:
  - Token Invalid/Expired -> Graceful exception caught, symbol skipped.
  - Connection Dropped/Timeout -> Exponentially retried, bubbled, symbol skipped.
  - Rate Limit Reached -> Backoff wait, bubbled on max retries, symbol skipped.
  - Data Quality Fails -> `_passes_data_quality` skips calculation seamlessly.

## Audit Area 4: PostgreSQL
- **Pool Sizing**: Async session `pool_size` set to 20 (max 30 with overflow). Sync session set to 80 (max 100).
- **Idle Handling**: `idle_in_transaction_session_timeout` explicitly set to `30s` via SQL injection on `connect` listener.
- **Retention Coverage**: Handled by nightly background cron job `retention_cleanup`.
- **New Tables Verification**: `scan_snapshots` and `scan_snapshot_records` mapped safely and efficiently.

## Audit Area 5: Memory
- **Growing Diagnostics State**: Resolved. `diagnostics_service.py` natively caps `scanner_runs` (max 50), `scheduler_runs` (max 100), and `dashboard_snapshots` (max 100) using array popping.
- **Unbounded Collections/Caches**: Identified `_ohlcv_cache`, `_ohlcv_source_cache`, and `_ltp_source_cache` in `fyers_service.py` as globally unbound `dict` objects. Given the finite Nifty500 symbol universe size, these behave as bounded lookups. However, prolonged uptimes without restarts may observe marginal leakage.

## Audit Area 6: Shadow Run Endpoint
- **Robustness checks for `GET /system/shadow-run/status`:**
  - **Scanner Never Ran**: Safe. Slices conditionally `diagnostics.scanner_runs[-1] if diagnostics.scanner_runs else None`.
  - **Scheduler Never Ran**: Safe. Emits `[]` array slice without crashing.
  - **FYERS Unavailable**: Safe. FYERS health returns default instantiated integer 0s.
  - **Database Degraded**: Safe. The `get_db_health` method leverages broad `try/except` returning standard `{ "error": "..." }`.

---

## Final Risk Classification

| ID | Issue | Risk | Description |
|---|---|---|---|
| R1 | FYERS Cache Eviction | **LOW** | `fyers_service.py` lacks an LRU eviction mechanism on dict caches. Mitigated by fixed maximum universe size, but could grow marginally under dynamic parameters over extremely long untethered lifespans. |
| R2 | Missed Execution Catch-ups | **LOW** | Missed jobs log gracefully without immediate retry attempts. While safe for system stability, network stutters on Monday at exactly 09:00 AM may bypass the scanner run completely. |

## Final Status
**READY_WITH_RISKS**
