# Technical Analysis: Cache Interactions

The Technical Analysis Engine operates as a high-speed computational layer. To maintain low latency across the entire system, various caching strategies are employed around the engine.

## 1. Redis Usage (Ecosystem Coordination)
The `TechnicalAnalysisService` itself does not calculate and store its outputs in Redis directly. Instead, Redis is used by the surrounding ecosystem (like `MarketDataService` and the live trading engine) to coordinate the *inputs* to the Technical Engine.
* **Rate Limiting:** Redis manages the API call budget for the `FyersService`, ensuring the system doesn't get banned while fetching the missing data required by the Technical Engine.
* **Token Management:** Distributed locks and token states are stored in Redis so that multiple scanner processes don't simultaneously try to refresh the API keys.

## 2. Cached Indicator Results (The Output Cache)
Because calculating indicators for 500 symbols takes non-zero CPU time, the final outputs of the Technical Engine (`TechnicalAnalysisResult` objects, containing scores and indicator values) are typically cached by the consuming service (e.g., `ScreenerService` or `LatestScanService`).
* **Swing Mode:** Because daily candles only update once per day, the final output of the Swing scan is highly cacheable. The system typically stores the final `ScreenerConditionResult` array in memory or a fast local store, serving frontend requests instantly without recalculating the EMA 200 every time a user refreshes the page.
* **Intraday Mode:** Intraday data changes every minute. Intraday indicator outputs are heavily ephemeral and generally not cached for longer than the resolution of the candle (e.g., a 1-minute TTL for a 1-minute chart).

## 3. The Input Cache (SQLite `candle_cache.db`)
As detailed in `18_database_interactions.md`, the primary cache for the Technical Engine is the SQLite historical database. 
* **Cache Invalidation:** The cache is never "cleared" routinely. Instead, it is continuously appended to. Invalidation only occurs if the `MarketDataService` detects a gap or continuity error (e.g., jumping from Monday to Thursday). If `validate_candle_continuity()` flags a symbol as `CORRUPTED`, the specific symbol's rows are wiped and forced to rebuild from the upstream API.
* **TTL / Refresh Strategy:** 
  * The system checks the most recent timestamp in the cache. 
  * If the timestamp is older than the last known trading session, a delta fetch is triggered. 
  * There is no strict TTL (Time To Live) on historical daily candles because a candle from 200 days ago never changes. The strategy is purely "append and forward-fill."

## 4. Why not Cache the Indicators inside the Database?
A common anti-pattern is storing the calculated SMA 200 or RSI 14 inside the SQL database alongside the price data. The Technical Analysis Engine explicitly avoids this.
* **Reasoning:** If an engineer decides to change the RSI lookback from 14 to 9, or switch the MACD from (12,26) to (10,20), caching the indicators in the database would require a massive database migration and recalculation script.
* **Current Implementation:** The database strictly caches the *raw, immutable truth* (OHLCV). The Technical Engine calculates the indicators on-the-fly in memory using Pandas. Because Pandas vectorized operations take mere milliseconds, the compute cost is so low that storing the indicators on disk is unnecessary and actually increases architectural complexity.
