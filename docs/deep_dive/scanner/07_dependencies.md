# Dependencies

The Scanner Engine operates as a central nervous system within the backend and relies on several critical internal and external dependencies.

## External Dependencies

1. **FYERS API**
   - **Purpose**: The primary market data provider for historical OHLCV candles (Daily and Intraday) and Real-time Last Traded Price (LTP).
   - **Integration**: Accessed via `FyersService`. Requires a valid access token stored in the database.
   - **Failure Impact**: If FYERS is down or rate limits are exceeded, the scanner falls back to `yfinance` (Yahoo Finance), or fails if the fallback also fails.

2. **yfinance (Yahoo Finance)**
   - **Purpose**: Fallback data provider.
   - **Integration**: `fallback_fetch_yfinance` in `ScreenerService`.
   - **Failure Impact**: Used only when FYERS fails. Slower and less reliable for Indian markets.

3. **News APIs**
   - **Purpose**: Used by the `NewsAnalysisAgent` on shortlisted stocks to determine sentiment.
   - **Failure Impact**: Returns a neutral sentiment score (0.5) gracefully if the API fails or is unconfigured.

## Internal Dependencies (Infrastructure)

1. **PostgreSQL**
   - **Tables Required**:
     - `daily_candles`, `intraday_candles` (Cache layer).
     - `scan_snapshots`, `scan_snapshot_records` (Persistence layer).
     - `watched_stocks`, `analysis_history`, `backtest_history` (Historical context).
   - **Failure Impact**: The scanner cannot function without the database. It will crash on startup if Alembic migrations are not at `head`.

2. **APScheduler**
   - **Purpose**: Manages background cron jobs (`automated_screening_job`).
   - **Configuration**: Resides in `backend/app/main.py`.

3. **Pandas & ta (Technical Analysis Library)**
   - **Purpose**: High-performance, vectorized computation of technical indicators.
   - **Failure Impact**: Core dependency. Without them, the math engine cannot process the 500+ stocks efficiently.

## Modules That Depend on the Scanner

1. **Frontend Dashboard**
   - Relies on `GET /scanner/latest` to display trading opportunities to the user.

2. **Orchestrator Agent**
   - Relies on the `ScreenerService` to reduce the universe of stocks to a manageable shortlist before invoking expensive LLM/News/Fundamental agents.

3. **Scan Diagnostics & Telemetry**
   - Observability modules rely on the scanner's execution loops to emit performance metrics (memory usage, execution time, failure rates).
