# Learning Notes for New Developers

Welcome to the Backtesting Engine. This engine is highly mathematical and uses data structures that differ slightly from the rest of the application.

## 1. Architecture Decisions
- **Why use Pandas `iterrows()` instead of vectorization for trades?**
  While indicators are computed using fast NumPy/C vectorization, the actual simulation of buying, holding, and selling relies on a state machine (`position_entry`). Doing path-dependent state machine logic (you can't enter a trade if you are already in one) natively in vectorized Pandas is notoriously complex (requiring cumulative sums and shift manipulations). Since we only backtest the final shortlist of ~10 stocks, the performance hit of a 250-row Python loop is negligible (0.05 seconds). Readability won over micro-optimization.
- **Why pass `candles` down instead of fetching in the service?**
  Dependency Injection. The Backtester should be a pure math function: `f(data) = result`. If it fetched its own data, testing it would require mocking API calls and databases. By passing `candles` into `run()`, you can easily unit test the Backtester with a hardcoded list of `OHLCVPoint` objects.

## 2. Common Misconceptions
- **"The Backtest calculates the Scanner Score."**
  False. The Backtester runs *after* the scanner. The scanner score is based purely on point-in-time indicators. The backtester simulates holding positions over history.
- **"The Backtest handles API errors."**
  False. If the API fails, it's the Orchestrator's job to handle it. The Backtester just looks at the list size.

## 3. Interview / Self-Check Questions
1. **How is CAGR calculated?**
   *Answer*: `(total_return) * (252 / total_candles)`. Assuming 252 trading days in a year.
2. **What happens if a stock drops 50% while holding a position?**
   *Answer*: The engine tracks `peak_equity`. Drawdown is calculated as `((peak_equity - equity) / peak_equity) * 100`. The max value of this over the entire run becomes the `max_drawdown`.
3. **If I want to change the RSI threshold from 50 to 60, where do I do it?**
   *Answer*: In `BacktestService.run()`, update `row["rsi"] >= 60` in the `bullish_entry` boolean check.

## 4. Best Practices for Extending
- If you add a new indicator to the strategy, add it using the `ta` library *before* the `iterrows()` loop.
- If you change the output schema (e.g., adding `Sortino Ratio`), you must update `BacktestResult` in `schemas/analysis.py`, and `BacktestHistory` in `models/analysis.py`, and the SQLAlchemy `_persist_analysis()` method in the `OrchestratorAgent`.

## 5. Recommended Learning Order
1. Read `backend/app/schemas/analysis.py` to understand the `BacktestResult` shape.
2. Read `backend/app/services/backtest_service.py` top to bottom. Focus on how the Pandas DataFrame is built, and how the `bullish_entry` boolean is evaluated.
3. Finally, read `backend/app/agents/orchestrator_agent.py` to see where `to_thread(run_backtest)` is launched.
