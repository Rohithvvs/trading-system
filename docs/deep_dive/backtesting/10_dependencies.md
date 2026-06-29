# Dependencies

The Backtesting Engine relies on a specific set of upstream pipelines and downstream consumers.

## 1. Market Data Pipeline
- **Dependency**: `MarketDataService` and PostgreSQL (`daily_candles`).
- **Nature**: Critical. The Backtest Engine requires a pristine, gap-free list of `OHLCVPoint` objects to function. It does not fetch data itself. If the Market Data Pipeline provides corrupted or short data, the backtest will produce corrupted or empty results.

## 2. Technical Analysis Library
- **Dependency**: Pandas and the `ta` (Technical Analysis) pip package.
- **Nature**: Critical. Instead of writing custom loops to calculate EMA and RSI, it uses `ta.trend.EMAIndicator` and `ta.momentum.RSIIndicator`.

## 3. Recommendation Engine
- **Dependency**: Downstream Consumer.
- **Nature**: The `RecommendationAgent` consumes the `BacktestResult`. It relies on the Backtester to provide mathematical proof that a strategy works on a specific stock before issuing a `BUY` signal.

## 4. Database
- **Dependency**: `backtest_history` table (PostgreSQL).
- **Nature**: Storage. Used by `OrchestratorAgent._persist_analysis()` to save the backtest scores and trade counts.

## 5. Redis & Schedulers
- **Dependency**: Upstream only.
- **Nature**: The Backtest Engine itself contains no Redis or Scheduler code. It is invoked purely as a synchronous CPU function. However, the Orchestrator that launches it is triggered by APScheduler, and the MarketDataService that feeds it uses Redis-backed rate limiters to fetch the data.
