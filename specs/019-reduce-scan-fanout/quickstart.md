# Quickstart & Verification Guide: Reduce Scan-Result Fan-out (Sprint 3)

## Prerequisites
* Python 3.11 environment with backend dependencies installed (`pytest`, `sqlalchemy`, etc.).
* Accessible test database (SQLite in-memory/file or PostgreSQL test database).

---

## 1. Feature Flag Verification Commands

### Test Legacy Multi-Write Mode (`SCAN_RESULT_MINIMAL_WRITES = OFF`)
```powershell
$env:SCAN_RESULT_MINIMAL_WRITES="false"
pytest backend/app/tests/test_scan_store.py -v
```
**Expected Outcome**: All 6 database tables (`latest_scan_results`, `market_data.scan_results`, `scan_snapshots`, `scan_snapshot_records`, `scan_history_snapshots`, `scanned_candidates`) receive write queries.

### Test Minimal Write Mode (`SCAN_RESULT_MINIMAL_WRITES = ON`)
```powershell
$env:SCAN_RESULT_MINIMAL_WRITES="true"
pytest backend/app/tests/test_scan_store.py -v
```
**Expected Outcome**: 
1. `latest_scan_results` is upserted.
2. `market_data.scan_results` receives 0 writes (when `save_history=false`).
3. `scan_snapshots`, `scan_snapshot_records`, `scan_history_snapshots`, `scanned_candidates` receive 0 writes.

### Test Conditional History Mode (`save_history = true`)
```powershell
$env:SCAN_RESULT_MINIMAL_WRITES="true"
pytest backend/app/tests/test_scanner_history_persistence.py -v
```
**Expected Outcome**: 
1. `latest_scan_results` is upserted.
2. `market_data.scan_results` receives historical insertion.
3. Legacy snapshot tables receive 0 writes.

---

## 2. API Parity Verification Command
```powershell
pytest backend/app/tests/test_dashboard.py -v
```
**Expected Outcome**: All GET `/api/v1/scanner/latest` and GET `/api/v1/dashboard/candidates` test assertions pass with 100% contract equality regardless of flag state.
