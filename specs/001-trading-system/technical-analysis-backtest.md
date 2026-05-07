# Technical Analysis & Backtesting — Summary

Date: 2026-05-06

This document summarizes the technical indicators, signal-generation rules, scoring, and the backtesting strategy implemented in this codebase. It's written for users and developers who want a clear, actionable overview.

---

## Key implementation files

- [backend/app/services/technical_analysis_service.py](backend/app/services/technical_analysis_service.py) — indicator calculations, scoring and signal logic.
- [backend/app/services/backtest_service.py](backend/app/services/backtest_service.py) — backtest engine and performance metrics.
- [backend/app/agents/technical_analysis_agent.py](backend/app/agents/technical_analysis_agent.py) — thin agent wrapper for the technical service.
- [backend/app/agents/backtest_agent.py](backend/app/agents/backtest_agent.py) — thin agent wrapper for the backtest service.
- [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py) — runs analysis and backtests, persists results, applies "strict buy gate" rules.
- [backend/app/routes/analysis.py](backend/app/routes/analysis.py) — API endpoints (`/analysis/*`) to run analysis/backtest/scan.

---

## Overview

- Two analysis modes are supported: `intraday` and `swing` (selected via `AnalysisMode`).
- The technical engine computes a set of indicators and derives a numeric `score` (0–100). Scores are mapped into signals: `bullish`, `neutral`, `bearish`.
- The backtest engine uses simple rule-based strategies (EMA/SMA, RSI, MACD, volume) to simulate trades and report performance metrics (total return, CAGR, max drawdown, win rate, profit factor).
- The orchestrator runs analysis + backtests per symbol, persists `BacktestHistory`, and uses backtest results as a component of the overall recommendation.

---

## Technical indicators (what is calculated)

### Intraday mode (short-term)
- EMA 9 and EMA 20 (`ta.trend.EMAIndicator`) — short-term trend alignment.
- RSI 14 (`ta.momentum.RSIIndicator`) — momentum filter.
- MACD (fast=12, slow=26, signal=9) (`ta.trend.MACD`) — momentum confirmation.
- VWAP window 14 (`ta.volume.VolumeWeightedAveragePrice`) — price vs intraday value area.
- Volume trend: compare average volume over last 5 bars vs last 20 bars.

Scoring highlights (intraday):
- +20 if close > VWAP
- +20 if EMA9 > EMA20
- +15 if MACD > signal
- +15 if RSI in [52, 72] (or +8 if RSI >= 45)
- +15 if volume is expanding (5-bar avg > 20-bar avg) else +5
- +15 if last close > EMA9
- Score capped at 100. Signal mapping: score >= 68 => `bullish`; >=48 => `neutral`; else `bearish`.

### Swing mode (multi-day / trend)
- EMA 20, SMA 20/30/50/100/200 (`ta.trend.*`).
- RSI 14 and MACD (12/26/9).
- Supertrend (custom implementation in `_calculate_supertrend`) — default `period=10`, `multiplier=3.0`.
- Support / resistance: min(low) and max(high) over last 20 bars.
- Price structure checks: higher-high/higher-low checks over recent bars (2/3/4-day patterns and 5-day confirmation).
- Candlestick heuristics: hammer / gravestone doji detection.
- Liquidity thresholds (e.g., volume > 50,000 and > previous day) and basic price filters (price > 100, price < 500,000).

Scoring highlights (swing):
- Weighted contributions from trend (EMA20, Supertrend), momentum (MACD, RSI), higher-timeframe trend (SMA alignment), volume and structure.
- Example weights: +18 (close > EMA20), +16 (supertrend positive), +12 (MACD positive), +8 (RSI supportive), +10 (higher-timeframe uptrend), structure score contributes up to 12, etc.
- Hard filters: must pass core trend filter (EMA20 + Supertrend), momentum filter (MACD + RSI supportive), and basic liquidity filter to be considered bullish.
- Final mapping: if hard_filters_pass and score >= 72 => `bullish`; if hard_filters_pass and score >= 52 => `neutral`; else `bearish`.

---

## Backtesting strategy (how historical tests are run)

- Implemented in `BacktestService.run()`.
- Strategy selection by mode:
  - `intraday`: strategy name `ema_rsi_volume`. Uses `fast_window = 9`, `slow_window = 20`.
  - `swing`: strategy name `sma_rsi_macd`. Uses `fast_window = 20`, `slow_window = 50`.

Indicators used:
- EMA fast / EMA slow (as above).
- RSI 14.
- MACD (12, 26, 9).
- `avg_volume` = rolling mean over 20 bars.

Entry rule (bullish entry):
- `close > ema_fast`
- `ema_fast > ema_slow`
- `macd > macd_signal`
- `rsi >= 50`
- `volume >= max(avg_volume, 1) * 0.8` (i.e., reasonable liquidity)

Exit rule:
- `close < ema_fast` OR `macd < macd_signal` OR `rsi < 45`.

Position sizing and P&L:
- Starting equity: `100,000` (fixed).
- When an entry triggers, the algorithm records `position_entry` at that bar's close.
- When exit triggers (or at final close), trade return is computed as percent change; equity is updated multiplicatively: `equity *= 1 + (trade_return/100)`.
- No explicit stop-loss / take-profit beyond the indicator exit rules.
- No slippage or commission is modeled.

Minimum data:
- Backtest requires at least 35 candles to run; some parts of orchestrator expect larger windows (the orchestrator checks for `minimum_swing_candles_met >= 220` for data-quality when deciding readiness).

Metrics returned:
- `total_return` (%), `cagr` (simplified), `max_drawdown` (%), `win_rate` (%), `profit_factor`, `trade_count`, `equity_curve` (recent points), `verdict` ("favorable" | "mixed" | "insufficient").

Verdict rule (simple heuristic in code):
- `favorable` if `total_return > 0` AND `win_rate >= 45` AND `profit_factor >= 1`
- `mixed` otherwise when trades exist
- `insufficient` if no trades

---

## How backtests influence recommendations

- The orchestrator runs technical analysis and backtests per mode and selects the `best_backtest = max(backtests, key=total_return)`.
- Backtest results are persisted to the `backtest_history` table (`BacktestHistory`).
- Recommendation scoring incorporates a backtest component: roughly `backtest_component = clamp(backtest.total_return * 2, -5, 25)` unless `backtest.verdict == "insufficient"` or `trade_count < 5` (in which case `backtest_component = 0`).
- A strict BUY gate requires:
  - strong live data (FYERS primary and enough candles),
  - `best_technical.score >= 75`,
  - primary trade plan `risk_reward_ratio >= 1.25`, and
  - `supportive_backtest` (best_backtest.verdict in `{"favorable","mixed"}`).
- If the strict gate fails, a recommended `BUY` may be downgraded to `WATCH`.

---

## Where to run analysis & backtests (API)

- HTTP endpoint to run backtests: `POST /analysis/backtest` with body equal to `AnalysisRequest` (same shape used across analysis endpoints).

Example `curl` (replace `http://127.0.0.1:8000` with your `VITE_API_BASE_URL` / dev server):

```bash
curl -s -X POST "http://127.0.0.1:8000/analysis/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["RELIANCE"],
    "mode": "both",
    "timeframe": { "intraday": "5m", "swing": "1d", "lookback_window": 220 }
  }'
```

Note: `lookback_window` controls how many candles are requested from your data source (FYERS / candle cache) — the orchestrator logs data source and candle counts.

---

## Limitations & suggested improvements

- No slippage, commissions or minimal tick assumptions — add per-trade cost modeling for realistic performance.
- Position sizing is "all equity" per trade; implement fixed % risk-per-trade or fixed position sizing to reflect realistic exposure.
- No out-of-sample split / walk-forward testing — consider train/validation/test splits to avoid overfitting.
- CAGR formula is simplistic; replace with a time-aware CAGR computed from timestamps.
- Add transaction-level timestamps to equity curve and include leverage/overnight financing if applicable.
- Add Monte Carlo / bootstrap stress tests for robustness and confidence intervals.
- Add configurable slippage/commission and allow per-symbol liquidity constraints.

---

## Quick pointers for developers

- To inspect the scoring, open: [backend/app/services/technical_analysis_service.py](backend/app/services/technical_analysis_service.py).
- To inspect the backtest rules and trade loop, open: [backend/app/services/backtest_service.py](backend/app/services/backtest_service.py).
- The orchestrator uses both services and persists results: [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py).

---

If you'd like, I can:
- add a `README` section with exact commands to run a single-symbol backtest locally,
- extend the backtest engine to model slippage and commission, or
- produce a short Jupyter notebook that runs a live backtest and plots the equity curve.

Which of these would you like next?
