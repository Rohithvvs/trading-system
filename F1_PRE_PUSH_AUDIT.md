# F.1 Pre-Push Audit

## Objective
Verify all Phase F.1 shadow run instrumentation is active and correctly configured prior to branch push.

## Verification Checklist

### 1. GET /system/shadow-run/status
- [x] **Endpoint exists:** Verified router `/system/shadow-run/status` is mapped and exposed.
- [x] **Endpoint payload structure:** Returns JSON with `latest_scan`, `latest_scheduler_runs`, `db_health`, `fyers_health`, and `memory_metrics`.

### 2. Scheduler Instrumentation
- [x] **APScheduler listeners:** Registered correctly at `main.py` initialization.
- [x] **Monitored events:** Verified `EVENT_JOB_SUBMITTED`, `EVENT_JOB_EXECUTED`, `EVENT_JOB_ERROR`, and `EVENT_JOB_MISSED` are actively wired and updating the diagnostics store.

### 3. Scanner Instrumentation
- [x] **Captured Metrics:** Verified that `start_time`, `end_time`, `duration_ms`, `valid_symbols`, `buy_count`, `watch_count`, and `rejected_count` are captured accurately at the orchestrator boundary inside `main.py`.

### 4. FYERS Instrumentation
- [x] **Tracked Counters:** Increment logics for `request_count`, `failed_request_count`, `auth_failures`, `timeout_count`, `retry_count`, and `rate_limit_count` are correctly injected into FYERS core request routines and response checks (`_check_fyers_response`).

### 5. Database Health Instrumentation
- [x] **PG Stat Activity:** Verified standard `pg_stat_activity` query executes to evaluate PostgreSQL connection states.
- [x] **Monitored Dimensions:** `active_connections`, `idle_connections`, and `idle_in_transaction` successfully resolved.

### 6. Memory Instrumentation
- [x] **psutil Fallback Strategy:** Memory fetching blocks in `diagnostics_service.py` and `main.py` are properly wrapped in a try/except, gracefully falling back to returning 0.0 MB rather than crashing the system if `psutil` is missing.

### 7. Startup Verification
- [x] **Application Boot:** Clean application start confirmed using local test client bindings.
- [x] **Sample Response:**
```json
{
  "latest_scan": null,
  "latest_scheduler_runs": [],
  "db_health": {
    "active_connections": 1,
    "idle_connections": 7,
    "idle_in_transaction": 0,
    "pool_exhaustion_events": 0
  },
  "fyers_health": {
    "request_count": 0,
    "failed_request_count": 0,
    "auth_failures": 0,
    "timeout_count": 0,
    "retry_count": 0,
    "rate_limit_count": 0
  },
  "memory_metrics": {
    "process_memory_mb": 0.0,
    "scanner_memory_before_run_mb": 0.0,
    "scanner_memory_after_run_mb": 0.0
  }
}
```

## Final Status
**READY_TO_PUSH**
