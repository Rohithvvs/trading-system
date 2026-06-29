# Code Walkthrough

This document walks through every file directly related to the Backtesting Engine.

## 1. `backend/app/services/backtest_service.py`
**Purpose**: The core mathematical engine that simulates trades over historical data.
**Classes**: `BacktestService`
**Methods**:
- `run(self, symbol, mode, candles)`: 
  - Converts `candles` (List of `OHLCVPoint`) to a Pandas DataFrame.
  - Cleans data (`ffill()`, `bfill()`).
  - Computes `ta` indicators (EMA, MACD, RSI).
  - Loops via `iterrows()` to simulate buy/sell states.
  - Computes aggregate metrics (`cagr`, `max_drawdown`, `profit_factor`, `win_rate`).
  - Returns a populated `BacktestResult`.
- `_empty_result(self, mode, strategy_name)`: 
  - Helper to return a 0-value result if input data is insufficient (<35 candles).
**Who calls it**: `BacktestAgent.run()`
**What it calls next**: It returns data. It doesn't call other services.
**Role**: The brain of the backtesting module.

## 2. `backend/app/agents/backtest_agent.py`
**Purpose**: A thin wrapper that conforms to the "Agent" pattern used by the Orchestrator.
**Classes**: `BacktestAgent`
**Methods**: 
- `__init__(self)`: Instantiates `BacktestService`.
- `run(self, symbol, mode, candles)`: Proxies the call to `self.service.run()`.
**Who calls it**: `OrchestratorAgent._analyze_symbol_post_bulk()`.
**What it calls next**: `BacktestService.run()`.
**Role**: Provides a clean interface for the Orchestrator to interact with the service layer.

## 3. `backend/app/schemas/analysis.py`
**Purpose**: Defines Pydantic models for data validation and API serialization.
**Classes** (related to backtest):
- `BacktestResult` (Pydantic BaseModel):
  - Defines the shape of the output: `total_return`, `cagr`, `trades` list, `equity_curve`, etc.
**Role**: Ensures type safety and JSON serialization format.

## 4. `backend/app/models/analysis.py`
**Purpose**: Defines SQLAlchemy ORM models for database persistence.
**Classes** (related to backtest):
- `BacktestHistory` (SQLAlchemy Base):
  - Maps to the `backtest_history` PostgreSQL table.
**Who calls it**: `OrchestratorAgent._persist_analysis()`.
**Role**: Allows the system to save backtest runs to the database permanently.
