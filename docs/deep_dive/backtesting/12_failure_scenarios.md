# Failure Scenarios

## 1. Backtest Crashes
- **What happened**: `BacktestService.run()` throws an unhandled Exception (e.g., `KeyError` or `TypeError`).
- **Why**: The `ta` library (Technical Analysis) occasionally throws errors if the Pandas DataFrame contains `NaN` values that cannot be interpolated, or if the `close` column is missing.
- **Expected behavior**: The individual backtest fails without crashing the entire scanning orchestrator.
- **Actual implementation**: `OrchestratorAgent._analyze_symbol_post_bulk()` wraps the backtest agent call in a `try/except` block. If it fails, it catches the exception and returns a dummy `BacktestResult` with `strategy_name="error_fallback"`, returning `0.0` for all metrics and `"Failed"` as the verdict.
- **Recovery**: Isolated failure. The overall scan completes successfully for other symbols.
- **Monitoring/Alerts**: Monitor backend logs for `"Backtest agent failed for %s in %s mode: %s"`.

## 2. Wrong Results / Wrong Metrics
- **What happened**: `win_rate` shows >100%, or `max_drawdown` is positive instead of negative.
- **Why**: Mathematical logic error in the `BacktestService` loops.
- **Actual implementation**: Metrics are strictly calculated. `win_rate` is `(len(wins) / trade_count) * 100`. Drawdown is calculated as `((peak_equity - equity) / peak_equity) * 100`. 
- **Developer debugging**: Write a pytest using a mocked `OHLCVPoint` array where you manually verify the exact trades that should happen.

## 3. Missing Trades
- **What happened**: `trade_count` is unexpectedly 0 for a stock that clearly trended.
- **Why**: The entry condition in `BacktestService` is highly restrictive: `bullish_entry = bool(row["close"] > row["ema_fast"] and row["ema_fast"] > row["ema_slow"] and row["macd"] > row["macd_signal"] and row["rsi"] >= 50 and row["volume"] >= max(row["avg_volume"] or 0, 1) * 0.8)`. All 5 conditions MUST align on the exact same candle.
- **Recovery**: This is not a failure, but a design choice. Adjust the strategy parameters if it's too restrictive.

## 4. Duplicate Trades
- **What happened**: A single symbol registers multiple active trades at the same time.
- **Why**: State machine bug.
- **Actual implementation**: Prevented by the `position_entry is None` check. The engine only allows 1 active trade at a time. It will not enter a new trade until the current one exits (`elif position_entry is not None and exit_signal`).

## 5. Incorrect Portfolio
- **What happened**: The `total_return` does not match the sum of individual trade percentages.
- **Why**: Compounding. 
- **Actual implementation**: The engine starts with `equity = 100000.0`. Each trade return compounds: `equity *= 1 + (trade_return / 100)`. Thus, five 10% wins do not equal 50% return, they equal a ~61% return. This is mathematically correct.
- **Monitoring**: The `equity_curve` array provides the exact progression of the portfolio for frontend charting.
