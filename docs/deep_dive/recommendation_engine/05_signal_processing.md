# Recommendation Engine: Signal Processing

Signal processing ensures that incoming data from various sources is validated, cleaned, and transformed into a format that the scoring engine can safely consume.

## 1. Handling OHLCV Market Data
**Cleaning & Validation:**
When bulk OHLCV data arrives for analysis, `TechnicalAnalysisService.analyze_bulk_from_frame()` performs several cleaning steps:
- Converts the list of `OHLCVPoint` objects into a Pandas DataFrame.
- Assigns a multi-index `(timestamp, symbol)`.
- Sorts by timestamp to ensure chronological integrity.
- Uses `.ffill().bfill()` in backtesting (`BacktestService.run()`) to handle missing candle data seamlessly without raising exceptions.

## 2. Handling Missing Fundamental Data
**Recovery/Fallback:**
The `FundamentalAnalysisAgent` requests data via `yfinance`. Often, Indian equities or specific tickers may return 404 errors or missing keys.
- **Transformation:** It safely handles `None` values and transforms fractional percentages (e.g., `0.15`) into whole percentages (`15.0%`).
- **Fallback:** If the API fails entirely or returns 404, it returns a `_fallback_result()` where `fundamental_score = 0.0`. This ensures a missing API doesn't crash the pipeline, rendering the fundamental component neutral.

## 3. Resolving Signal Conflicts (Technical vs AI)
Different sub-systems might produce conflicting indicators.
**Example Conflict:** 
Technical analysis produces a high `score` of 85 ("bullish"). However, breaking news is catastrophic, leading `LLMService` to return a `sentiment_score` of `-0.95`.

**Transformation via Dynamic Weights:**
The `RecommendationService` observes the highly negative news (-0.95) and triggers the **Catalyst Regime**. It drastically reduces the Technical weight (from 50% to 20%) and increases the News weight (from 0% to 30%). 
Because the News score is normalized to -95 (out of 100) and given 30% weight, it deeply drags down the final score, successfully overriding the Bullish technical signal and resulting in a `REJECT`.

## 4. Structuring and Standardizing
Every engine outputs a differently scaled metric:
- Technicals output 0 to 100.
- Sentiment outputs -1.0 to 1.0.
- Fundamentals output -1.0 to 1.0.
- Backtesting outputs raw percentage returns (e.g., 34.5%).

The `RecommendationService` processes these signals by standardizing them all into a **0 to 100 (or -100 to 100)** scale before applying weights:
- `raw_tech` = `technical_score` (0 to 100)
- `raw_backtest` = min(max((return * 4), -20), 100)
- `raw_news` = `sentiment_score * 100` (-100 to 100)
- `raw_fund` = `fundamental_score * 100` (-100 to 100)
