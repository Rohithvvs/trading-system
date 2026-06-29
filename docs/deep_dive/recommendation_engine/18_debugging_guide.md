# Recommendation Engine: Debugging Guide

If the Recommendation Engine is producing incorrect output (e.g. issuing a `BUY` on a collapsing stock, or a `WATCH` on a perfect setup), use this workflow.

## 1. Trace the Recommendation
**File to check:** `backend/logs/app.log`
- Search the logs for `STRICT BUY GATE EVALUATE | symbol=<TICKER>`.
- The log contains a snapshot of exactly *why* a decision was made:
  `rec_score=78.00 | rec_conf=0.78 | best_tech_score=85.00 | backtest_verdict=favorable | plan_rw=2.1 | mock_warning=False`

## 2. Check the Downgrades
**File to check:** `backend/app/agents/orchestrator_agent.py`
**Method:** `_enforce_strict_buy_gate()`
- If the stock *should* be a `BUY` but is a `WATCH`, this is almost always the culprit.
- Check if `strong_live_data`, `strong_technical`, or `strong_execution` evaluated to `False`.

## 3. Verify the Technical Score Math
**File to check:** `backend/app/services/technical_analysis_service.py`
**Method:** `analyze_bulk_from_frame()`
- If `best_tech_score` seems wrong, temporarily add print statements inside the loop for the specific symbol:
  ```python
  if symbol == "RELIANCE":
      print(f"EMA20: {ema_20}, Close: {lc}, RSI: {rsi_14}")
  ```
- Recalculate the points manually (e.g., +18 for Close > EMA20).

## 4. Verify AI LLM Responses
**File to check:** `backend/app/services/llm_service.py`
- If the text reasoning is garbage or the sentiment score is `0.0` when breaking news exists, check the Groq API key in `.env`.
- Check if `fallback_logs.jsonl` contains timeout errors.

## 5. Database & Cache Verification
**Database:** PostgreSQL (`SessionLocal`)
- Table: `analysis_histories`. Query: `SELECT * FROM analysis_histories WHERE stock_id = (SELECT id FROM watched_stocks WHERE symbol='RELIANCE');`
- If the data isn't here, the `OrchestratorAgent._persist_analysis` method failed.

**SQLite Cache:** `candle_cache.db`
- Table: `daily_candles`.
- If the system is defaulting to mocked data or REJECTing due to missing data, the cache might be empty or stale. Use the `candle_store.py` tools to clear and rebuild.

## Developer Workflow Summary
1. Start at `OrchestratorAgent.run_screener` to confirm the stock survived the initial scanner funnel.
2. Check `TechnicalAnalysisService.analyze_bulk_from_frame` for math errors.
3. Check `RecommendationService.build` for weighting issues.
4. Check `OrchestratorAgent._enforce_strict_buy_gate` for safety overrides.
