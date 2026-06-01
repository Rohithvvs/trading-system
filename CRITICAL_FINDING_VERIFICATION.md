# CRITICAL FINDING VERIFICATION

## 1. SQLite transaction writes still exist
**Status:** UNVERIFIED
**Evidence:** Could not produce evidence. The string `"Failed to write BUY transaction or notification to SQLite"` exists in `backend/app/services/paper_trading_service.py` at line 273, but this is merely a stale logging string. The actual database operation (`self.db.add(tx)`) executes against the injected SQLAlchemy session, which is correctly backed by PostgreSQL. No actual SQLite transaction writes occur.

## 2. asyncio.run misuse exists
**Status:** VERIFIED
**Exact File:** `backend/app/services/fyers_service.py`
**Exact Line:** 48
**Exact Code Snippet:**
```python
    if main_loop and main_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, main_loop).result()
    else:
        # Fallback for scripts and tests without a main loop
        return _SYNC_EXECUTOR.submit(asyncio.run, coro).result()
```

## 3. Order engine lacks row-level locking
**Status:** VERIFIED
**Exact File:** `backend/app/services/paper_trading_service.py`
**Exact Line:** 494-500
**Exact Code Snippet:**
```python
        if order.status in {"FILLED", "CANCELLED", "REJECTED"}:
            position = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.symbol == order.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
```
*Note:* The retrieval of `PaperPosition` during the fill attempt lacks `.with_for_update()`, exposing the system to concurrent position modification vulnerabilities despite the parent account being locked.

## 4. Accounting drift risk
**Status:** UNVERIFIED
**Evidence:** Could not produce evidence. Since Finding 1 (SQLite writes) is unverified and false, the split-brain database scenario does not exist. All ledger transactions and position updates execute atomically against the primary PostgreSQL database, negating the accounting drift risk caused by external DB logging.
