# F3.7 PERSISTENCE VERIFICATION

## SOURCE CODE EVIDENCE
File: `backend/app/main.py` -> `automated_screening_job()`
Lines: 706-727

```python
                await db.commit()
                logger.info("Saved scan candidates and latest scan snapshot to database.")
                
                diagnostics.set_scanner_success(response.screener_name or f"scan-{start_t_iso}")
                logger_service.log_info(
                    message="Automated screening job completed successfully.",
                    source="JOB",
                    module="Scheduler",
                    endpoint="automated_screening_job"
                )
                logger.info("AUTOMATED SCREENING job complete")
            except Exception as db_e:
                logger.error("Failed to save scan candidates to DB: %s", db_e)
                await db.rollback()
                diagnostics.set_scanner_failed(str(db_e))
                logger_service.log_error(
                    message=f"Scheduled job failed to persist: {str(db_e)}",
                    source="JOB",
                    module="Scheduler",
                    endpoint="automated_screening_job",
                    exc=db_e
                )
```

## VERIFICATION
- `diagnostics.set_scanner_success()` location: Inside the `try` block, strictly **after** `await db.commit()`.
- `diagnostics.set_scanner_failed()` location: Inside the `except Exception as db_e:` block, strictly **after** `await db.rollback()`.
- **Can db.commit() fail while diagnostics still shows SUCCESS?**: NO. If `await db.commit()` throws an exception, execution immediately jumps to the `except` block, completely bypassing `set_scanner_success` and triggering `set_scanner_failed`.

## CLASSIFICATION
**PASS**
