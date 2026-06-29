# MONDAY SHADOW RUN CHECKLIST

## 09:00 Scanner Validation
- [ ] Monitor logs at 08:55 AM IST to verify `job_market_engine_spin_up` fires.
- [ ] At 09:00 AM IST, ensure `pre_market_deep_scan` executes successfully.
- [ ] Access `GET /system/shadow-run/report`.
- [ ] **Verify `scheduler_summary`**: Confirm `success: true` for the 09:00 execution.
- [ ] **Verify `scanner_summary`**: Confirm exactly 1 run exists.
- [ ] Check that `requested_symbols` matches the configured universe size.
- [ ] Check that `duration_ms` is within expected operational limits.

## 09:30 Dashboard Validation
- [ ] Open the React Frontend Dashboard.
- [ ] **Verify Mounting**: Ensure the dashboard loads without triggering a live sweep.
- [ ] **Verify Persistence**: Confirm the components successfully retrieved the `09:00` scan snapshot.
- [ ] Access `GET /system/shadow-run/report`.
- [ ] **Verify `dashboard_summary`**: Check that `latest_scan_requests` has incremented and `failed_requests` remains at 0.

## 12:00 Health Validation
- [ ] Access `GET /system/shadow-run/report`.
- [ ] **Verify `database_summary`**:
  - `active_connections` should be stable.
  - `idle_in_transaction` should ideally be 0.
  - `scan_snapshot_count` should equal 1.
  - `scan_snapshot_record_count` should equal `buy_count` + `watch_count` + `rejected_count`.
- [ ] **Verify `fyers_summary`**:
  - Confirm `auth_failures` == 0.
  - Check `timeout_count` and `retry_count` limits.
- [ ] **Verify `runtime_summary`**: Ensure memory (`process_memory_mb`) has not ballooned unexpectedly post-garbage collection.

## 15:30 Market Close Validation
- [ ] Monitor logs to verify `job_market_engine_cool_down` fires at 15:30 IST.
- [ ] Review any new `scheduler_runs` via the `/system/shadow-run/report` payload to ensure intraday heartbeats completed seamlessly.
- [ ] Perform a final audit of `database_summary` connection metrics to confirm PostgreSQL resources cleanly shut down and drained.
- [ ] Generate final export of `/system/shadow-run/report` JSON data for end-of-day analytics.
