# Database Interactions

The Scanner Engine is heavily dependent on PostgreSQL. The database is used both for high-performance caching (OHLCV candles) and for persisting the final results.

## 1. Candle Caching
**Table**: `daily_candles`
- **Purpose**: Stores historical EOD (End of Day) data for all symbols.
- **Queries**:
  - `SELECT max(timestamp) FROM daily_candles WHERE symbol = :symbol`
    - *Purpose*: Find the most recent date we have data for, so we only fetch incremental data from the API.
  - `SELECT count(*) FROM daily_candles WHERE symbol = :symbol`
    - *Purpose*: Validate that we have enough historical candles (e.g., > 240) to compute long-term moving averages.
- **Inserts/Updates**:
  - Uses Pandas `to_sql()` or SQLAlchemy bulk inserts in `MarketDataService.upsert_candles()`. 
  - Conflict resolution relies on unique constraints on `(symbol, timestamp)`.

## 2. Scan Persistence
The scanner preserves historical data for the dashboard without overwriting previous runs.

**Table**: `scan_snapshots`
- **Purpose**: Stores the metadata of a single scanner execution.
- **Fields**: `scan_id` (UUID), `scan_timestamp`, `scan_duration_ms`, `total_scanned`, `valid_symbols`, `buy_count`, `watch_count`, `rejected_count`, `status`.
- **Inserts**: One row inserted per complete scan run via `LatestScanService.persist_successful_scan`.

**Table**: `scan_snapshot_records`
- **Purpose**: Stores the individual stock results associated with a `scan_snapshot`.
- **Fields**: `scan_id` (Foreign Key), `symbol`, `recommendation` (BUY/WATCH/REJECTED), `score`, `close_price`, `sma50`, `sma200`, `rsi`, `macd`, `volume`, `reason`.
- **Inserts**: Iterates through `ScreenerResponse.analysis.items` and `ScreenerResponse.matches` to insert records. Bulk inserts are preferred.

## 3. Dashboard Retrieval
**Query**:
```sql
SELECT * FROM scan_snapshots ORDER BY scan_timestamp DESC LIMIT 1;
SELECT * FROM scan_snapshot_records WHERE scan_id = :scan_id;
```
- **Purpose**: Power the frontend UI via `GET /scanner/latest`.

## 4. Analytics & Backtesting (Agent Output)
**Tables**: `analysis_history`, `backtest_history`
- **Purpose**: Stores the historical LLM agent reasoning and mathematical backtest results for deeply analyzed stocks.
- **Interactions**: Inserted by `OrchestratorAgent._persist_analysis`.
