# Learning Notes for New Developers

Welcome to the Scanner Engine. This document contains notes, architectural context, and common gotchas to help you onboard quickly.

## 1. Most Important Concepts
- **The Funnel Approach**: Do not run LLMs or external API calls (News, Fundamentals) on all 500 stocks. The Scanner is the wide mouth of the funnel. It uses cheap, fast math (Pandas) to filter 500 down to 10. Only those 10 get the expensive, slow Agent treatment.
- **Vectorization over Iteration**: In `TechnicalAnalysisService`, never use a Python `for` loop to calculate indicators for a list of stocks. We use Pandas `.groupby("symbol").transform()`. It pushes the looping down to C-level code, making it orders of magnitude faster.
- **Memory Management**: Loading 1 year of data for 500 stocks consumes a lot of RAM. Watch out for memory leaks. Always use raw DataFrames for bulk processing, avoid converting them to Pydantic objects (`OHLCVPoint`) until absolutely necessary (e.g., passing tail candles to scoring). Use `del` to explicitly free large DataFrames.

## 2. Common Misconceptions
- **"The Scanner runs live every second"**: False. The scanner uses EOD (End of Day) swing data primarily. Intraday loops exist, but the heavy deep scan is designed for batch processing, not high-frequency tick-by-tick evaluation.
- **"We overwrite previous scans"**: False. Historically this might have been true, but the architecture now uses `scan_snapshots` and `scan_snapshot_records` to preserve every run immutably.
- **"FYERS data is perfect"**: False. You will encounter missing days, zero volumes, and split adjustments. This is why `_passes_data_quality` exists. Never trust raw API data without validating it.

## 3. Architecture Decisions
- **Why PostgreSQL for caching instead of Redis?** 
  Candle data is structured and relational. We need to query ranges, fill gaps, and do complex continuity checks. Postgres handles this perfectly. Redis is better for simple key-value TTLs (like API rate limit locks), not time-series financial data arrays.
- **Why fallback to yfinance?**
  FYERS tokens expire daily and require manual user login due to broker regulations. If the token expires while the user is asleep, the scheduled jobs would fail. `yfinance` provides a degraded but functional fallback.

## 4. Interview / Self-Check Questions
Before modifying the scanner, ensure you can answer these:
1. If I change the `sma_50` calculation, do I change it in the `ScreenerService` or `TechnicalAnalysisService`? *(Answer: TechnicalAnalysisService)*
2. What happens if a stock has 100 days of history but we require a 200 SMA? *(Answer: It is safely rejected in `_passes_data_quality`)*
3. Why do we forward-fill (`ffill`) missing days? *(Answer: To ensure the Pandas DataFrame index is perfectly aligned across all 500 stocks so vectorized math works correctly.)*

## 5. Recommended Learning Order
1. Trace `backend/app/routes/scanner.py` to see how the frontend consumes data.
2. Read `ScreenerService.screen_symbols_swing` to understand the main loop.
3. Read `TechnicalAnalysisService.analyze_bulk_from_frame` to understand Pandas vectorization.
4. Review `MarketDataService` to understand how PostgreSQL is used as an intelligent time-series cache.
