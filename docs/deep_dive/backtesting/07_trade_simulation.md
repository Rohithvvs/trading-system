# Trade Simulation

The trade simulation loop runs sequentially across the historical timeframe. It tracks virtual capital and virtual trades in memory.

## Virtual Portfolio Initialization
When `BacktestService.run()` begins, it initializes the virtual portfolio:
```python
equity = 100000.0  # ₹1,00,000 starting cash
peak_equity = equity
max_drawdown = 0.0
position_entry = None
```
The simulation does *not* track discrete shares (e.g., buying 100 shares of Reliance). Instead, it assumes 100% of the portfolio `equity` is deployed into every single trade.

## Position Opening (Virtual Order)
When `bullish_entry` is True and `position_entry` is None:
- `position_entry = float(row["close"])`
- The system assumes perfect execution at the exact closing price of the day the signal was generated.
- No brokerage, slippage, or taxes are subtracted at entry in this implementation.

## Position Closing (Virtual Execution)
When `exit_signal` is True and `position_entry` is not None:
- `exit_price = float(row["close"])`
- The system calculates the un-leveraged percentage return of the trade:
  `trade_return = ((exit_price - position_entry) / position_entry) * 100`

## Portfolio Updates
Immediately after a trade closes, the portfolio equity is compounded by the trade return:
- `equity *= 1 + (trade_return / 100)`

*Numerical Example*:
- Start: ₹100,000
- Trade 1: Bought at ₹100, Sold at ₹110. Return: +10%.
- New Equity: `100,000 * 1.10 = 110,000`
- Trade 2: Bought at ₹200, Sold at ₹180. Return: -10%.
- New Equity: `110,000 * 0.90 = 99,000`

## Drawdown Tracking
After every closed trade, the engine updates the highest water mark (`peak_equity`) and calculates the drawdown from that peak.
- `peak_equity = max(peak_equity, equity)`
- `drawdown = ((peak_equity - equity) / peak_equity) * 100`
- `max_drawdown = max(max_drawdown, drawdown)`

## Trade History Generation
Every closed trade is appended as a dictionary to the `trades` list. 
At the very end of the DataFrame iteration, if a trade is still open (`position_entry is not None`), the system forces a "Mark to Market" exit using the absolute last available closing price, ensuring the final equity curve reflects the current open profit/loss.
