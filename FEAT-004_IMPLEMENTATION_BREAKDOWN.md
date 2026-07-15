# FEAT-004 — Market Regime Overlay: Implementation Breakdown
**Version:** 1.0
**Date:** 2026-07-11
**Status:** Pre-implementation task breakdown. No production code.

---

## 1. Integration Point

### Exact hook location
`RecommendationAgent.generate_recommendation()` (or equivalent top-level synthesis method).

The hook fires **after** the weighted composite score is computed and **before** the Strict Buy Gate evaluation block. This is a single insertion point: one function call to `apply_feat004_regime_overlay(composite_score, recommendation_context)` that returns `(adjusted_score, feat004_log_payload)`.

### What inputs are already available at this location
- `composite_score: float` — weighted sum of Technical, Fundamental, Backtest, News scores
- `raw_technical_score: float` — already computed by TechnicalAnalysisService; must not be modified by FEAT-004
- `symbol: str` — current stock ticker
- `data_source_is_primary: bool` — already tracked for Buy Gate (FYERS primary flag)
- `recommendation_context: dict` — in-flight object carrying all intermediate outputs

### What new inputs must be passed in
- `benchmark_ohlcv: pd.DataFrame | None` — pre-fetched daily OHLCV for the benchmark index (Nifty 500 or Nifty 50); fetched once per session, not per stock
- `sector_mapping: dict[str, str] | None` — static map of `{symbol: sector_index_symbol}`; loaded from config at session start
- `sector_ohlcv_cache: dict[str, pd.DataFrame] | None` — per-session cache of pre-fetched sector index OHLCV; keyed by sector index symbol
- `feat004_config: dict` — all config flags defined in Section 5

### Why this hook location is correct
Under `CLASSIFICATION_RULEBOOK v1.1` Rule 3 (Gating Order): the composite score is a synthesis output of `RecommendationAgent`. Modifying it here is a `COMP-REC` delta. The raw technical score consumed by the Strict Buy Gate is read from `raw_technical_score`, which FEAT-004 never touches. The Gate therefore evaluates its own unchanged input. If FEAT-004 were placed inside `ScreenerService`, it would be a `COMP-SCR` pre-filter; it is not, because no stock is discarded before receiving a technical score.

---

## 2. New Helper Functions

### 2.1 `resolve_benchmark_ohlcv`
- **Purpose:** Fetch or retrieve the benchmark index OHLCV from the existing data layer. Returns the series or `None` with a reason string.
- **Inputs:**
  - `benchmark_symbols: list[str]` — ordered priority list, e.g. `["NIFTY500", "NIFTY50"]`
  - `min_candles: int` — minimum required rows (default: 220)
  - `staleness_limit_days: int` — max age of last candle in calendar days (default: 1)
  - `data_fetcher` — existing data access object already used by the pipeline
- **Outputs:** `tuple[pd.DataFrame | None, str | None, str | None]`
  - `(ohlcv_df, symbol_used, failure_reason)`
  - On success: `(df, "NIFTY500", None)`
  - On failure: `(None, None, "benchmark_fetch_failed" | "insufficient_benchmark_history" | "benchmark_data_stale")`
- **Safe fallback:** Never raises. Returns `(None, None, reason_string)` on any exception. All exceptions caught internally; error type appended to reason string.

---

### 2.2 `compute_benchmark_indicators`
- **Purpose:** Compute the five boolean/float fields derived from benchmark OHLCV needed for regime classification.
- **Inputs:**
  - `ohlcv_df: pd.DataFrame` — must have `close` column; must have ≥ 200 rows
- **Outputs:** `dict` with exactly these keys:
  ```
  {
    "bm_close": float,
    "bm_sma50": float,
    "bm_sma200": float,
    "bm_sma20_slope": float,
    "bm_roc20": float,
    "bm_above_sma50": bool,
    "bm_sma50_above_sma200": bool,
    "bm_sma20_slope_positive": bool,
    "bm_roc20_positive": bool
  }
  ```
- **Safe fallback:** If any calculation fails (e.g., division by zero in ROC), set the affected bool fields to `False` and float fields to `0.0`. Do not raise. Return whatever partial result is computable.
- **Notes:** SMA20 slope = `(SMA20[-1] - SMA20[-6]) / SMA20[-6]`. ROC20 = `(close[-1] - close[-21]) / close[-21]`. Use iloc indexing, not date-based.

---

### 2.3 `classify_market_regime`
- **Purpose:** Map the benchmark indicator dict to exactly one of five discrete regime codes.
- **Inputs:**
  - `indicators: dict` — output of `compute_benchmark_indicators`; may also be `None` if benchmark unavailable
- **Outputs:** `str` — one of: `"FAV"`, `"NEU"`, `"CAU"`, `"DEF"`, `"ABS"`
- **Classification logic (evaluated top-to-bottom, first match wins):**
  1. If `indicators is None`: return `"ABS"`
  2. If `bm_above_sma50=True` AND `bm_sma50_above_sma200=True` AND `bm_sma20_slope_positive=True` AND `bm_roc20_positive=True`: return `"FAV"`
  3. If `bm_above_sma50=True` AND `bm_sma50_above_sma200=True` AND (slope or ROC is False): return `"NEU"`
  4. If `bm_above_sma50=False` OR (`bm_sma50_above_sma200=False` AND `bm_sma20_slope_positive=True`): return `"CAU"`
  5. If `bm_above_sma50=False` AND `bm_sma50_above_sma200=False` AND `bm_sma20_slope_positive=False`: return `"DEF"`
  6. Default (no match): return `"NEU"` (conservative tie-break)
- **Safe fallback:** Entire function body wrapped in try/except; returns `"ABS"` on any exception.

---

### 2.4 `apply_regime_score_modifier`
- **Purpose:** Compute the score delta and BUY→WATCH downgrade decision based on regime state and current stage setting.
- **Inputs:**
  - `regime_state: str` — one of the five codes
  - `composite_score: float` — pre-adjustment score
  - `current_label: str` — `"BUY"`, `"WATCH"`, or `"REJECT"` from pre-FEAT-004 synthesis
  - `stage: str` — `"SHADOW"` or `"ACTIVE"`
  - `score_deltas: dict` — from config: `{"FAV": 2.0, "NEU": 0.0, "CAU": -3.0, "DEF": -5.0, "ABS": 0.0}`
  - `downgrade_thresholds: dict` — from config: `{"CAU": 74.0, "DEF": 77.0}`
  - `buy_threshold: float` — existing BUY threshold (72.0); used for FAVORABLE cap
- **Outputs:** `tuple[float, str, bool, float]`
  - `(adjusted_score, adjusted_label, downgrade_applied, score_delta_applied)`
- **Logic:**
  - If `stage == "SHADOW"`: return `(composite_score, current_label, False, 0.0)` immediately.
  - Compute `raw_delta = score_deltas.get(regime_state, 0.0)`
  - If `regime_state == "FAV"` AND `composite_score < buy_threshold`:
    - `adjusted_score = min(composite_score + raw_delta, buy_threshold - 0.01)` — cap prevents WATCH→BUY
  - Else: `adjusted_score = composite_score + raw_delta`
  - Determine `downgrade_applied`:
    - If `current_label == "BUY"` AND `regime_state in ("CAU", "DEF")`:
      - threshold = `downgrade_thresholds.get(regime_state)`
      - If `adjusted_score < threshold`: `adjusted_label = "WATCH"`, `downgrade_applied = True`
    - Else: `adjusted_label = current_label`, `downgrade_applied = False`
  - Return `(adjusted_score, adjusted_label, downgrade_applied, raw_delta)`
- **Safe fallback:** Returns `(composite_score, current_label, False, 0.0)` on any exception.

---

### 2.5 `compute_sector_strength` (optional)
- **Purpose:** Compute relative strength of a stock's sector vs benchmark. Returns metadata only; no label effect in v1.
- **Inputs:**
  - `symbol: str`
  - `sector_mapping: dict[str, str] | None`
  - `sector_ohlcv_cache: dict[str, pd.DataFrame] | None`
  - `benchmark_roc20: float | None` — already computed in Step 2.2; pass through to avoid re-computation
  - `min_candles: int` — minimum sector series length (default: 50)
- **Outputs:** `dict` with exactly these keys:
  ```
  {
    "sector_mapped": bool,
    "sector_index_symbol": str | None,
    "sector_roc20": float | None,
    "relative_strength_ratio": float | None,
    "sector_regime_state": "STRONG" | "NEUTRAL" | "WEAK" | "UNKNOWN",
    "sector_abstained_reason": str | None
  }
  ```
- **Classification:**
  - `ratio > 1.10` → `"STRONG"`
  - `0.90 <= ratio <= 1.10` → `"NEUTRAL"`
  - `ratio < 0.90` → `"WEAK"`
  - Any missing input → `"UNKNOWN"`
- **Safe fallback behaviors (return UNKNOWN with reason):**
  - `sector_mapping is None` → `sector_abstained_reason = "no_sector_mapping_config"`
  - `symbol not in sector_mapping` → `sector_abstained_reason = "symbol_not_in_mapping"`
  - `sector_ohlcv_cache is None or sector_index not in cache` → `sector_abstained_reason = "sector_index_unavailable"`
  - `len(sector_df) < min_candles` → `sector_abstained_reason = "insufficient_sector_history"`
  - `benchmark_roc20 is None or benchmark_roc20 == 0.0` → `relative_strength_ratio = 1.0` (safe divide; log as neutral)
  - Any exception → `sector_abstained_reason = f"exception:{type(e).__name__}"`

---

### 2.6 `build_feat004_log_payload`
- **Purpose:** Assemble the complete log dict from all intermediate FEAT-004 outputs.
- **Inputs:** All intermediate values produced by helpers 2.1–2.5 plus config metadata.
- **Outputs:** `dict` — fully populated logging schema (see Section 6).
- **Safe fallback:** Always returns a valid dict; missing values set to `None` explicitly, never omitted.

---

### 2.7 `apply_feat004_regime_overlay` (orchestrator)
- **Purpose:** Top-level entry point called from `RecommendationAgent`. Calls all sub-helpers in order and returns final adjusted values.
- **Inputs:**
  - `composite_score: float`
  - `current_label: str`
  - `symbol: str`
  - `benchmark_ohlcv: pd.DataFrame | None`
  - `sector_mapping: dict | None`
  - `sector_ohlcv_cache: dict | None`
  - `feat004_config: dict`
- **Outputs:** `tuple[float, str, dict]`
  - `(adjusted_score, adjusted_label, feat004_log_payload)`
- **Safe fallback:** Entire body in outer try/except; on any unhandled exception returns `(composite_score, current_label, {"feat004_abstained_reason": f"exception:{type(e).__name__}", "feat004_stage": "ABSTAINED"})`.

---

## 3. Execution Order

```
1. [EXISTING] All agent outputs ready:
      technical_score, fundamental_score, backtest_score, news_score

2. [EXISTING] Weighted composite score computed:
      composite_score = weighted_sum(technical, fundamental, backtest, news)
      current_label   = classify(composite_score)  # BUY / WATCH / REJECT
      raw_technical_score preserved and passed separately to Strict Buy Gate

3. [FEAT-004] Benchmark resolution:
      (benchmark_df, symbol_used, fail_reason) = resolve_benchmark_ohlcv(...)

4. [FEAT-004] Regime classification:
      if benchmark_df is not None:
          indicators = compute_benchmark_indicators(benchmark_df)
      else:
          indicators = None
      regime_state = classify_market_regime(indicators)

5. [FEAT-004] Stage-based score adjustment:
      (adj_score, adj_label, downgrade_applied, delta_applied) =
          apply_regime_score_modifier(regime_state, composite_score, current_label, ...)

6. [FEAT-004 optional] Sector strength metadata:
      sector_result = compute_sector_strength(symbol, sector_mapping, sector_ohlcv_cache,
                                              benchmark_roc20, ...)

7. [FEAT-004] Log payload assembly:
      feat004_log = build_feat004_log_payload(all intermediate values)

8. [EXISTING] Strict Buy Gate evaluation:
      gate_input_score = raw_technical_score    # UNCHANGED
      gate_result      = strict_buy_gate(raw_technical_score, rr_ratio,
                                         data_source_primary, history_depth)
      if gate_result.downgrade:
          adj_label = "WATCH"

9. [EXISTING] Final output assembly:
      recommendation_output = {
          ...existing fields...,
          "composite_score": adj_score,
          "label": adj_label,
          "feat004": feat004_log
      }
```

---

## 4. Data Contract

The following fields must be added to the in-memory recommendation dict. No schema migration or new storage is required; these are additions to the existing in-flight Python dict.

```python
recommendation_output["feat004"] = {
    # Core
    "feat004_enabled":                bool,
    "feat004_stage":                  str,        # "SHADOW" | "ACTIVE" | "ABSTAINED"
    # Benchmark
    "market_regime_state":            str,        # "FAV" | "NEU" | "CAU" | "DEF" | "ABS"
    "benchmark_symbol_used":          str | None,
    "benchmark_trend_inputs": {
        "bm_close":                   float | None,
        "bm_sma50":                   float | None,
        "bm_sma200":                  float | None,
        "bm_above_sma50":             bool  | None,
        "bm_sma50_above_sma200":      bool  | None,
        "bm_sma20_slope":             float | None,
        "bm_roc20":                   float | None,
    },
    # Score adjustment
    "feat004_pre_adjustment_score":   float,
    "feat004_score_adjustment":       float,
    "feat004_post_adjustment_score":  float,
    "feat004_watch_downgrade_applied": bool,
    "feat004_abstained_reason":       str | None,
    # Sector
    "sector_mapped":                  bool,
    "sector_index_symbol":            str | None,
    "sector_roc20":                   float | None,
    "sector_relative_strength_ratio": float | None,
    "sector_regime_state":            str,        # "STRONG" | "NEUTRAL" | "WEAK" | "UNKNOWN"
    "feat004_sector_abstained_reason": str | None,
    # Explanation
    "feat004_explanation":            str,
}
```

**`feat004_explanation` generation rule:**
```
"Market regime: {state_label} ({condition_summary}). Score adjusted by {delta:+.1f} "
"({pre:.1f} -> {post:.1f}). {'BUY downgraded to WATCH. ' if downgraded else ''}"
"Sector: {sector_index} - {sector_regime}. Benchmark: {benchmark_symbol}."
```

---

## 5. Config Flags

All flags live in the existing application config (YAML, JSON, or Python dict). No new config system required.

```yaml
feat004:
  enabled: true                   # Master switch. false = FEAT-004 never runs.
  stage: "SHADOW"                 # "SHADOW" | "ACTIVE"
  benchmark_symbols:              # Priority-ordered. First fetchable wins.
    - "NIFTY500"
    - "NIFTY50"
  min_benchmark_candles: 220      # Minimum candles required for benchmark series.
  staleness_limit_days: 1         # Max calendar days since last benchmark candle.
  sector_mapping_enabled: true    # false = sector helper never runs.
  sector_min_candles: 50          # Minimum candles required for sector series.
  score_deltas:                   # Applied only in ACTIVE stage.
    FAV:  2.0
    NEU:  0.0
    CAU: -3.0
    DEF: -5.0
    ABS:  0.0
  buy_downgrade_thresholds:       # BUY->WATCH if adj_score below this AND regime matches.
    CAU: 74.0
    DEF: 77.0
  favorable_cap_below_buy: true   # true = FAV bonus cannot push WATCH score to BUY.
  buy_threshold: 72.0             # Mirror of existing BUY threshold; used for FAV cap.
```

---

## 6. Logging Contract

Every field below is written on every stock processed, regardless of whether FEAT-004 fires or abstains.

| Field | Populated When | Value if Abstained |
|---|---|---|
| `feat004_enabled` | Always | `false` |
| `feat004_stage` | Always | `"ABSTAINED"` |
| `market_regime_state` | Always | `"ABS"` |
| `benchmark_symbol_used` | Benchmark resolved successfully | `null` |
| `benchmark_trend_inputs.*` | Benchmark indicators computed | All `null` |
| `feat004_pre_adjustment_score` | Always | `composite_score` (unchanged) |
| `feat004_score_adjustment` | Always | `0.0` |
| `feat004_post_adjustment_score` | Always | `composite_score` (unchanged) |
| `feat004_watch_downgrade_applied` | Always | `false` |
| `feat004_abstained_reason` | FEAT-004 abstains for any reason | `null` when active |
| `sector_mapped` | Always | `false` |
| `sector_index_symbol` | Sector mapping found | `null` |
| `sector_roc20` | Sector series available | `null` |
| `sector_relative_strength_ratio` | Ratio computed | `null` |
| `sector_regime_state` | Always | `"UNKNOWN"` |
| `feat004_sector_abstained_reason` | Sector abstains | `null` when computed |
| `feat004_explanation` | Always | `"FEAT-004 abstained: {reason}"` |

---

## 7. Failure Handling

### Boundary 1 — Outer orchestrator (`apply_feat004_regime_overlay`)
- Wraps the entire FEAT-004 execution.
- **Catches:** `Exception`
- **Returns:** `(original_composite_score, original_label, {"feat004_abstained_reason": f"exception:{type(e).__name__}", "feat004_stage": "ABSTAINED"})`
- **Effect on recommendation:** None. Original score and label pass through unchanged.

### Boundary 2 — Benchmark resolver (`resolve_benchmark_ohlcv`)
- **Catches:** `Exception` (network errors, data format errors, empty DataFrame)
- **Returns:** `(None, None, f"benchmark_fetch_failed:exception:{type(e).__name__}")`
- **Downstream effect:** `classify_market_regime(None)` returns `"ABS"`.

### Boundary 3 — Indicator calculator (`compute_benchmark_indicators`)
- **Catches:** `Exception` (ZeroDivisionError, IndexError on short series, NaN propagation)
- **Returns:** Dict with all fields set to `None` or `False`; does not raise.
- **Downstream effect:** `classify_market_regime` receives a partial dict; falls through to default `"NEU"` if no condition fires, or `"ABS"` if dict is None.

### Boundary 4 — Regime classifier (`classify_market_regime`)
- **Catches:** `Exception`
- **Returns:** `"ABS"`

### Boundary 5 — Score modifier (`apply_regime_score_modifier`)
- **Catches:** `Exception`
- **Returns:** `(composite_score, current_label, False, 0.0)` — original values unchanged.

### Boundary 6 — Sector helper (`compute_sector_strength`)
- **Independent** from all other boundaries. Runs inside its own try/except.
- **Catches:** `Exception`
- **Returns:** `{"sector_regime_state": "UNKNOWN", "sector_abstained_reason": f"exception:{type(e).__name__}", ...all other fields: None}`
- **Effect on recommendation:** None in v1.

---

## 8. Unit Test Plan

All tests are deterministic: fixed inputs, fixed expected outputs. No live data.

| # | Test Name | Input | Expected Output |
|---|---|---|---|
| 1 | `test_regime_favorable` | All 4 conditions True | `regime_state == "FAV"` |
| 2 | `test_regime_neutral` | SMA cross True, slope False | `regime_state == "NEU"` |
| 3 | `test_regime_cautious` | `bm_above_sma50 = False`, slope True | `regime_state == "CAU"` |
| 4 | `test_regime_defensive` | All 3 negative conditions True | `regime_state == "DEF"` |
| 5 | `test_regime_abstained_none_input` | `indicators = None` | `regime_state == "ABS"` |
| 6 | `test_shadow_mode_no_score_change` | `stage="SHADOW"`, regime=`DEF`, score=80.0 | `adjusted_score == 80.0`, `downgrade_applied == False` |
| 7 | `test_active_cautious_penalty` | `stage="ACTIVE"`, regime=`CAU`, score=75.0 | `adjusted_score == 72.0`, `downgrade_applied == True` (< 74.0 threshold) |
| 8 | `test_active_defensive_penalty` | `stage="ACTIVE"`, regime=`DEF`, score=78.0 | `adjusted_score == 73.0`, `downgrade_applied == True` (< 77.0 threshold) |
| 9 | `test_favorable_cap_prevents_watch_to_buy` | `stage="ACTIVE"`, regime=`FAV`, score=70.0 | `adjusted_score == 71.99`, `label == "WATCH"` |
| 10 | `test_favorable_no_cap_when_already_buy` | `stage="ACTIVE"`, regime=`FAV`, score=80.0 | `adjusted_score == 82.0`, `label == "BUY"` |
| 11 | `test_benchmark_fetch_failure_defaults_to_abs` | `benchmark_ohlcv = None` | `market_regime_state == "ABS"`, `score_adjustment == 0.0` |
| 12 | `test_benchmark_stale_defaults_to_abs` | Last candle date = T-3 | `feat004_abstained_reason == "benchmark_data_stale"` |
| 13 | `test_sector_no_mapping_returns_unknown` | `sector_mapping = None` | `sector_regime_state == "UNKNOWN"`, `sector_abstained_reason == "no_sector_mapping_config"` |
| 14 | `test_sector_symbol_not_in_mapping` | symbol not in mapping dict | `sector_regime_state == "UNKNOWN"`, `sector_abstained_reason == "symbol_not_in_mapping"` |
| 15 | `test_sector_strong` | sector_roc20=0.05, bm_roc20=0.03 (ratio=1.67) | `sector_regime_state == "STRONG"` |
| 16 | `test_sector_weak` | sector_roc20=0.01, bm_roc20=0.03 (ratio=0.33) | `sector_regime_state == "WEAK"` |
| 17 | `test_outer_exception_returns_original_score` | Inject exception inside orchestrator | Returns original `composite_score` and `label` unchanged |
| 18 | `test_log_payload_always_complete` | ABSTAINED path | All log fields present, none missing (no KeyError) |
| 19 | `test_strict_buy_gate_receives_unmodified_raw_ta_score` | ACTIVE mode, regime=DEF | `raw_technical_score` passed to gate equals pre-FEAT-004 TA score |
| 20 | `test_reject_label_unchanged_by_regime` | `current_label = "REJECT"`, any regime | `adjusted_label == "REJECT"` (regime cannot upgrade REJECT) |

---

## 9. Stage A Rollout (Shadow Mode)

1. Set `feat004.enabled = true` and `feat004.stage = "SHADOW"` in config.
2. `apply_regime_score_modifier` returns the original score immediately when `stage == "SHADOW"`. No score or label is changed.
3. The `feat004` log dict is fully populated on every stock: regime state, indicators, sector metadata, explanation.
4. All existing recommendation outputs are unchanged.
5. Log fields are written into the per-stock recommendation dict and any existing session log file.
6. After each session, review the distribution of `market_regime_state` values and cross-reference with same-day `label` outcomes.
7. Run Stage A for a minimum of 30 trading sessions before evaluating Stage B readiness.
8. **To disable Stage A without restarting:** Set `feat004.enabled = false`. No code change required.

---

## 10. Stage B Activation

### Activation condition
All of the following must be confirmed from Stage A logs:
- `market_regime_state` distributes across at least 3 of the 4 states over the observation window (confirms the classifier fires).
- No `feat004_abstained_reason` pattern indicates a systematic data availability problem.
- No unit test regressions.
- Backtest comparison (Section 9 of the spec) passes all success metrics.

### What changes at activation
1. Set `feat004.stage = "ACTIVE"` in config. One line change.
2. `apply_regime_score_modifier` now applies `score_deltas` and evaluates downgrade thresholds.
3. `feat004_score_adjustment` in logs will be non-zero for CAU, DEF, and FAV regimes.
4. `feat004_watch_downgrade_applied` may be `true` for borderline BUY calls in CAU/DEF regimes.
5. No other code change. The Stage A code path is the Stage B code path; only the config flag differs.

### Rollback from Stage B
1. Set `feat004.stage = "SHADOW"` in config. Instant effect on next session.
2. All scores and labels revert to pre-FEAT-004 values.
3. Log payload continues to be written (useful for post-incident analysis).

---

*End of FEAT-004 Implementation Breakdown v1.0*
