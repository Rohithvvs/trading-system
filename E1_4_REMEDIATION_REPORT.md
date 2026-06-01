# E1_4_REMEDIATION_REPORT.md
## Order Transaction Boundary Refactor

### Root Cause Analysis
The bottleneck was caused by `PaperTradingService.place_order`. Before the fix, the function would:
1. Implicitly begin a PostgreSQL transaction via `_get_or_create_account(for_update=False)`.
2. Fetch external market data via `_price_snapshot` (which connects to the FYERS API and downloads OHLCV and LTP data) while holding the database connection open.
3. Acquire an exclusive row lock on the account via `_get_or_create_account(for_update=True)`.
4. Perform idempotency checks and insertions.
5. Create the order and update positions.

During high concurrency (e.g., 50 market orders at once), the database connection pool was rapidly exhausted as connections were tied up waiting for FYERS network responses. Even worse, the requests that successfully fetched data would hold the `FOR UPDATE` lock on the account while performing additional checks, causing the remaining requests to back up and eventually fail with `lock_timeout` (which is configured to 5s in PostgreSQL) and `HTTP 500`.

### Remediation Steps
The order execution flow was entirely refactored to minimize lock durations and eliminate network I/O inside the active database transaction:

1. **Idempotency Check Isolation:** The `_acquire_idempotency` and `_update_idempotency` steps were moved to the very top, running in their own isolated, short-lived transaction.
2. **Pre-fetching Network Data:** The system now queries the active pending orders in a brief read-only transaction, commits it to release the database connection, and then fetches all required market data from FYERS.
3. **Optimized Transaction Boundary:** The exclusive `FOR UPDATE` lock is only acquired *after* all market prices have been cached locally in memory. The core insertion, fill logic, and balance updates now complete entirely in milliseconds without any network latency.
4. **Connection Pool Safety:** By committing before the network call, database connections are freed back to the pool, ensuring that long external requests do not exhaust system capacity.
