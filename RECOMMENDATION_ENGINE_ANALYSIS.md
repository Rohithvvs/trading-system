# Recommendation Engine Analysis & Redesign

**Date:** 2026-07-23  
**Branch:** `SAI_CHANDRA`  
**Status:** Implemented and validated  

---

## 1. Existing Recommendation Flow

Signals are **not** produced immediately after market data is loaded. The scanner runs a full multi-stage pipeline; the final BUY / WATCH / REJECT label is applied only at the end.

### 1.1 End-to-end pipeline (production)

```
Universe Selection
        ↓
Market Data Fetch (OHLCV — FYERS / CANDLE_CACHE_DB)
        ↓
Data Validation (min candles, source quality, liquidity filters)
        ↓
Screener Condition Checks (price, volume, trend eligibility)
        ↓
Shortlist Top-N Matched Symbols
        ↓
── Full Analysis (OrchestratorAgent.run_full) ──────────────────
        ↓
Technical Analysis (bulk)  ← all indicators below
  • Trend / structure
  • Support & Resistance
  • Moving Averages (SMA 20/30/50/100/200, EMA 9/20/50)
  • Momentum
  • RSI
  • MACD (+ signal)
  • SuperTrend / ATR-based structure
  • Volume trend / VWAP (intraday path)
  • Liquidity / price band filters
  • Higher-timeframe trend labels
        ↓
News / Sentiment Analysis
        ↓
Fundamental Analysis
        ↓
Backtest Engine
        ↓
Sector Relative Strength (SR-003)
        ↓
Market Permission / Regime (SR-004) — telemetry / challenger only
        ↓
AI Reasoning (LLMService.build_reasoning)
        ↓
Composite Score Calculation (RecommendationService)
        ↓
Trade Plan Generation (entry / SL / targets / R:R)
        ↓
FEAT-004 / FEAT-007 overlays — SHADOW telemetry only
        ↓
Final Recommendation Gate (score-based only)
        ↓
Rank BUY / WATCH → API + UI
```

### 1.2 Primary modules / classes

| Stage | File | Class / Function |
|-------|------|------------------|
| Universe / screener | `backend/app/services/screener_service.py` | `ScreenerService` |
| Orchestration | `backend/app/agents/orchestrator_agent.py` | `OrchestratorAgent.run_full`, `_run_screener_stage`, `_analyze_symbol_post_bulk` |
| Market data | `backend/app/services/fyers_service.py`, `market_data_service.py` | OHLCV fetch / cache |
| Technical analysis | `backend/app/services/technical_analysis_service.py` | `TechnicalAnalysisService.analyze_bulk` |
| Technical agent | `backend/app/agents/technical_analysis_agent.py` | `TechnicalAnalysisAgent.run_bulk` |
| News / sentiment | `backend/app/agents/news_analysis_agent.py`, `sentiment_service.py` | Sentiment labels/scores |
| Fundamentals | fundamental agent/service | `FundamentalAnalysisResult` |
| Backtest | `backend/app/agents/backtest_agent.py`, `backtest_service.py` | Strategy backtests |
| Sector RS | `backend/app/services/sector_rs_service.py` | `SectorRelativeStrengthService` |
| Market permission | `backend/app/services/market_permission_service.py` | Regime evaluation (challenger) |
| AI reasoning | `backend/app/services/llm_service.py` | `LLMService.build_reasoning` |
| Recommendation agent | `backend/app/agents/recommendation_agent.py` | `RecommendationAgent.run` |
| Recommendation engine | `backend/app/services/recommendation_service.py` | `RecommendationService.build`, `classify_signal_from_score` |
| Final gate | `backend/app/agents/orchestrator_agent.py` | `_enforce_strict_buy_gate` |
| Ranking | ranking agent | BUY / WATCH ranking |
| API | `backend/app/routes/*`, schemas | `ScreenerResponse`, `FinalRecommendation` |
| Frontend | `frontend/src/App.tsx` | Consumes `buy_candidate_symbols` / `watch_candidate_symbols` |

### 1.3 When the signal is generated

1. Screener completes universe scan + shortlist.  
2. Full analysis runs for shortlisted symbols only (tech → news → fund → backtest → sector → AI).  
3. `RecommendationService.build()` computes composite **score**, **confidence**, and **trade plans**.  
4. Orchestrator final gate validates preconditions, then classifies by score.  
5. Shortlist BUY/WATCH lists are built from `item.recommendation.action`.

**Confirmed:** no BUY/WATCH/REJECT is assigned solely from raw market data without analysis.

---

## 2. Files Modified

| File | Change |
|------|--------|
| `backend/app/services/recommendation_service.py` | BUY threshold **70**; shared classifiers + preconditions; overlays telemetry-only |
| `backend/app/agents/orchestrator_agent.py` | Final gate: mandatory preconditions → score-only classification |
| `backend/tests/unit/test_recommendation_fixes.py` | Full coverage for thresholds + Analysis Failed paths |
| `backend/tests/regression/test_feat001_stage1_screener.py` | Gate regression assertion (score-based policy) |

### Unchanged (by design)

- All technical analysis modules  
- AI / LLM reasoning  
- Score calculation weights / matrix  
- Trade plan math (entry/SL/targets/R:R still computed)  
- API schemas (same `action` / `score` fields)  
- Frontend UI fields (Score, Confidence, Trend, R:R, Entry, SL, Target, evidence)  
- Challenger sector/market path (shadow only; does not set production shortlist)

---

## 3. Functions Modified

### `backend/app/services/recommendation_service.py`

| Symbol | Role |
|--------|------|
| `BUY_SCORE_THRESHOLD = 70.0` | Production BUY cutoff |
| `WATCH_SCORE_THRESHOLD = 55.0` | Production WATCH cutoff |
| `ANALYSIS_FAILED_REASON` | Standard failure label |
| `classify_signal_from_score(score)` | Pure score → BUY/WATCH/REJECT |
| `is_trade_plan_complete(plan)` | Entry / SL / target presence |
| `analysis_preconditions_ok(...)` | Mandatory preconditions helper |
| `RecommendationService.build()` | Still runs full scoring + plans + AI inputs; final label score-only (or REJECT on analysis failure) |
| `_apply_feat007_overlay()` | Unchanged telemetry path (does not override production) |

### `backend/app/agents/orchestrator_agent.py`

| Symbol | Role |
|--------|------|
| `_enforce_strict_buy_gate(...)` | Final gate after full analysis: preconditions then score classification |

Call order inside `_analyze_symbol_post_bulk` (preserved):

```
technical + news + fundamental + backtest
  → sector RS
  → recommendation_agent.run  (AI + score + trade plan)
  → _enforce_strict_buy_gate  (final signal only)
  → challenger (shadow)
  → persist / return
```

---

## 4. Old Recommendation Logic

```
All analysis modules execute
  → Composite score
  → Initial label (historically ≥72 or ≥68 BUY / ≥55 WATCH)
  → FEAT-004 may adjust score + label (if ACTIVE)
  → FEAT-007 may adjust score + label (if ACTIVE)
  → Strict BUY Gate (if BUY):
        require strong_live_data
        AND technical ≥ 70
        AND R:R ≥ 1.15
        else BUY → WATCH
  → Challenger sector/market downgrades (shadow)
```

**Problem:** strong composite scores were frequently forced to WATCH by non-score gates (R:R, tech conviction, data flags mis-handling, overlays).

---

## 5. New Recommendation Logic

### 5.1 Analysis still runs completely first

No analysis module was removed. Indicators, AI reasoning, confidence, trade plans, R:R, sector RS, and regime metadata continue to be calculated and returned for UI display.

### 5.2 Mandatory preconditions

If **any** fail → **Signal = REJECT**, **Reason = Analysis Failed**

| Check | Implementation |
|-------|----------------|
| Market data available | Trusted source `FYERS_PRIMARY` or `CANDLE_CACHE_DB` |
| Price / OHLC valid | `minimum_swing_candles_met`, not mock |
| Trade plan generated | Non-empty `trade_plans` |
| Entry calculated | `entry_low` / `entry_high` > 0 and ordered |
| Stop loss calculated | `stop_loss` > 0 |
| Target calculated | `target_1` > 0 |
| Score calculated | Finite composite score |
| Confidence calculated | Finite confidence |
| Analysis completed | Technical results present |

### 5.3 Final score rules (only decision factors)

| Score | Signal |
|------:|--------|
| **≥ 70** | **BUY** |
| **55 – 69.99** | **WATCH** |
| **&lt; 55** | **REJECT** |

### 5.4 Explicitly ignored for final decision (still displayed)

- Risk Reward  
- Conviction / trend strength  
- AI confidence thresholds  
- Market regime  
- Breakout confirmation  
- Hidden feature flags  
- Safety overrides / BUY suppression  
- Watch promotion logic  
- FEAT-004 / FEAT-007 label adjustments  

---

## 6. Validation Results

### Unit tests

```text
pytest tests/unit/test_recommendation_fixes.py -v
→ 21 passed
```

### Step 7 score matrix

| Score | Expected | Actual |
|------:|----------|--------|
| 82 | BUY | BUY |
| 75 | BUY | BUY |
| 71 | BUY | BUY |
| 70 | BUY | BUY |
| 69 | WATCH | WATCH |
| 63 | WATCH | WATCH |
| 58 | WATCH | WATCH |
| 55 | WATCH | WATCH |
| 54 | REJECT | REJECT |
| 40 | REJECT | REJECT |

### Full `RecommendationService.build` samples

| Sample | Tech | Backtest | Score | Action | Trade plan complete |
|--------|-----:|---------:|------:|--------|---------------------|
| BUY_SAMPLE | 90 | +15% | **72.5** | **BUY** | Yes |
| WATCH_SAMPLE | 75 | +5% | **55.0** | **WATCH** | Yes |
| REJECT_SAMPLE | 30 | 0% | **27.5** | **REJECT** | Yes |

### Mandatory failure cases

| Case | Score | Result | Reason |
|------|------:|--------|--------|
| Mock / untrusted data | 82 | REJECT | Analysis Failed |
| Missing trade plan | 82 | REJECT | Analysis Failed |
| Incomplete entry/SL/target | 80 | REJECT | Analysis Failed |
| No technical results | 80 | REJECT | Analysis Failed |

### Weak R:R / weak tech (informational)

| Case | Score | R:R / Tech | Result |
|------|------:|------------|--------|
| Weak R:R | 75 | R:R 0.5 | **BUY** (R:R ignored) |
| Weak technical | 73 | tech 65 | **BUY** (tech threshold ignored) |

---

## 7. Before vs After Comparison

| Aspect | Before | After |
|--------|--------|-------|
| BUY threshold | 68 (or 72 historically) + gates | **≥ 70** only |
| WATCH band | 55–67.99 (when not overridden) | **55–69.99** |
| R:R gate | Could force BUY → WATCH | Display only |
| Tech ≥ 70 gate | Could force BUY → WATCH | Display only |
| FEAT-004/007 on production label | Could change action | Telemetry only |
| Invalid data | Often BUY → WATCH | **REJECT / Analysis Failed** |
| Missing trade plan | Soft/inconsistent | **REJECT / Analysis Failed** |
| Analysis modules | Full | **Full (unchanged)** |
| AI / score / plans | Required | **Still required before signal** |
| UI fields | Full | **Full (signal source = backend score)** |

---

## 8. Sample BUY Stocks

Synthetic validation candidates (score construction uses production weights when no news catalyst: tech 50% / backtest 25% / fund 25%; neutral fund → 50/100):

| Sample ID | Score | Action | Notes |
|-----------|------:|--------|-------|
| BUY_SAMPLE | 72.5 | BUY | Strong tech + favorable backtest |
| Boundary 70 | 70.0 | BUY | Exact BUY threshold |
| High score 82 | 82.0 | BUY | Weak R:R still BUY |
| High score 75 | 75.0 | BUY | |
| High score 71 | 71.0 | BUY | |

Live shortlist BUY names will appear when scanner composite score ≥ 70 and preconditions pass (trusted candles + complete trade plan).

---

## 9. Sample WATCH Stocks

| Sample ID | Score | Action | Notes |
|-----------|------:|--------|-------|
| WATCH_SAMPLE | 55.0 | WATCH | Mid technical / modest backtest |
| Score 69 | 69.0 | WATCH | Just below BUY (was BUY under 68 threshold) |
| Score 63 | 63.0 | WATCH | |
| Score 58 | 58.0 | WATCH | |
| Score 55 | 55.0 | WATCH | Exact WATCH floor |

---

## 10. Sample REJECT Stocks

| Sample ID | Score | Action | Notes |
|-----------|------:|--------|-------|
| REJECT_SAMPLE | 27.5 | REJECT | Weak technical composite |
| Score 54 | 54.0 | REJECT | Just below WATCH |
| Score 40 | 40.0 | REJECT | |
| MOCK_DATA_HIGH | 82* | REJECT | Analysis Failed (invalid market data) |
| NO_PLAN_HIGH | 82* | REJECT | Analysis Failed (no trade plan) |

\*Score may be high; action is REJECT solely because preconditions failed.

---

## 11. Confirmation: All Technical Analysis Still Executes Before Recommendation

| Module | Still executes before final signal? | Evidence |
|--------|-------------------------------------|----------|
| Trend / structure | Yes | `TechnicalAnalysisService.analyze_bulk` swing path |
| Support & Resistance | Yes | `support_series` / `resistance_series` |
| Moving averages | Yes | SMA 20/30/50/100/200, EMA 9/20/50 |
| Momentum / RSI / MACD | Yes | RSI-14, MACD, MACD signal |
| ATR / SuperTrend | Yes | `_calculate_supertrend` |
| Volume / liquidity / price filters | Yes | Screener + technical score components |
| Breakout / pullback structure | Yes | Structure score components in swing TA |
| Sector / relative strength | Yes | `SectorRelativeStrengthService` before recommendation |
| AI analysis | Yes | `LLMService.build_reasoning` in `RecommendationAgent.run` |
| Confidence calculation | Yes | `score/100` clamped confidence in `build()` |
| Trade plan (entry/SL/target/R:R) | Yes | `_build_trade_plans` before final label |
| Composite score | Yes | Dynamic weights or scoring matrix before label |
| Final recommendation | **Last** | Gate only after full path completes |

**No analysis module was deleted or short-circuited.** Only the **final decision function** changed:

```text
IF preconditions fail → REJECT ("Analysis Failed")
ELSE IF score >= 70 → BUY
ELSE IF score >= 55 → WATCH
ELSE → REJECT
```

---

## 12. Code Audit — Where BUY / WATCH / REJECT Are Assigned

| Location | Role after redesign |
|----------|---------------------|
| `classify_signal_from_score()` | **Canonical** production classifier |
| `RecommendationService.build()` | Applies classifier after score + plans |
| `OrchestratorAgent._enforce_strict_buy_gate()` | Re-validates preconditions + re-applies classifier |
| Empty/missing data path | Explicit REJECT (no analysis) |
| Challenger recommendation | Shadow only; not used for `buy_candidate_symbols` |
| Frontend | Displays backend action lists (no independent classification) |
| Technical `signal` bullish/neutral/bearish | Indicator-level only — **not** BUY/WATCH/REJECT |
| Paper trading `side=BUY` | Order side — unrelated to scanner signal |

Duplicate production overrides (R:R gate, multi-condition BUY gate, overlay label application) have been removed from the production path.

---

## 13. How Operators Verify

1. Ensure broker token / candle cache is healthy (trusted data).  
2. Run scanner over the universe.  
3. For each shortlisted symbol:

```text
preconditions pass AND score >= 70  → BUY
preconditions pass AND 55 <= score < 70 → WATCH
preconditions pass AND score < 55 → REJECT
any precondition fails → REJECT (Analysis Failed)
```

4. Log markers:

```text
SCORE SIGNAL POLICY
SCORE SIGNAL PASS
SCORE SIGNAL RECLASSIFY
SCORE SIGNAL REJECT | reason=Analysis Failed
ANALYSIS_FAILED | stage=recommendation_service
```

---

## Summary

The recommendation engine still performs the **entire** analysis stack. The only production change is the **final** mapping:

**Score ≥ 70 → BUY · Score 55–69.99 → WATCH · Score &lt; 55 → REJECT**

with hard **Analysis Failed → REJECT** when market data, OHLC, trade plan (entry/SL/target), score, confidence, or analysis completion is missing.
