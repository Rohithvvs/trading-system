# Failure Scenarios

## 1. Complete FYERS API Outage
- **Symptoms**: Scanner runs but returns 0 matched symbols. Logs show `data_source_failed=True` for all symbols.
- **Root Causes**: FYERS servers are down, or network connectivity from the backend host to FYERS is blocked.
- **Recovery**: The scanner attempts to use cached database candles. If the cache is stale, it might attempt the `yfinance` fallback (which is slower). If both fail, the scan returns an empty shortlist.
- **Alerts**: Search `logs/latest_scan.log` for `data_source_failed`.
- **Monitoring**: Check `ScreenerResponse.data_warning`.

## 2. Token Expiration
- **Symptoms**: Every FYERS request throws `FyersAuthExpiredError` or `FyersAuthInvalidError`.
- **Root Causes**: The access token stored in the database has expired (usually lasts 1 day). The auto-refresh job failed or the user didn't generate a new one.
- **Recovery**: Manual intervention required. The user must authenticate via the frontend UI to generate a new token.
- **Alerts**: Backend logs: `Scan aborted: No cached token available in memory or DB`.
- **Monitoring**: `diagnostics.set_scanner_failed("No FYERS token configured")`.

## 3. Database Connection Pool Exhaustion
- **Symptoms**: Application hangs during the scan. Logs show SQLAlchemy timeout errors or `asyncpg.exceptions.TooManyConnectionsError`.
- **Root Causes**: Memory leaks in session management, or `asyncio.gather` firing too many concurrent database queries during cache checks.
- **Recovery**: Restart the backend service. Ensure `AsyncSessionLocal` is used with an async context manager.
- **Alerts**: HTTP 500s across the board.

## 4. OOM (Out of Memory) Kills
- **Symptoms**: The backend container restarts unexpectedly during a scan. No graceful error logs.
- **Root Causes**: Attempting to load millions of rows into a Pandas DataFrame without chunking, or holding too many object references (e.g., `OHLCVPoint` lists instead of raw dataframes).
- **Recovery**: The system is designed to use vectorized DataFrames specifically to prevent this. Memory audits (`get_rss_mb()`) are placed throughout `ScreenerService`. Check the logs before the crash to see RSS usage.
- **Monitoring**: Monitor container/pod memory metrics.

## 5. Corrupted DB Cache
- **Symptoms**: The scanner triggers "forced rebuilds" repeatedly for the same symbols.
- **Root Causes**: The `MarketDataService.validate_candle_continuity` detects gaps (e.g., missing 5 days in a row) in the local database.
- **Recovery**: Automatic. The cache health check detects it and triggers a backfill from FYERS to heal the continuity. 
- **Alerts**: `Corrupted cache detected for [SYMBOL], triggering forced rebuild.`
