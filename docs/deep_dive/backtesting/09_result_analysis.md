# Result Analysis

After the simulation loop completes, the engine analyzes the generated trades to build reports and final verdicts.

## 1. How Final Reports are Generated
The `BacktestService` aggregates the raw data into presentation-ready fields within the `BacktestResult` Pydantic schema:
- **`equity_curve`**: An array of `{"label": Date, "equity": Value}` dictionaries, truncated to the last 50 points to save payload size for the frontend chart.
- **`monthly_returns`**: A heatmap dictionary `{"YYYY-MM": sum(pnl_percent)}`. It parses the string dates from the `trades` list, groups them by month, and sums the returns.
- **`best_trade` & `worst_trade`**: Extracts the maximum and minimum elements from the `trades` array based on `pnl_percent`.

## 2. Verdict Generation (Selecting Best Strategies)
The engine assigns a qualitative string `verdict` to the backtest.
- **`favorable`**: Issued if `total_return > 0` AND `win_rate >= 45` AND `profit_factor >= 1.0`.
- **`mixed`**: Issued if trades occurred, but the metrics did not meet the favorable threshold (e.g., a losing strategy).
- **`insufficient`**: Issued if the stock had less than 35 days of history, or generated zero trades during the backtest window.

## 3. How Recommendations Use Backtesting
The `BacktestResult` is returned to the `OrchestratorAgent`.
The Orchestrator then passes this result into the `RecommendationAgent`.
The Recommendation Agent uses the backtest as a **historical proof-of-concept**:
- If the technical scanner says `BUY` today, but the `BacktestResult` verdict is `mixed` (meaning this specific strategy historically loses money on this specific stock), the Recommendation Agent may downgrade the signal to `WATCH` or `REJECT`.
- If the verdict is `favorable`, it boosts confidence in the technical signal, confirming that the stock behaves predictably according to trend-following rules.
