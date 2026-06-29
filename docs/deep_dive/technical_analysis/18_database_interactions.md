# Technical Analysis: Database Interactions

The Technical Analysis Engine (`TechnicalAnalysisService`) does not interact with the database directly. It expects a fully hydrated Pandas DataFrame to be passed into its `analyze_bulk_from_frame()` method. 

However, the pipeline that feeds the engine (orchestrated by the `ScreenerService` and `MarketDataService`) relies heavily on a local SQLite database to achieve the latency and rate-limit compliance required for bulk technical analysis.

## Database Overview
* **System:** SQLite
* **File Location:** `backend/app/services/candle_cache.db`
* **Manager:** `backend/app/services/candle_store.py`
* **Purpose:** To persist historical OHLCV data across restarts, dramatically reducing the number of external API calls required to run the Technical Engine.

## Table: `daily_candles`

This is the primary table accessed for Swing mode technical analysis.

### Schema
* `symbol` (TEXT): The instrument identifier (e.g., `NSE:HDFCBANK-EQ`).
* `timestamp` (TIMESTAMP): The naive UTC timestamp of the candle.
* `open` (REAL): Opening price.
* `high` (REAL): Highest price.
* `low` (REAL): Lowest price.
* `close` (REAL): Closing price.
* `volume` (INTEGER): Total traded volume.

### Purpose
To store the minimum 240+ days of history required to accurately calculate long-term moving averages (SMA 200) and recursive exponential smoothing indicators (EMA, MACD) for every symbol in the universe.

### Queries

**1. Loading Full History (The Feed)**
When the scanner starts, it loads the entire cached history into a DataFrame to feed the Technical Engine.
```sql
SELECT timestamp, open, high, low, close, volume 
FROM daily_candles 
WHERE symbol = ? 
ORDER BY timestamp ASC
```

**2. Continuity Validation**
Before running calculations, the system checks if the cache is healthy and contiguous.
```sql
SELECT timestamp FROM daily_candles WHERE symbol = ? ORDER BY timestamp ASC
```

**3. Upserting New Data (Persistence)**
When the `MarketDataService` fetches the missing "delta" (e.g., yesterday's data) from the Fyers API, or forward-fills missing calendar days, it persists them back to the database.
```sql
INSERT OR REPLACE INTO daily_candles 
(symbol, timestamp, open, high, low, close, volume) 
VALUES (?, ?, ?, ?, ?, ?, ?)
```

## Other Tables

While `daily_candles` is used for Swing mode (1D timeframe), the system also manages:
* **`intraday_candles`**: Used when `AnalysisMode.intraday` is active, storing 1-minute, 5-minute, or 15-minute data required for VWAP and intraday EMA crossovers.
* **`cache_metadata`**: Stores the last-updated timestamps for each symbol to quickly determine if an API sync is required before launching the Technical Engine.

## Persistence Strategy
The database acts as a write-through cache. 
1. The system checks the DB.
2. If data is missing or stale, it fetches exactly what is missing from the API.
3. It writes the new data to the DB.
4. It reads the complete merged dataset from the DB to construct the DataFrame for the engine. 

This ensures that the Technical Analysis Engine always calculates indicators based on the exact same dataset that is persisted to disk, guaranteeing deterministic, reproducible results.
