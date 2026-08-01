# Quickstart & Verification Guide: Scanner Single Final Write (Sprint 5)

**Feature**: Scanner Single Final Write  
**Status**: Complete  
**Spec**: [spec.md](spec.md)  

---

## 1. Environment Setup

### Enable Single Final Write Architecture
To enable the Single Final Write mode in local development or test environments, set the environment variable:

```bash
export SCANNER_SINGLE_FINAL_WRITE_ENABLED=true
```

To run in legacy fail-safe mode:
```bash
export SCANNER_SINGLE_FINAL_WRITE_ENABLED=false
```

---

## 2. Automated Test Execution Commands

### Run Unit & Atomicity Tests
Execute unit tests for in-memory scan aggregation, timeout handling, and transaction atomicity:

```bash
pytest backend/app/tests/test_scanner_single_final_write.py -v
```

### Run Feature Flag Rollback Tests
Verify dynamic switching between ON and OFF flag states without service restarts:

```bash
pytest backend/app/tests/test_single_write_rollback.py -v
```

### Run API Payload Parity Regression Tests
Assert that `/api/v1/scanner/latest` returns identical payloads across flag states:

```bash
pytest backend/app/tests/test_latest_scan_service_unified.py -v
```

---

## 3. Manual Verification Steps

1. **Trigger Intraday Market Scan with Flag ON**:
   - Set `SCANNER_SINGLE_FINAL_WRITE_ENABLED=true`.
   - Trigger a scan run via API or background runner.
2. **Inspect Query Telemetry**:
   - Confirm that 0 database `INSERT` or `UPDATE` queries occur during active analysis loop.
   - Confirm that exactly 1 database transaction containing `latest_scan_results` upsert is logged upon scan completion.
3. **Verify Dashboard Read Consistency**:
   - Query `GET /api/v1/scanner/latest`.
   - Verify 200 OK status and correct candidate list.
4. **Test Dynamic Rollback**:
   - Change `SCANNER_SINGLE_FINAL_WRITE_ENABLED=false`.
   - Trigger scan run.
   - Confirm that legacy multi-point persistence executes cleanly.
