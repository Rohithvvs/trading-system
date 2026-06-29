# Technical Analysis Engine: Architecture

The Technical Analysis Engine in this repository is built for high-performance, vectorized computation of market indicators. It sits between the data acquisition layer and the signal combination/screening layer.

## Complete Architecture Overview

The core of the Technical Analysis Engine resides within `backend/app/services/technical_analysis_service.py`. It leverages the `ta` library (specifically `ta.momentum`, `ta.trend`, and `ta.volume`) for standard indicators and implements custom logic for complex, multi-condition indicators (like Supertrend and Candlestick patterns).

```mermaid
graph TD
    MD[Market Data Service<br/>& Candle Store] --> |OHLCV Data via DataFrame| SS[Screener Service]
    SS --> |DataFrame<br/>Batch Symbols| TAS[Technical Analysis Service]
    
    subgraph Technical Analysis Service
        VM[Vectorized Math<br/>Pandas GroupBy]
        TA_LIB[TA Library<br/>MACD, RSI, EMA, SMA, VWAP]
        CUSTOM[Custom Logic<br/>Supertrend, Hammer, Doji]
        SCORE[Scoring Engine<br/>0 to 100]
        SIGNAL[Signal Generator<br/>Bullish/Neutral/Bearish]
        
        VM --> TA_LIB
        VM --> CUSTOM
        TA_LIB --> SCORE
        CUSTOM --> SCORE
        SCORE --> SIGNAL
    ]
    
    SIGNAL --> |TechnicalAnalysisResult| SS
    SS --> |ScreenerConditionResult| OUTPUT[Trading Logic / UI]
```

## Core Services

### `TechnicalAnalysisService` (`technical_analysis_service.py`)
The primary engine responsible for all mathematical calculations. 
- **Roles:**
  - Ingests bulk OHLCV data (either as a dictionary of `OHLCVPoint` lists or directly as a MultiIndex Pandas DataFrame).
  - Calculates indicators in two modes: `AnalysisMode.intraday` and `AnalysisMode.swing`.
  - Determines candlestick patterns (Hammer, Gravestone Doji).
  - Assigns a numerical score based on a weighted sum of technical conditions.
  - Emits a final signal (`bullish`, `neutral`, `bearish`).

### `ScreenerService` (`screener_service.py`)
Acts as the consumer and orchestrator of the `TechnicalAnalysisService`.
- **Roles:**
  - Fetches historical market data (`MarketDataService`, `FyersService`).
  - Ensures data quality and continuity (handling missing candles).
  - Builds the canonical MultiIndex DataFrame and passes it to `TechnicalAnalysisService.analyze_bulk_from_frame`.
  - Takes the resulting `TechnicalAnalysisResult` and applies further broad trend filters and volume filters.
  - Calculates the final `screener_score`.

### `MarketDataService` & `FyersService`
- **Roles:** Provide the raw OHLCV inputs required by the Technical Analysis Engine. They handle API rate limits, database caching (`candle_cache.db`), and data backfilling.

## Helper and Utility Methods (within `TechnicalAnalysisService`)

- `get_required_candle_count(mode)`: Defines the minimum warmup period (e.g., 240 candles for swing mode to calculate the SMA 200).
- `_calculate_supertrend(frame, period, multiplier)`: Custom implementation of the Supertrend indicator, returning a pandas Series of `SupertrendPoint` objects (value and direction).
- `_is_hammer(candle)`: Detects a bullish Hammer candlestick pattern based on body size and wick proportions.
- `_is_gravestone_doji(candle)`: Detects a bearish Gravestone Doji based on body size and upper wick length.
- `_log_analysis_decision(...)`: Structured logging utility that records the exact indicator values, failed filters, and final score for deterministic debugging.

## Indicator Modules

The engine calculates the following indicators using a mix of the `ta` library and native Pandas vectorized functions (`ewm`, `rolling`):

1. **Trend Indicators:** EMA (9, 20, 50), SMA (20, 30, 50, 100, 200), MACD, Supertrend.
2. **Momentum Indicators:** RSI (14-period).
3. **Volume Indicators:** VWAP, Volume Trend (Expanding vs. Stable).
4. **Price Action:** Support/Resistance (20-day rolling min/max), Higher-Highs/Higher-Lows (HH/HL) structure checks, Candlestick patterns (Hammer, Doji).

## Dependencies

- **Pandas (`pd`)**: The backbone of the engine. Used extensively for DataFrame manipulation, grouping (`groupby(level="symbol")`), and vectorized math.
- **ta (`ta.momentum`, `ta.trend`, `ta.volume`)**: External library used primarily for specific indicator imports, though the codebase relies heavily on manual Pandas `ewm` implementations for performance.
- **psutil / os**: Used for memory auditing (`get_rss_mb()`) during large batch processing.
- **Internal Schemas**: `AnalysisMode`, `OHLCVPoint`, `TechnicalAnalysisResult`, `SupertrendPoint`.
- **Logger**: Uses `app.utils.get_logger` for detailed operational telemetry.
