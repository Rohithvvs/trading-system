# F3.7 SCHEDULER VERIFICATION

## SOURCE CODE EVIDENCE
File: `backend/app/main.py`
Lines: 342-347

```python
    # FYERS refresh automation removed. Manual access-token workflow only.
    if not settings.quarantine_mode:
        scheduler.start()
        logger.info("Scheduler started — nightly sync at 18:30 IST")
    else:
        logger.info("QUARANTINE MODE: Scheduler execution bypassed.")
```

## VERIFICATION
1. **`scheduler.start()` exists**: YES.
2. **Is NOT commented**: YES.
3. **Is reachable**: YES. It triggers on application boot inside the FastAPI `lifespan` generator.
4. **Executes when `quarantine_mode=False`**: YES.

## CLASSIFICATION
**PASS**
