# Cache Interactions

The Scanner Engine employs multiple layers of caching to optimize performance, reduce network latency, and avoid API rate limits.

## 1. Database Candle Cache (PostgreSQL)
This is the primary cache layer for the Scanner.

- **Storage**: `daily_candles` and `intraday_candles` tables.
- **Lifecycle**: Persistent. Candles are never deleted unless explicitly purged.
- **Cache Miss**: If `MarketDataService.get_latest_candle_time()` returns `None`, or if `validate_candle_continuity()` reports missing history, a cache miss is triggered.
- **Cache Refresh / Backfill**: 
  - On a cache miss, the scanner makes a targeted request to the FYERS API for the missing dates (incremental fetch).
  - The new data is upserted into the database.
- **Benefits**: Reduces a 500-stock scan from taking minutes (due to API rate limits) to taking seconds.

## 2. In-Memory Pandas DataFrames
During execution, the scanner moves data from disk to memory for extremely fast computation.

- **Storage**: `symbol_frames` (Dictionary of DataFrames), which is then concatenated into a single `combined_frame`.
- **Lifecycle**: Ephemeral. Exists only during the execution of `screen_symbols_swing()`.
- **Memory Management**: 
  - The cache is explicitly cleared using the `del` keyword in Python (`del frame_parts`, `del combined_frame`) immediately after indicators are calculated.
  - This prevents Out-Of-Memory (OOM) errors in production.

## 3. FYERS Token Caching
- **Storage**: PostgreSQL (`auth_tokens` table managed by `token_service`).
- **Lifecycle**: The access token is valid for a single trading day (approx 24 hours).
- **Cache Invalidation**: Handled via scheduled jobs or when API calls return HTTP 401 Unauthorized (`FyersAuthExpiredError`).
- **Cache Refresh**: Historically automated, but currently restricted to manual user login via the frontend UI due to broker API constraints.

## 4. Redis (Architectural Provision)
While PostgreSQL acts as the primary data store, Redis is provisioned in the architecture for distributed locks and rate limiting, though the core scanner primarily relies on local DB caching and memory arrays.
