# Edge Cases

The Scanner Engine handles several edge cases to ensure stability and accuracy during bulk operations.

## Missing Candles
- **What happened**: A stock is newly listed, or API data is missing for specific dates.
- **Why**: Trading holidays, exchange glitches, or FYERS API issues.
- **Expected behavior**: Calculate indicators on available data without crashing.
- **Actual implementation**: 
  - `ScreenerService` checks `_passes_data_quality`. If `total_candle_count < MINIMUM_SWING_CANDLES` (220), the stock is failed with `data_quality_failed=True`.
  - Missing days in the middle of a dataset are patched using Forward Fill (`ffill()`) in Pandas before bulk vectorization.
- **Recovery**: Automatic. Missing internal dates are `ffilled`. Short histories are gracefully rejected.

## Duplicate Symbols
- **What happened**: A symbol appears twice in the universe list.
- **Why**: Misconfigured universe arrays (e.g., a stock is in both NIFTY500 and FNO lists, and both are scanned).
- **Expected behavior**: Process the symbol only once.
- **Actual implementation**: `OrchestratorAgent._dedupe_symbols()` uses a `set` to track seen symbols and normalizes them via `_canonical_symbol()` (stripping `-EQ` and `NSE:` prefixes).
- **Recovery**: Automatic. Duplicates are logged and skipped.

## Empty API Responses
- **What happened**: FYERS API returns a 200 OK but the `candles` array is empty.
- **Why**: Invalid symbol ticker, or the stock is delisted/suspended.
- **Expected behavior**: Skip the symbol, do not crash the bulk matrix.
- **Actual implementation**: Returns an empty DataFrame. The symbol is dropped before entering `analyze_bulk_from_frame`.
- **Recovery**: Handled gracefully. Symbol is marked as `data_source_failed`.

## Partial Data / Short History
- **What happened**: FYERS returns 50 candles instead of the requested 240.
- **Why**: The stock is a recent IPO.
- **Expected behavior**: Reject the stock since 200-day moving averages cannot be computed accurately.
- **Actual implementation**: The cache validation in `MarketDataService` identifies insufficient history. It attempts to backfill. If the full history is still less than the required count (`get_required_candle_count`), the symbol is skipped gracefully.
- **Recovery**: Automatic. Handled gracefully.

## Market Closed / Trading Holiday
- **What happened**: The scanner runs on a Saturday or a public holiday.
- **Why**: Scheduled cron job executes on a non-trading day (if not handled by the scheduler config).
- **Expected behavior**: Scan the last available trading day.
- **Actual implementation**: FYERS API returns historical data up to the last trading session. The Pandas index logic handles weekends natively by aligning to business days and forward-filling if needed.
- **Recovery**: Automatic. It just scans Friday's close.

## Rate Limits
- **What happened**: FYERS API rate limits the backend (HTTP 429).
- **Why**: Fetching incremental data for 500 stocks concurrently.
- **Expected behavior**: Throttle requests or back off.
- **Actual implementation**: Uses `TokenBucketRateLimiter` (`_rate_limiter`) configured at 5 calls per second in `ScreenerService`. 
- **Recovery**: Automatic throttling.
