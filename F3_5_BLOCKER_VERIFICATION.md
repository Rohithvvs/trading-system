# F3.5 BLOCKER VERIFICATION

## VERIFY BLOCKER 1: `scheduler.start()`

- **File Path**: `backend/app/main.py`
- **Line Number**: 336
- **Code Snippet**:
```python
    # FYERS refresh automation removed. Manual access-token workflow only.
    if not settings.quarantine_mode:
        # scheduler.start()
        logger.info("Scheduler started — nightly sync at 18:30 IST")
    else:
        logger.info("QUARANTINE MODE: Scheduler execution bypassed.")
```
- **Determination**: **COMMENTED**
- **Classification**: **BLOCKER_CONFIRMED**

---

## VERIFY BLOCKER 2: Scheduler Registration

All scheduler jobs explicitly registered in `backend/app/main.py` during `lifespan`:

| Job ID | Cron (Asia/Kolkata) | Function |
|--------|----------------------|----------|
| `market_engine_spin_up` | `mon-fri`, `08:55` | `job_market_engine_spin_up` |
| `pre_market_deep_scan` | `mon-fri`, `09:00` | `automated_screening_job` |
| `intraday_heartbeat_1` | `mon-fri`, `09:00-14:45` (every 15m) | `job_intraday_heartbeat` |
| `intraday_heartbeat_2` | `mon-fri`, `15:00-15:30` (every 15m) | `job_intraday_heartbeat` |
| `market_engine_cool_down` | `mon-fri`, `15:30` | `job_market_engine_cool_down` |
| `track_strategy_drift_job`| `fri`, `16:00` | `track_strategy_drift_job` |
| `retention_cleanup` | Every day, `02:15` | `job_retention_cleanup` |

- **Verification**: `automated_screening_job` is indeed registered under the ID `pre_market_deep_scan`.
- **Classification**: **BLOCKER_CONFIRMED** (Registration exists, but it is orphaned because the scheduler never starts).

---

## VERIFY BLOCKER 3: 09:00 Collisions

Analyzing overlapping execution paths specifically on Monday morning at 09:00 IST:

| Job | Cron | Next Fire Time |
|-----|------|----------------|
| `automated_screening_job` | `mon-fri`, `09:00` | **09:00:00** |
| `job_intraday_heartbeat` (`intraday_heartbeat_1`) | `mon-fri`, `9-14`, `0,15,30,45` | **09:00:00** |

- **Identify Overlapping Jobs**: Both the heavy 755-symbol deep scan and the intense market WebSocket engine heartbeat are scheduled to strike the exact same millisecond.
- **Classification**: **BLOCKER_CONFIRMED**

---

## VERIFY BLOCKER 4: Persistence Success Masking

- **File Path**: `backend/app/main.py`
- **Call Chain**: Inside `automated_screening_job()` (Lines 680-705):
```python
            diagnostics.set_scanner_success(response.screener_name or f"scan-{start_t_iso}")

            try:
                # Still add to ScannedCandidate if it's used elsewhere
                for item in response.matches:
                    ...
                # New logic for PHASE S1: Persist full scan snapshot
                from .services.latest_scan_service import LatestScanService
                scan_service = LatestScanService(db)
                await scan_service.persist_successful_scan(response, duration_ms)
                
                await db.commit()
                logger.info("Saved scan candidates and latest scan snapshot to database.")
            except Exception as db_e:
                logger.error("Failed to save scan candidates to DB: %s", db_e)
                await db.rollback()
                
            logger_service.log_info(
                message="Automated screening job completed successfully.", ...
```
- **Verification**: `diagnostics.set_scanner_success()` is unconditionally executed on Line 680, *prior* to entering the persistence `try/except` block. If `db.commit()` raises an exception, the script enters the `except` block, rolls back the transaction, but **fails to unset or update the diagnostic state**. It then drops down and logs `Automated screening job completed successfully` to the system logger, completely blinding operators to the silent dashboard failure.
- **Classification**: **BLOCKER_CONFIRMED**
