# Score-Based Recommendation Logic

**Date:** 2026-07-23  
**Branch:** `SAI_CHANDRA`  
**Status:** Superseded by `RECOMMENDATION_ENGINE_ANALYSIS.md`  

> **Update:** BUY threshold is now **≥ 70** (not 68). See `RECOMMENDATION_ENGINE_ANALYSIS.md` for the current production design.

---

## Problem

The scanner produced **WATCH** and **REJECT** signals even when composite scores were strong enough for **BUY**.

Root cause: after `RecommendationService` assigned a score-based label, production BUY signals were often **overridden** by the Strict BUY Gate (and potentially by FEAT-004 / FEAT-007 overlays when enabled). Overrides included:

| Override | Effect |
|----------|--------|
| Risk:Reward ≥ 1.15 required | BUY → WATCH when R:R weak |
| Technical score ≥ 70 required | BUY → WATCH when tech soft |
| Trusted live data + min candles | BUY → WATCH on data quality miss |
| FEAT-004 regime overlay (if ACTIVE) | Score/label adjust; BUY → WATCH |
| FEAT-007 sector RS overlay (if ACTIVE) | Score/label adjust; BUY → WATCH |
| Challenger sector/market regime | Shadow only (did not drive shortlist BUY list) |

---

## New Signal Rules (Production)

After mandatory validations pass, classify **only** by composite score:

| Score | Signal |
|------:|--------|
| **≥ 68** | **BUY** |
| **55 – 67.99** | **WATCH** |
| **&lt; 55** | **REJECT** |

### Mandatory validations (before score classification)

1. **Valid market data** — trusted source (`FYERS_PRIMARY` or `CANDLE_CACHE_DB`), not mock, minimum swing candles met  
2. **Successful scan** — composite score computed and finite  
3. **Trade plan generated** — non-empty `trade_plans` for BUY/WATCH candidates  

If (1) or (3) fails → **REJECT** (does not fall through to WATCH via R:R/tech gates).

### Explicitly removed from production signal decision

- Risk:Reward threshold  
- Conviction / technical score gate  
- AI confidence threshold  
- Breakout confirmation  
- Market regime filters on production label  
- FEAT-004 / FEAT-007 score/label overrides on production output  
- Multi-condition Strict BUY Gate  

Overlays still run for **telemetry / shadow metadata** only; they do **not** change `recommendation.action` or `recommendation.score`.

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/recommendation_service.py` | Added `classify_signal_from_score()`; production action/score ignore FEAT-004/007 adjustments |
| `backend/app/agents/orchestrator_agent.py` | Replaced Strict BUY Gate with score policy + mandatory validations |
| `backend/tests/unit/test_recommendation_fixes.py` | Updated/expanded tests for score bands and removed overrides |
| `backend/tests/regression/test_feat001_stage1_screener.py` | Updated gate regression assertion to score-based policy |

### Not modified (no change required)

| Layer | Reason |
|-------|--------|
| API schemas / routes | `action` / `score` fields already present; shortlist still keys on `recommendation.action` |
| Frontend (`App.tsx`, tables) | Displays `buy_candidate_symbols` / `watch_candidate_symbols` from backend |
| Challenger recommendation path | Remains shadow/compare only; production shortlist uses primary `recommendation` |

---

## Functions Modified

### 1. `backend/app/services/recommendation_service.py`

**Added**

```python
BUY_SCORE_THRESHOLD = 68.0
WATCH_SCORE_THRESHOLD = 55.0

def classify_signal_from_score(score: float) -> str:
    if score >= 68: return "BUY"
    if score >= 55: return "WATCH"
    return "REJECT"
```

**`RecommendationService.build()`**

| Stage | Previous | New |
|-------|----------|-----|
| Initial label | `score≥68 BUY / ≥55 WATCH / else REJECT` | Same (via `classify_signal_from_score`) |
| FEAT-004 | Applied adjusted score + label to production output | Telemetry only; production keeps composite score |
| FEAT-007 | Applied adjusted score + label to production output | Telemetry only; production keeps composite score |
| Final `action` / `score` | Post-overlay values | Pure composite score + score thresholds |

### 2. `backend/app/agents/orchestrator_agent.py`

**`OrchestratorAgent._enforce_strict_buy_gate()`** (name retained for call-site compatibility)

| Previous | New |
|----------|-----|
| Only ran when action == BUY | Always re-classifies by score |
| Required `strong_live_data` + `strong_technical` (≥70) + `strong_execution` (R:R ≥ 1.15) | R:R and tech score **not** used |
| Failure → downgrade BUY → **WATCH** | Invalid data / no plan → **REJECT** |
| Pass → keep BUY | Pass → score band action (BUY / WATCH / REJECT) |

---

## Previous Recommendation Logic

```
composite score
  → initial action (68 / 55 thresholds)
  → FEAT-004 may change score + label (if ACTIVE)
  → FEAT-007 may change score + label (if ACTIVE)
  → Strict BUY Gate (if BUY):
        strong_live_data AND strong_technical(≥70) AND strong_execution(R:R≥1.15)
          ? keep BUY
          : downgrade to WATCH
  → Challenger (sector + market) stored separately
  → Shortlist BUY/WATCH from production recommendation.action
```

Typical failure mode: score 70–80 BUY candidate → gate fails on R:R, tech, or data flags → **WATCH only**.

---

## New Recommendation Logic

```
composite score (unchanged weighting/scoring matrix)
  → action = classify_signal_from_score(score)   # 68 / 55
  → FEAT-004 / FEAT-007: log only (no production override)
  → Orchestrator score policy:
        if invalid market data → REJECT
        if BUY/WATCH and no trade plan → REJECT
        else action = classify_signal_from_score(score)
  → Challenger remains shadow-only
  → Shortlist BUY/WATCH from production recommendation.action
```

---

## Validation Results

### Unit tests

```text
pytest tests/unit/test_recommendation_fixes.py -v
→ 17 passed
```

Covered:

- Threshold constants and pure classifier  
- `build()` BUY / WATCH / REJECT samples  
- Trusted `CANDLE_CACHE_DB` allows BUY  
- Mock data → REJECT  
- Weak technical / weak R:R still BUY when score ≥ 68  
- Insufficient candles → REJECT  
- Missing trade plan → REJECT  
- Boundary scores 68 / 55 / 54.99  
- FEAT-004 enabled does not override production BUY  

### End-to-end script validation (2026-07-23)

#### Pure classifier

| Score | Signal |
|------:|--------|
| 100 | BUY |
| 80 | BUY |
| 68 | BUY |
| 67.99 | WATCH |
| 60 | WATCH |
| 55 | WATCH |
| 54.99 | REJECT |
| 40 | REJECT |
| 0 | REJECT |

#### `RecommendationService.build` samples

| Symbol | Tech | Backtest ret | Composite score | Action |
|--------|-----:|-------------:|----------------:|--------|
| STRONG_BUY_CAND | 90 | 15.0 | **72.50** | **BUY** |
| MID_WATCH_CAND | 75 | 5.0 | **55.00** | **WATCH** |
| WEAK_REJECT_CAND | 30 | 0.0 | **27.50** | **REJECT** |

#### Orchestrator policy (trusted data + plan, R:R = 0.5 intentionally weak)

| Score | Expected | Got | Notes |
|------:|----------|-----|-------|
| 80 | BUY | BUY | Weak R:R no longer blocks |
| 60 | WATCH | WATCH | |
| 40 | REJECT | REJECT | |
| 68 | BUY | BUY | BUY boundary |
| 55 | WATCH | WATCH | WATCH boundary |
| 54.99 | REJECT | REJECT | REJECT boundary |

#### Mandatory validations

| Case | Score | Result |
|------|------:|--------|
| Mock / untrusted data | 80 | REJECT |
| No trade plan | 80 | REJECT |

---

## Sample Stocks Showing BUY / WATCH / REJECT

Synthetic scan candidates used for validation (score construction uses production weights: tech 50% / backtest 25% / fundamental 25% when no news catalyst; neutral fund → 50/100):

### BUY (score ≥ 68)

| Sample | Score | Action | Why |
|--------|------:|--------|-----|
| STRONG_BUY_CAND | 72.50 | BUY | Strong tech (90) + favorable backtest (+15% → 60 component) |
| BUY_BOUNDARY | 68.00 | BUY | Exact BUY threshold |
| WEAK_RR_STILL_BUY | 75.00 | BUY | R:R 0.5 would previously have forced WATCH |

### WATCH (55 ≤ score &lt; 68)

| Sample | Score | Action | Why |
|--------|------:|--------|-----|
| MID_WATCH_CAND | 55.00 | WATCH | Mid tech (75) + modest backtest |
| WATCH_BAND | 60.00 | WATCH | Interior of WATCH band |
| WATCH_BOUNDARY | 55.00 | WATCH | Exact WATCH threshold |

### REJECT (score &lt; 55)

| Sample | Score | Action | Why |
|--------|------:|--------|-----|
| WEAK_REJECT_CAND | 27.50 | REJECT | Weak tech (30) |
| REJECT_BAND | 40.00 | REJECT | Interior of REJECT band |
| MOCK_DATA_HIGH_SCORE | 80.00* | REJECT | Failed mandatory data validation |
| NO_PLAN_HIGH_SCORE | 80.00* | REJECT | Failed mandatory trade-plan validation |

\*Composite score remains high; action is REJECT solely due to mandatory validation failure.

---

## API / Frontend Impact

- **API:** No schema change. `FinalRecommendation.action` and `score` continue to be returned; `buy_candidate_symbols` / `watch_candidate_symbols` still derived from `item.recommendation.action == "BUY"|"WATCH"`.  
- **Frontend:** No change required. Scanner cards and filters already consume backend candidate lists.  
- **Trade readiness** strings may still mention R:R for operator context; they do **not** change the signal.

---

## How to Verify in a Live Scan

1. Ensure Fyers token / candle cache is healthy (trusted data path).  
2. Run scanner (UI or API).  
3. For each shortlisted symbol, confirm:

```text
score >= 68  and valid data + trade plan  →  BUY
score in [55, 68) and valid data + trade plan  →  WATCH
score < 55  →  REJECT
invalid data or missing trade plan  →  REJECT
```

4. Logs to grep:

```text
SCORE SIGNAL POLICY
SCORE SIGNAL PASS
SCORE SIGNAL REJECT
SCORE SIGNAL RECLASSIFY
```

---

## Summary

Production signals are now **score-driven** with only three hard preconditions (data, scan, trade plan). The multi-condition Strict BUY Gate and overlay label overrides no longer suppress BUY ideas when the composite score is already ≥ 68.
