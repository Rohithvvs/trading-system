# Code Walkthrough

This document provides a chronological tour of the key files and classes that make up the Scanner Engine.

## 1. `backend/app/main.py`
- **Purpose**: Application entry point and scheduler configuration.
- **Key Sections**:
  - `lifespan`: Validates database schema and startup health of the scanner (`validate_startup_health`).
  - `scheduler`: Configures APScheduler. Contains commented-out jobs for automated scanning (`automated_screening_job`), indicating manual API triggering is currently preferred.
- **Calls Next**: `OrchestratorAgent.run_screener()` (if job is enabled).

## 2. `backend/app/routes/scanner.py`
- **Purpose**: Exposes REST endpoints for the frontend.
- **Key Functions**:
  - `@router.get("/latest")`: Fetches the most recent scan.
- **Calls Next**: `LatestScanService.get_latest_completed_scan()`.

## 3. `backend/app/agents/orchestrator_agent.py`
- **Purpose**: The conductor. Coordinates the scanner flow.
- **Class**: `OrchestratorAgent`
- **Key Functions**:
  - `run_screener`: Iterates through prioritized universes (NIFTY500, FNO).
  - `_run_screener_stage`: Passes symbols to the screener service, takes the top results, and passes them to downstream agents (`run_full`).
- **Calls Next**: `ScreenerService.screen_symbols_swing()`.

## 4. `backend/app/services/screener_service.py`
- **Purpose**: High-throughput data fetching and mathematical scoring.
- **Class**: `ScreenerService`
- **Key Functions**:
  - `screen_symbols_swing`: The main loop. Fetches data, concatenates DataFrames, calls bulk analysis, and iterates results.
  - `fetch_all_symbols`: Uses `asyncio.gather` and `MarketDataService` to build symbol DataFrames.
  - `_passes_broad_trend` & `_passes_data_quality`: Hard gatekeepers.
  - `_weighted_score`: Computes the final 0-100 score.
- **Calls Next**: `TechnicalAnalysisService.analyze_bulk_from_frame()`.

## 5. `backend/app/services/technical_analysis_service.py`
- **Purpose**: Vectorized indicator math.
- **Class**: `TechnicalAnalysisService`
- **Key Functions**:
  - `analyze_bulk_from_frame`: Takes a massive multi-index DataFrame and uses Pandas `.groupby().transform()` to calculate SMA, EMA, MACD, RSI, and Supertrend in C-optimized memory.
- **Returns**: Maps of symbols to `TechnicalAnalysisResult`.

## 6. `backend/app/agents/recommendation_agent.py` (Implied)
- **Purpose**: Final decision making on the shortlist.
- **Behavior**: Takes the technical score, fundamental data, news sentiment, and backtest results to output `BUY`, `WATCH`, or `REJECT`.

## 7. `backend/app/services/latest_scan_service.py`
- **Purpose**: Database persistence for the dashboard.
- **Class**: `LatestScanService`
- **Key Functions**:
  - `persist_successful_scan`: Saves `ScanSnapshot` and `ScanSnapshotRecord`.
  - `get_latest_completed_scan`: Retrieves formatted JSON for the UI.
