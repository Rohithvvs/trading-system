# Recommendation Engine: Database Interactions

The Recommendation Engine primarily reads from and writes to the **PostgreSQL** database managed by SQLAlchemy (`backend/app/db/session.py`).

## Core Tables

### 1. `watched_stocks`
- **Purpose:** Tracks the universe of symbols.
- **Interaction:** `OrchestratorAgent` queries this to map a string symbol (e.g., "RELIANCE") to an internal `stock_id`. If it doesn't exist, it creates it.

### 2. `analysis_histories`
- **Purpose:** The permanent ledger of all recommendations produced by the engine.
- **Columns Written:**
  - `stock_id` (FK)
  - `mode` (swing/intraday)
  - `technical_score`
  - `sentiment_score`
  - `backtest_score`
  - `recommendation` (BUY, WATCH, REJECT)
  - `confidence`
  - `reasoning` (AI generated summary)
- **Query Location:** `OrchestratorAgent._persist_analysis()`

### 3. `backtest_histories`
- **Purpose:** Records the simulation results for the setup at the time of recommendation.
- **Columns Written:**
  - `strategy_name`
  - `total_return`, `cagr`, `max_drawdown`, `win_rate`, `profit_factor`, `trade_count`, `verdict`.
- **Query Location:** `OrchestratorAgent._persist_analysis()`

## Relationships
- `analysis_histories` and `backtest_histories` hold a Many-to-One relationship to `watched_stocks`.

## Execution Style
The engine uses SQLAlchemy 2.0 Asyncio (`AsyncSessionLocal`) to prevent database I/O from blocking the main event loop.
```python
async with AsyncSessionLocal() as db:
    db.add(analysis_entry)
    db.add(backtest_entry)
    await db.commit()
```
