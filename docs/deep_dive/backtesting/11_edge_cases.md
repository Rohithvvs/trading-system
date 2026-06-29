# Edge Cases

The Backtesting Engine processes raw OHLCV data. Due to market mechanics and API quirks, this data is rarely perfect. Handling edge cases robustly prevents the engine from generating impossible returns.

## 1. Missing Historical Candles
- **What happened**: A random Tuesday is missing from the dataset.
- **Why**: Exchange data glitch or broker API failure.
- **Expected behavior**: Calculate indicators without throwing errors, assuming price remained flat.
- **Actual implementation**: `BacktestService` uses Pandas `ffill()` (Forward Fill). If Tuesday is missing, Monday's Close price is carried forward.
- **Recovery**: Automatic.
- **Developer debugging**: Check if the DataFrame contains identical consecutive rows in `close`.

## 2. Duplicate Candles
- **What happened**: Two candles exist for the same date.
- **Why**: Database upsert race conditions upstream.
- **Expected behavior**: Only use one candle per date.
- **Actual implementation**: If duplicate timestamps are passed in the `OHLCVPoint` list, the `sort_values("timestamp")` aligns them, but doesn't explicitly drop them. This could cause the indicators to tick twice on the same day. Upstream DB constraints (`UNIQUE(symbol, timestamp)`) prevent this from reaching the backtester.
- **Recovery**: Prevented upstream.
- **Developer debugging**: Run `SELECT count(*), timestamp FROM daily_candles GROUP BY timestamp HAVING count(*) > 1`.

## 3. Incorrect Timestamps
- **What happened**: A timestamp is set in the future or 1970.
- **Why**: Epoch parsing errors upstream.
- **Expected behavior**: Ignore or sort correctly.
- **Actual implementation**: The engine runs `frame.sort_values("timestamp")`. If a 1970 date exists, it goes to the start of the dataframe and usually fails the `slow_window` skip check anyway.
- **Recovery**: Automatic ordering.
- **Developer debugging**: Look for massive gaps in the `equity_curve` dates.

## 4. Stock Splits & 5. Bonus Issues
- **What happened**: A stock drops from ₹1000 to ₹500 overnight.
- **Why**: Corporate action (2:1 split).
- **Expected behavior**: The backtest must use split-adjusted data, otherwise it will register a 50% loss.
- **Actual implementation**: The FYERS API provides split-adjusted historical data by default. The engine relies purely on this upstream adjustment. It does not perform manual split detection.
- **Recovery**: Upstream API handles it.
- **Developer debugging**: If an inexplicable -50% trade exists, check NSE corporate action announcements for that date.

## 6. Market Holidays
- **What happened**: No data for Saturday/Sunday or Public Holidays.
- **Why**: Markets are closed.
- **Expected behavior**: Ignore the gap and treat Friday and Monday as contiguous trading days.
- **Actual implementation**: Pandas `EMAIndicator` operates on the index row number, not the calendar date gap. Friday is `n`, Monday is `n+1`. The math works perfectly without requiring calendar imputation.
- **Recovery**: Native Pandas handling.
- **Developer debugging**: None required.

## 7. Missing Volume
- **What happened**: Volume is 0 for a trading day.
- **Why**: Illiquid stock hitting upper circuit, or API glitch.
- **Expected behavior**: Do not enter a trade if there is no liquidity.
- **Actual implementation**: `bullish_entry` requires `volume >= max(avg_volume, 1) * 0.8`. If volume is 0, this evaluates to `False`. The trade is rejected.
- **Recovery**: Automatic rejection of entry.
- **Developer debugging**: Inspect the `volume` column in the Pandas DataFrame.

## 8. Corrupted Data
- **What happened**: `close` price is `NaN` or 0.
- **Why**: Severe API failure upstream.
- **Expected behavior**: Do not crash. Do not generate infinity returns.
- **Actual implementation**: `ffill()` attempts to patch `NaN`. If the entire column is 0, indicators like RSI will evaluate to 0, preventing `bullish_entry` (which requires `rsi >= 50`).
- **Recovery**: Trades are simply not taken.
- **Developer debugging**: Check if `trade_count == 0`.

## 9. Very Short History & 18. Partial Historical Data
- **What happened**: Only 20 days of data provided.
- **Why**: Recent IPO.
- **Expected behavior**: Do not run the backtest.
- **Actual implementation**: `if len(candles) < 35: return _empty_result()`.
- **Recovery**: Graceful abort. Verdict = `insufficient`.
- **Developer debugging**: Check `len(candles)` passed into `run()`.

## 10. Strategy Generates No Trades
- **What happened**: The stock never meets all 5 entry conditions simultaneously.
- **Why**: Stock has been in a severe downtrend for years (e.g., Yes Bank).
- **Expected behavior**: Return 0 return, not a crash.
- **Actual implementation**: `position_entry` never triggers. `trade_count` remains 0. Verdict becomes `insufficient`.
- **Recovery**: Automatic.
- **Developer debugging**: Relax the entry conditions (e.g., drop the volume check temporarily) to see if trades trigger.

## 11. Continuous Losses
- **What happened**: The strategy takes 10 trades and loses all 10.
- **Why**: Whipsaw market conditions (choppy range).
- **Expected behavior**: Calculate the heavy drawdown accurately.
- **Actual implementation**: `equity` drops continuously. `win_rate` goes to 0.0. `verdict` becomes `mixed`. The Recommendation Agent will likely reject the stock based on this.
- **Recovery**: Correct mathematical operation.
- **Developer debugging**: Check `profit_factor`. It should be 0.0.

## 12. Extreme Volatility
- **What happened**: A stock goes up 20% in one day, then down 20%.
- **Why**: Earnings shock or pump-and-dump.
- **Expected behavior**: Accurately track PnL based on closing prices.
- **Actual implementation**: The engine only acts on the `close` price. Intraday spikes are ignored in `swing` mode.
- **Recovery**: Automatic.
- **Developer debugging**: This is why `max_drawdown` tracking is vital. Check if `max_drawdown` exceeds 30%.

## 13. Gap-Up Openings & 14. Gap-Down Openings
- **What happened**: Prices jump overnight bypassing limit orders.
- **Expected behavior**: Register the entry/exit at the close of the day the signal was generated.
- **Actual implementation**: The simulation assumes execution at the exact `close` of the signal day. If the gap happens the *next* day, the profit/loss is fully captured when the trade eventually closes.
- **Recovery**: Mathematical tracking.
- **Developer debugging**: Look at `pnl_percent` on individual trades.

## 15. Database Failure, 16. Redis Unavailable, 17. API Timeout
- **What happened**: Infrastructure components fail upstream.
- **Why**: Network outages.
- **Expected behavior**: The backtest degrades safely.
- **Actual implementation**: The Orchestrator handles these errors. If it passes an empty `candles` list to the Backtester due to these failures, the Backtester immediately returns `_empty_result()`.
- **Recovery**: Graceful fallback.
- **Developer debugging**: Look for connection timeout errors in `logs/latest_scan.log`.
