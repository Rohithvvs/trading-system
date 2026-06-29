# Recommendation Engine: Failure Scenarios

## 1. Wrong Recommendation
- **Description:** A stock receives a `BUY`, but immediately tanks in the next session.
- **Root Cause:**
  - Standard lagging nature of technical indicators (e.g. moving averages pointing up, but a sudden institutional dump occurs).
  - Positive news sentiment incorrectly evaluated by the LLM.
- **Recovery (System):** The `TradePlan` always includes a strict `stop_loss`. The paper trading module will exit if the support is broken.
- **Recovery (Dev):** Analyze the `TechnicalAnalysisService` hard filters and adjust the `score` thresholds (currently 72) or the Risk-Reward gate (currently 1.25) in `OrchestratorAgent`.

## 2. No Recommendation (System returning REJECT for everything)
- **Description:** During a massive bull run, the engine refuses to output a single `BUY`.
- **Root Cause:**
  - The `Strict Buy Gate` is blocking them due to `mock_warning=True` (API token expired).
  - The `ScreenerService` broad trend eligibility is failing because index/market data is misconfigured.
  - Candlestick data fetch size is too small, failing the `minimum_swing_candles_met` gate.
- **Recovery:** Re-authenticate Fyers. Ensure SQLite cache (`candle_cache.db`) is populated with at least 300 days of history.

## 3. Recommendation Delay (Scan takes > 30 seconds)
- **Description:** The user clicks "Run Full Analysis" and the UI times out.
- **Root Cause:**
  - Deep backtesting across 500 stocks sequentially instead of vectorized or concurrent processing.
  - LLM Rate limits throttling the `NewsAnalysisAgent`.
- **Recovery:** The `OrchestratorAgent` utilizes `asyncio.gather` for concurrent network I/O. For heavy math, `TechnicalAnalysisService` relies on vectorized Pandas operations (`analyze_bulk_from_frame`). Check if the batch size is too large for the available CPU.

## 4. Inconsistent Recommendations
- **Description:** Running the scan at 10:00 AM outputs BUY, but running it at 10:05 AM outputs WATCH for the same stock without significant price change.
- **Root Cause:**
  - News headlines refreshed and the LLM evaluated a newly published article as bearish.
  - The 20-period volume average ticked down, pushing the R/R ratio just below 1.25, triggering a downgrade.
- **Recovery:** By design, the engine is highly reactive. If more stability is desired, smoothing functions on volume or a time-decay on news sentiment scores would need to be implemented.
