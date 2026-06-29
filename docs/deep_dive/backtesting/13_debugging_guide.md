# Debugging Guide

If the Backtesting Engine behaves incorrectly or produces bizarre `BacktestResult` metrics, follow this complete debugging workflow.

## 1. Which Files Should Developers Inspect?
- **Core Logic**: `backend/app/services/backtest_service.py`. This contains 100% of the mathematical logic, Pandas dataframe creation, indicator calculation, and the state-machine loop that records trades.
- **Agent Wrapper**: `backend/app/agents/backtest_agent.py`.
- **Invocation**: `backend/app/agents/orchestrator_agent.py` (Search for `run_backtest`).
- **Schemas**: `backend/app/schemas/analysis.py` (`BacktestResult` model).

## 2. Which Database Tables?
- `backtest_history`: Look here to see what the engine *saved* after a run. 
- `daily_candles` / `intraday_candles`: Look here to see the raw input data. If the input data is corrupted (e.g. `close` is 0), the backtest will be corrupted.

## 3. Which Logs?
- Check `logs/latest_scan.log`.
- Search for `Backtest agent failed`.
- Search for the specific symbol: `grep "RELIANCE" logs/latest_scan.log`.

## 4. Complete Debugging Workflow

### Step A: Verify Input Data
The BacktestEngine does not fetch its own data. It relies on the caller passing a `list[OHLCVPoint]`.
1. Check the DB: `SELECT count(*) FROM daily_candles WHERE symbol = 'X';`
2. If count < 35, the engine intentionally aborts.

### Step B: Run an Isolated Test
Create a small python script that bypasses the Orchestrator:
```python
from backend.app.services.backtest_service import BacktestService
from backend.app.services.market_data_service import MarketDataService

async def test():
    candles = await MarketDataService.get_historical_candles("RELIANCE", "swing")
    service = BacktestService()
    result = service.run("RELIANCE", "swing", candles)
    print(result.trade_count, result.total_return, result.verdict)
```

### Step C: Inspect Intermediate Pandas State
If trades are missing, edit `BacktestService.run`:
1. Add `print(frame.tail(10))` right before the `for index, row in frame.iterrows():` loop.
2. Verify that `ema_fast`, `ema_slow`, `rsi`, and `macd` are generating valid float numbers and not `NaN`.
3. If they are `NaN`, the `ta` library failed. This usually means `ffill()` and `bfill()` failed to clean up missing `close` prices.

### Step D: Check the Exit Condition
If trades are entering but never exiting (resulting in massive drawdowns):
1. Review the `exit_signal`.
2. Ensure `position_entry` state is being reset to `None` after a trade closes. (It is, on line 80).
