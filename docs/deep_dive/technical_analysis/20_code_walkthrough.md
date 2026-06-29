# Technical Analysis: Code Walkthrough

This document provides a line-by-line structural walkthrough of the files that make up the Technical Analysis Engine pipeline.

---

## 1. `backend/app/services/technical_analysis_service.py`

### Purpose
The core mathematical brain of the system. It takes raw price data, applies vectorized formulas, and outputs a technical score and signal.

### Classes
* **`SupertrendPoint` (Dataclass):** A simple struct holding the `value` (float) and `direction_up` (bool) for a single point in time.
* **`TechnicalAnalysisService`**: The main service class.

### Methods
* **`__init__()`**: Initializes the logger.
* **`get_required_candle_count(mode)`**: 
  * Returns `40` for intraday, `240` for swing. 
  * Called by `ScreenerService` to determine how much history to fetch from the DB.
* **`analyze_bulk(universe_candles, mode)`**: 
  * The legacy method for processing dictionaries of `OHLCVPoint` lists. Largely superseded by the frame-based method for memory efficiency.
* **`analyze_bulk_from_frame(frame, mode)`**: 
  * **The most important method in the engine.**
  * Takes a MultiIndex Pandas DataFrame.
  * Groups by symbol, runs vectorized transforms (`ewm`, `rolling`) for all indicators.
  * Loops through the tail of the data to calculate the final `score` and `signal`.
  * Returns a dictionary mapping `symbol -> TechnicalAnalysisResult`.
* **`_log_analysis_decision(...)`**: 
  * Emits the exact indicators, failed filters, and final score to the logger for deterministic debugging.
* **`_calculate_supertrend(...)`**: 
  * Calculates True Range, ATR, and the upper/lower bands. Returns a Series of `SupertrendPoint`s.
* **`_is_hammer(...)` / `_is_gravestone_doji(...)`**: 
  * Boolean structural checks based on candle body and wick proportions.

### Call Chain
* **Who calls it:** `ScreenerService.screen_symbols_swing()` calls `analyze_bulk_from_frame()`.
* **What it calls next:** It relies on Pandas and the `ta` library for math. Once complete, it returns control to the Screener.
* **Role:** Pure computation. No I/O, no database access.

---

## 2. `backend/app/services/screener_service.py`

### Purpose
The orchestrator. It acts as the bridge between the raw data in the database and the pure math in the Technical Engine.

### Classes
* **`TokenBucketRateLimiter`**: Utility for managing API throughput.
* **`ScreenerService`**: The main orchestrator class.

### Methods (Relevant to TA Engine)
* **`screen_symbols_swing(symbols, lookback_window)`**: 
  * The main entry point. 
  * Fetches historical data via `asyncio.gather()`.
  * Fills missing gaps using `df.ffill()`.
  * Concatenates everything into a single `combined_frame`.
  * Passes the frame to `TechnicalAnalysisService.analyze_bulk_from_frame()`.
  * Loops over the results, calling `_process_single_symbol()` to finalize scoring.
* **`_process_single_symbol(...)`**: 
  * Takes the Technical Engine's output and validates data quality (`_passes_data_quality`) and broad trend (`_passes_broad_trend`).
* **`_weighted_score(...)`**: 
  * Calculates the final `screener_score`, combining the technical score with dynamic volume lift.

### Call Chain
* **Who calls it:** A cron job, a REST API endpoint, or the `LatestScanService`.
* **What it calls next:** `MarketDataService` (for data), `TechnicalAnalysisService` (for math), and `app.core.log_manager` (for telemetry).
* **Role:** Memory management, data cleaning, and final business logic filtering.

---

## 3. `backend/app/schemas/technical_analysis.py` (Assumed Schema Definitions)

*(Note: These schemas are imported into the engine from `..schemas`)*

### Purpose
Defines the strictly typed data structures passed between services.

### Key Classes
* **`AnalysisMode` (Enum):** Defines `swing` vs `intraday`.
* **`OHLCVPoint` (BaseModel):** Defines the exact structure of a single candle (timestamp, open, high, low, close, volume).
* **`TechnicalAnalysisResult` (BaseModel):** The output of the Technical Engine. Contains `signal`, `score`, `indicators` (dict), and a human-readable `summary`.
* **`ScreenerConditionResult` (BaseModel):** The final output of the Screener. Contains the `screener_score` and the `matched` boolean.

### Role
Ensures type safety across the pipeline. By using Pydantic/dataclasses, the system guarantees that if the Technical Engine expects a `close` value, it will always be a float, preventing runtime math crashes.
