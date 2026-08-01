# Recommendation Pipeline Fix

**Date:** 2026-07-23  
**Branch:** `SAI_CHANDRA`  
**Status:** Fixed and unit-validated  

---

## 1. Root Cause

Two defects combined after the score-based recommendation change:

### A. False “Analysis Failed” on valid shortlist data (backend)

Shortlist analysis reuses **prefetched OHLCV** from the screener. Those candles were **not registered** in `FyersService._ohlcv_source_cache`, so:

```text
get_ohlcv_source() → "unknown"
→ mock_warning = True  (old rule: source not in {FYERS_PRIMARY, CANDLE_CACHE_DB})
→ analysis_preconditions_ok() failed
→ Signal = REJECT ("Analysis Failed")
```

Full technical analysis, composite score, confidence, and trade plans had already been computed. The final gate then incorrectly treated the stock as a failed analysis.

### B. REJECT results stripped from the API payload (backend → UI)

```python
# OLD
analysis_items = buy_items + watch_items  # REJECT dropped
```

Frontend builds rows from `shortlisted_symbols` and looks up analysis by symbol:

```ts
// OLD
score: analysis?.recommendation.score ?? match?.screener_score ?? 0
```

When analysis was missing:

| UI field | What user saw |
|---------|----------------|
| Score | **screener_score** (often **100.0**) |
| Conviction | `--` |
| Entry / SL / TP / R:R | `--` |
| Chart | **No chart data** (no `analysisItem`) |
| Signal | REJECT |

That is exactly the reported regression.

**Pipeline did not stop mid-analysis.** Analysis usually completed; results were either mis-gated or not returned to the UI.

---

## 2. Files Modified

| File | Change |
|------|--------|
| `backend/app/agents/orchestrator_agent.py` | Prefetch source registration; data-quality remap; include REJECT in analysis payload; clear score on true failure |
| `backend/app/services/recommendation_service.py` | Preconditions accept full candle series without inventing scores |
| `backend/tests/unit/test_recommendation_fixes.py` | Coverage for unknown+candles, mock clear, BUY 71.7 path |
| `frontend/src/App.tsx` | Never fall back to screener_score; null score for failures |
| `frontend/src/Dashboard.tsx` | Same candidate-row fix |
| `frontend/src/types.ts` | `score: number \| null`, `analysisFailed` |
| `frontend/src/components/CandidateTable.tsx` | N/A display; OHLCV chart fallback |
| `frontend/src/components/StockDetailPanel.tsx` | N/A score display |
| `frontend/src/components/PaperTradingPage.tsx` | N/A score display |

---

## 3. Functions Modified

| Function | Role |
|----------|------|
| `OrchestratorAgent` screener shortlist block | Register prefetched source as `CANDLE_CACHE_DB`; **return BUY+WATCH+REJECT** analysis items |
| `OrchestratorAgent._data_quality_payload` | `unknown` + ≥220 candles → treat as trusted cache; mock only for explicit mock/empty |
| `OrchestratorAgent._enforce_strict_buy_gate` | On true Analysis Failed: `score=0`, `confidence=0`, `trade_plans=[]` (never keep a fake high score) |
| `analysis_preconditions_ok` | Do not reject solely for non-FYERS source when candles + plan are valid |
| `buildCandidateRows` (App + Dashboard) | Composite score only; never screener_score |
| Candidate table chart helper | Equity curve, else last 60 OHLCV closes |

---

## 4. Why Score = 100 Occurred

1. Stock completed analysis (or was shortlisted with a high **screener** score).  
2. Final gate marked REJECT (false Analysis Failed and/or score band).  
3. REJECT analysis object was **omitted** from `analysis.items`.  
4. UI fallback: `match.screener_score` — screener `_weighted_score` is **capped at 100** and often lands near 100 for strong matches.  
5. User saw **Score = 100.0** with no conviction/trade plan — **not** a real composite score of 100.

No recommendation path assigned composite score 100 on failure. The 100 was a **UI fallback to the wrong score field**.

---

## 5. Why “No chart data” Occurred

Mini charts read:

```ts
row.analysisItem?.backtests?.[0]?.equity_curve
```

With `analysisItem` missing (REJECT dropped), equity curve was empty → **“No chart data”**.

Secondary: even with analysis present, empty equity curves now fall back to OHLCV closes.

---

## 6. How the Pipeline Was Fixed

### Correct flow (unchanged analysis stages)

```text
Universe → Market Data → Indicators → … → AI → Composite Score
  → Trade Plan (Entry / SL / Target / R:R)
  → Final score classification
      score ≥ 70 → BUY
      55 ≤ score < 70 → WATCH
      score < 55 → REJECT
```

### Fixes applied

1. **Prefetch source registration** so shortlist candles are not `unknown`/mock.  
2. **Data quality**: full OHLC series is trusted; mock only for `MOCK_FALLBACK` / empty.  
3. **API**: always return full analysis for shortlisted symbols, including REJECT.  
4. **True analysis failure**: clear score/confidence/plans; UI shows **N/A**, never Score=100.  
5. **Frontend**: recommendation score = composite only; screener_score never used for that column.  
6. **Chart**: OHLCV fallback when equity curve empty.

### Recommendation still runs only after full analysis

Technical, AI, confidence, score, and trade plan still run in `RecommendationAgent` / `RecommendationService.build` **before** the final gate. The gate only classifies or marks Analysis Failed.

---

## 7. Validation Results

```text
pytest tests/unit/test_recommendation_fixes.py -v
→ 23 passed
```

Key cases:

| Test | Result |
|------|--------|
| Score bands 82/75/71/70 BUY; 69–55 WATCH; 54/40 REJECT | Pass |
| CANDLE_CACHE_DB + score 80 → BUY with plan | Pass |
| MOCK_FALLBACK → REJECT, score 0, empty plans | Pass |
| unknown source + 250 candles → trusted, not mock | Pass |
| Prefetch-style trusted path score 71.7 → BUY, plans kept | Pass |
| Weak R:R / weak tech do not block BUY when score ≥ 70 | Pass |

---

## 8. Before vs After

| Aspect | Before (broken) | After (fixed) |
|--------|-----------------|---------------|
| Prefetch OHLCV source | `unknown` → mock | Registered / remapped to cache |
| Final gate on shortlist | Often Analysis Failed | Passes when candles + plan + score exist |
| `analysis.items` | BUY + WATCH only | BUY + WATCH + **REJECT** |
| UI score for REJECT | screener_score (≈100) | Real composite, or **N/A** if failed |
| Conviction / Entry / SL / TP | `--` when analysis missing | Populated from returned analysis |
| Chart | “No chart data” | Equity curve or OHLCV |
| Composite Score=100 on failure | Appeared via fallback | **Never** |

### Example stock (conceptual)

| Field | Broken | Fixed |
|-------|--------|-------|
| Score | 100.0 | 71.7 (real composite) |
| Conviction | -- | 72% |
| Entry | -- | 7606–7644 |
| SL / TP | -- | present |
| R:R | -- | present |
| Chart | No chart data | curve / OHLCV |
| Signal | REJECT (false fail) | BUY if score ≥ 70 |

---

## 9. Confirmation

- Recommendations are generated **only after** the full analysis pipeline (tech → news → fund → backtest → sector → AI → score → trade plan).  
- No default composite score of 100 is assigned on failure.  
- Analysis Failed → REJECT with cleared score/plans; UI shows N/A.  
- Successful analysis always returns Score, Conviction, Entry, SL, Target, R:R, trade plan, and chart source data.

---

## 10. Operator re-test checklist

1. Run scanner on the universe.  
2. For each shortlisted symbol with valid history, confirm:  
   - Score is composite (not 100 unless truly 100)  
   - Conviction present  
   - Entry / SL / Target / R:R present  
   - Chart not “No chart data” when OHLCV/backtest exists  
3. Logs: `SCORE SIGNAL PASS` / `SCORE SIGNAL REJECT` / `ANALYSIS_FAILED` only for real failures.  
4. Grep UI payloads: every shortlisted symbol should appear under `analysis.items`.
