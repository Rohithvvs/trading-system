# Signal Generation

The Backtesting Engine (`BacktestService`) relies on strict mathematical conditions to generate trade signals. It does not use external ML models or fundamental data; it purely evaluates the Pandas DataFrame representing historical OHLCV data.

## Entry Signals (`BUY`)
An entry signal (`bullish_entry`) is triggered when all five of the following conditions align on the exact same daily candle:

1. **Price Momentum**: `close > ema_fast` (Price is above the short-term EMA).
2. **Trend Alignment**: `ema_fast > ema_slow` (Short-term trend is above the long-term trend).
3. **MACD Confirmation**: `macd > macd_signal` (MACD histogram is positive, showing accelerating momentum).
4. **RSI Strength**: `rsi >= 50` (Stock is in bullish territory, not oversold/bearish).
5. **Volume Breakout**: `volume >= avg_volume * 0.8` (Volume is at least 80% of the 20-day average, ensuring sufficient liquidity).

*Numerical Example*:
- Close: ₹105
- EMA Fast (20): ₹102
- EMA Slow (50): ₹98
- MACD: 1.2, MACD Signal: 0.9
- RSI: 55
- Volume: 1,000,000 (Avg: 800,000)
- **Result**: `bullish_entry = True`. The engine simulates buying at ₹105.

## Exit Signals (`SELL`)
An exit signal (`exit_signal`) is triggered if *any* of the following conditions occur while in an active trade:

1. **Price Breakdown**: `close < ema_fast` (Price closes below the short-term support).
2. **MACD Reversal**: `macd < macd_signal` (Momentum flips negative).
3. **RSI Weakness**: `rsi < 45` (RSI drops into bearish territory).

*Numerical Example*:
- Stock was bought at ₹105. It rallies to ₹120.
- On day 10, the stock drops to ₹117.
- `ema_fast` is ₹118.
- Because `close (117) < ema_fast (118)`, `exit_signal = True`. The engine simulates selling at ₹117, securing a ₹12 profit per share (11.4% return).

## HOLD Decisions
There is no explicit `HOLD` command in the code. A `HOLD` is implicitly executed when the engine is actively in a trade (`position_entry is not None`) and the `exit_signal` evaluates to `False`. During a hold, the stock price can fluctuate wildly, but until a hard exit condition is met, the engine continues to hold.

## REJECT / Ignore Decisions
If a `bullish_entry` triggers while the engine is *already* in a trade, it is completely ignored. The engine only supports a single active position at a time per symbol. There is no pyramiding or adding to winning positions. Similarly, if an `exit_signal` fires while *not* in a trade, it is completely ignored.
