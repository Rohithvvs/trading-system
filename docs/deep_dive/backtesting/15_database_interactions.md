# Database Interactions

The Backtesting Engine relies on the database for input data and output persistence.

## 1. Input Tables (Read-Only to Backtester)
The BacktestEngine does not directly query the database. It receives `candles` from the orchestrator, which fetched them from:
- `daily_candles`
- `intraday_candles`

## 2. Output Table: `backtest_history`
Defined in `backend/app/models/analysis.py`.

**Purpose**: Persist the final mathematical results of a backtest run so they can be viewed in the UI or referenced in future analytical reports without recalculating.

**Schema**:
- `id`: Primary Key
- `stock_id`: Foreign Key (`watched_stocks.id`)
- `mode`: String (e.g., 'swing', 'intraday')
- `strategy_name`: String (e.g., 'sma_rsi_macd', 'ema_rsi_volume')
- `total_return`: Float
- `cagr`: Float
- `max_drawdown`: Float
- `win_rate`: Float
- `profit_factor`: Float
- `trade_count`: Integer
- `verdict`: String ('favorable', 'mixed', 'insufficient')
- `created_at`: Timestamp

**Relationships**:
- Belongs to `WatchedStock` (`back_populates="backtests"`).

**Persistence Strategy**:
- Saved via `OrchestratorAgent._persist_analysis`.
- **Query**:
  ```python
  backtest_entry = BacktestHistory(...)
  db.add(backtest_entry)
  await db.commit()
  ```
- Note: There is no `UNIQUE` constraint on `(stock_id, created_at)`, meaning every time the scanner runs, a new historical row is appended. This creates a time-series log of backtest performance over time.
