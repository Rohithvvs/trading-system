# F1.2 Pre-Deployment Consistency Audit

## Objective
Verify that all recent changes are internally consistent before pushing to development.

## 1. Scanner Vectorization Fix
- **Files Modified**: `backend/app/services/screener_service.py`
- **Execution Path**: Dataframes are built inside `screen_symbols_swing` immediately after gathering tasks. Data is indexed by timestamp, sorted, and forward-filled using pandas to heal continuity gaps.
- **Dependencies**: `pandas`
- **Possible Regression Risks**: Performance overhead on very large symbol universes during the conversion between generic Python classes (`OHLCVPoint`) and pandas DataFrames. 

## 2. Latest Scan Persistence
- **Files Modified**: `backend/app/services/latest_scan_service.py`, `backend/app/models/market_data.py`, `backend/app/main.py`
- **Execution Path**: Following successful completion of `agent.run_screener`, `LatestScanService.persist_successful_scan` is called in `main.py`. This processes the `ScreenerResponse` mapping to SQLAlchemy `ScanSnapshot` and `ScanSnapshotRecord` objects.
- **Dependencies**: `SQLAlchemy`
- **Possible Regression Risks**: High volumes of matched candidates might briefly block the event loop during database insertion if not chunked, but current universes are suitably bounded.

## 3. Dashboard Latest Scan Loading
- **Files Modified**: `backend/app/routes/scanner.py`, `frontend/src/Dashboard.tsx`, `frontend/src/api.ts`
- **Execution Path**: Dashboard initializes and hooks `useEffect` to `api.getLatestScan()`. The FastAPI router `GET /scanner/latest` invokes `LatestScanService.get_latest_completed_scan()` checking for the newest timestamp.
- **Dependencies**: `React`, `FastAPI`
- **Possible Regression Risks**: UI mounting empty responses.

## 4. Shadow Run Instrumentation
- **Files Modified**: `backend/app/services/diagnostics_service.py`, `backend/app/routes/system.py`, `backend/app/services/fyers_service.py`, `backend/app/main.py`
- **Execution Path**: Various API boundaries directly invoke synchronous `.record_*` and `.increment_*` methods inside the `ShadowRunDiagnostics` singleton instance. 
- **Dependencies**: `psutil` (Safely guarded by `ImportError` fallback).
- **Possible Regression Risks**: None. All operations are non-blocking list appends capped at a threshold.

## 5. Scheduler Registration
- **Files Modified**: `backend/app/main.py`
- **Execution Path**: Synchronous event handler attached via `scheduler.add_listener` intercepting standard APScheduler events (`EVENT_JOB_SUBMITTED`, etc.).
- **Dependencies**: `apscheduler`
- **Possible Regression Risks**: Standard listener overhead. Negligible.

---

## VERIFY DATABASE
- **Models**: `ScanSnapshot`, `ScanSnapshotRecord`
- **Foreign Keys**: Confirmed `ForeignKey("scan_snapshots.scan_id", ondelete="CASCADE")`. Safe schema mapping.
- **Indexes**: Confirmed indexed across `scan_id`, `scan_timestamp`, and `symbol`.
- **Retention Coverage**: ⚠️ **MISSING**. `retention_service.py` natively omits cleanup directives for both `ScanSnapshot` and `ScanSnapshotRecord`. Without updates, `scan_snapshot_records` will accumulate indefinitely creating unbound database bloat.

## VERIFY API CONTRACTS
**`GET /scanner/latest`**
- **Response Schema**: Mapped accurately back to UI expectations (`buy_candidates`, `watch_candidates`, etc.).
- **Null Handling**: Clean fallback to `{"message": "No completed scans found", "buy_candidates": [], ...}`.
- **Empty Scan Handling**: Confirmed gracefully handled by frontend component checks.

## VERIFY FRONTEND
- **Dashboard Load (No execution)**: Confirmed. The UI component does not directly execute sweeps.
- **Dashboard Loads Latest Snapshot Only**: Confirmed. `getLatestScan()` isolates retrieving the snapshot vs `runPresetScreener()`.
- **No Orchestrator Invocation**: Confirmed. Handlers strictly pull from PostgreSQL cache endpoints.

## VERIFY OBSERVABILITY
**`GET /system/shadow-run/status`**
- **Empty State**: Safe list slicing (`[-5:]`) and fallback configurations handle empty instances without throwing `IndexError`.
- **DB Failure**: Handles `pg_stat_activity` probe safely under broad `except` block.
- **FYERS Failure**: Hardcoded initialization ensures health metrics exist as 0 structurally regardless of runtime availability.

---

## Output Status

**Classification:** **WARNING**
**Final Status:** **READY_TO_PUSH** (with remediation advised on database retention).
