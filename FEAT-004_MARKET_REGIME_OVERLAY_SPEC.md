# FEAT-004 — Market Regime Overlay
**Version:** 1.0 — Specification
**Date:** 2026-07-11
**Status:** Ready for implementation

---

## Candidate Idea Submission

| Field | Value |
|---|---|
| **Idea Name** | FEAT-004 — Market Regime Overlay |
| **One-Line Description** | Compute a discrete broad market regime state from benchmark index OHLCV and apply it as a soft score modifier and optional watch-only downgrade inside the | **Primary Component Tag** | `COMP-REC` |
| **Secondary Component Tag** | `None` |
| **Primary Situation Tag** | `SIT-BMR` |
| **Secondary Situation Tags** | `SIT-SR` (sector-strength extension, optional) |
| **Target Implementation Class** | `RecommendationAgent` (primary); `SectorStrengthHelper` utility injected into `RecommendationAgent` (secondary) |
| **Required Input Data** | Benchmark index OHLCV (Nifty 500 or Nifty 50 daily); optional sector index OHLCV per stock mapping |
| **Safe Fallback Behavior** | If index data is unavailable or stale, default to `NEUTRAL` regime; preserve existing standard weights; log `feat004_abstained_reason` |
| **Deterministic Logic Check** | Given the same benchmark OHLCV inputs on the same date, the regime state and score adjustment are always identical — no LLM inference, no randomness. |
| **Explainability Check** | A human can read the logged `market_regime_state`, `benchmark_trend_inputs`, and `feat004_score_adjustment` fields and manually verify the regime classification against a chart. |

---

## 1. Why `COMP-REC` Is the Correct Primary Tag

Under the `CLASSIFICATION_RULEBOOK v1.1` Rule 3 (Gating Order): filters that discard assets **prior to scoring** are `COMP-SCR`; modifications that adjust **final synthesis or post-synthesis state** are `COMP-REC` or `COMP-RISK`.

FEAT-004 does **not** discard stocks before they receive a technical score. It applies a regime-aware modifier to the already-computed composite score, or optionally downgrades `BUY → WATCH` in the synthesis layer. The code delta therefore lives in `RecommendationAgent`, not `ScreenerService`.

**`COMP-SCR` would only be correct if:** the regime state were used to drop entire stock batches from the universe before technical analysis runs. That is explicitly not Stage A or Stage B of this spec. If a future version adds a hard-reject gate at the screener level for `DEFENSIVE` regimes, that portion would be reclassified to `COMP-SCR` at that time.

---

## 2. Required Input Data

| Input | Source | Staleness Limit | Notes |
|---|---|---|---|
| Benchmark index OHLCV | FYERS API primary; yfinance fallback | Must not be older than T-1 (previous trading day) | Nifty 500 preferred; Nifty 50 acceptable fallback |
| Benchmark indicator series | Computed internally from OHLCV | Derived at runtime | SMA20, SMA50, SMA200, 20-day ROC |
| Sector mapping table | Static config file or database table | No real-time requirement | Stock symbol → sector index symbol mapping |
| Sector index OHLCV | FYERS API or yfinance | T-1 minimum | One series per sector present in the universe |

**No new external databases are required.** The benchmark and sector index series are the same OHLCV format already consumed by the existing data layer.

---

## 3. Derived Fields (Benchmark Only)

All fields below are computed once per trading session, not per stock:

| Field | Formula | Type |
|---|---|---|
| `bm_close` | Latest closing price of benchmark | float |
| `bm_sma50` | Simple moving average, 50 periods | float |
| `bm_sma200` | Simple moving average, 200 periods | float |
| `bm_sma20_slope` | `(SMA20[today] - SMA20[5 days ago]) / SMA20[5 days ago]` | float |
| `bm_roc20` | `(Close[today] - Close[20 days ago]) / Close[20 days ago]` | float |
| `bm_above_sma50` | `bm_close > bm_sma50` | bool |
| `bm_sma50_above_sma200` | `bm_sma50 > bm_sma200` | bool |
| `bm_sma20_slope_positive` | `bm_sma20_slope > 0.0` | bool |
| `bm_roc20_positive` | `bm_roc20 > 0.0` | bool |

---

## 4. Regime State Definitions

Exactly four discrete states, evaluated top-to-bottom. First matching state wins.

| State | Code | Conditions (all must be true) |
|---|---|---|
| **FAVORABLE** | `FAV` | `bm_above_sma50 = True` AND `bm_sma50_above_sma200 = True` AND `bm_sma20_slope_positive = True` AND `bm_roc20_positive = True` |
| **NEUTRAL** | `NEU` | `bm_above_sma50 = True` AND `bm_sma50_above_sma200 = True` AND at least one of slope or ROC is False |
| **CAUTIOUS** | `CAU` | `bm_above_sma50 = False` OR (`bm_sma50_above_sma200 = False` AND `bm_sma20_slope_positive = True`) |
| **DEFENSIVE** | `DEF` | `bm_above_sma50 = False` AND `bm_sma50_above_sma200 = False` AND `bm_sma20_slope_positive = False` |
| **ABSTAINED** | `ABS` | Benchmark data unavailable, stale, or insufficient history | 

> **Tie-breaking rule:** If exactly two conditions from NEUTRAL and CAUTIOUS fire simultaneously, default to `CAUTIOUS`. When in doubt, be conservative.

---

## 5. Downstream Actions by Regime State

### Stage A — Shadow Mode (Logging Only, No Score Effect)

| Regime State | Score Adjustment | BUY Downgrade | Action |
|---|---|---|---|
| FAVORABLE | 0 | No | Log state only |
| NEUTRAL | 0 | No | Log state only |
| CAUTIOUS | 0 | No | Log state only |
| DEFENSIVE | 0 | No | Log state only |
| ABSTAINED | 0 | No | Log `feat004_abstained_reason` |

**Purpose of Stage A:** Run for a minimum of 30 trading sessions. Observe correlation between logged regime states and actual recommendation outcomes. Validate that CAUTIOUS and DEFENSIVE states predict higher false-positive rates before activating Stage B.

### Stage B — Score-Affecting Mode (Activate After Validation)

All adjustments are applied to the **final composite score** computed by `RecommendationAgent`, **after** the standard weighted synthesis but **before** the Strict Buy Gate evaluation.

| Regime State | Composite Score Delta | BUY→WATCH Downgrade Threshold | Notes |
|---|---|---|---|
| FAVORABLE | +2.0 points | None applied | Mild bonus; does not push borderline WATCH to BUY |
| NEUTRAL | 0.0 points | None | Standard logic unchanged |
| CAUTIOUS | -3.0 points | Apply if adjusted score < 74 | Soft penalty; borderline BUYs may slip to WATCH |
| DEFENSIVE | -5.0 points | Apply if adjusted score < 77 | Stronger penalty; only high-conviction BUYs survive |
| ABSTAINED | 0.0 points | None | Preserve existing logic exactly |

**Constraint:** The FAVORABLE bonus of +2.0 cannot push a score from WATCH territory to BUY. Cap: `if regime == FAV and pre_adjustment_score < 72: final_score = min(pre_adjustment_score + 2.0, 71.99)`.

**Constraint:** The regime modifier adjusts the composite score only. It does not alter the raw technical score used by the Strict Buy Gate. The Gate continues to evaluate against its own criteria unchanged.

---

## 6. Sector-Strength Extension (v1 — Explanation Only)

### Availability gate
This section executes **only if** both of these conditions are met:
1. A sector mapping exists for the current stock symbol (static config file).
2. A sector index OHLCV series with ≥ 50 candles is available.

If either condition fails: set `sector_regime_state = UNKNOWN`, log reason, and do not compute further.

### Computation

| Field | Formula |
|---|---|
| `sector_roc20` | `(SectorClose[today] - SectorClose[20 days ago]) / SectorClose[20 days ago]` |
| `benchmark_roc20` | Already computed from Step 3 |
| `relative_strength_ratio` | `sector_roc20 / benchmark_roc20` (safe divide: if benchmark_roc20 == 0, set ratio = 1.0) |
| `sector_regime_state` | See table below |

| `relative_strength_ratio` | `sector_regime_state` |
|---|---|
| > 1.10 | `STRONG` |
| 0.90 – 1.10 | `NEUTRAL` |
| < 0.90 | `WEAK` |

### v1 Behavior

- `sector_regime_state` is written to the explanation log and recommendation output metadata **only**.
- It does **not** alter BUY/WATCH/REJECT in v1.
- A human reviewing the output can see: `"Sector: IT — STRONG vs Nifty 500"`.
- v2 may use this to apply an additional soft modifier inside `COMP-REC` once backtested independently.

---

## 7. Safe Fallback Behavior

| Failure Scenario | Behavior | Log Entry |
|---|---|---|
| Benchmark index series not fetched | `market_regime_state = ABSTAINED`; preserve standard weights | `feat004_abstained_reason = benchmark_fetch_failed` |
| Benchmark has fewer than 200 candles | `market_regime_state = ABSTAINED`; preserve standard weights | `feat004_abstained_reason = insufficient_benchmark_history` |
| Benchmark data is stale (older than T-1) | `market_regime_state = ABSTAINED`; preserve standard weights | `feat004_abstained_reason = benchmark_data_stale` |
| Sector mapping missing for stock | `sector_regime_state = UNKNOWN` | `feat004_sector_abstained_reason = no_sector_mapping` |
| Sector index series unavailable | `sector_regime_state = UNKNOWN` | `feat004_sector_abstained_reason = sector_index_unavailable` |
| Any exception inside FEAT-004 logic | Catch, log, return `ABSTAINED`; do not propagate | `feat004_abstained_reason = exception: {error_type}` |

**No exception from FEAT-004 may propagate into the main recommendation path.** The entire FEAT-004 block must be wrapped in a try/except that catches all exceptions and defaults to ABSTAINED.

---

## 8. Logging Schema

All fields below must be written to the recommendation output and to the session log for every processed stock:

```
feat004_enabled              = True | False
feat004_stage                = SHADOW | ACTIVE | ABSTAINED
market_regime_state          = FAV | NEU | CAU | DEF | ABS
benchmark_symbol_used        = e.g. "NIFTY500" | "NIFTY50" | null
benchmark_trend_inputs       = {
    bm_close: float,
    bm_sma50: float,
    bm_sma200: float,
    bm_above_sma50: bool,
    bm_sma50_above_sma200: bool,
    bm_sma20_slope: float,
    bm_roc20: float
}
feat004_score_adjustment     = float (e.g. -3.0, 0.0, +2.0)
feat004_pre_adjustment_score = float
feat004_post_adjustment_score= float
feat004_watch_downgrade_applied = True | False
feat004_abstained_reason     = string | null
sector_mapped                = True | False
sector_index_symbol          = string | null
sector_relative_strength_ratio = float | null
sector_regime_state          = STRONG | NEUTRAL | WEAK | UNKNOWN
feat004_sector_abstained_reason = string | null
```

**Human-readable explanation string (generated from logs):**
> `"Market regime: CAUTIOUS (index below SMA50, SMA50 below SMA200). Score adjusted by -3.0 (72.4 → 69.4). BUY downgraded to WATCH. Sector: IT — STRONG. Benchmark: NIFTY500."`

---

## 9. Backtest and Walk-Forward Validation Plan

### Data split

| Period | Label | Approximate NSE Regime |
|---|---|---|
| In-sample set A | Bull | 2020-04-01 to 2021-09-30 |
| In-sample set B | Sideways/Choppy | 2021-10-01 to 2022-03-31 |
| In-sample set C | Bear/Volatile | 2022-04-01 to 2022-12-31 |
| Out-of-sample | Mixed | 2023-01-01 to 2024-06-30 |

### Isolation method

1. Run backtest with FEAT-004 **disabled** (baseline).
2. Run backtest with FEAT-004 Stage B **enabled** (treatment).
3. Compare metrics between baseline and treatment for each period.

### Success metrics

| Metric | Minimum Acceptance | Rollback Trigger |
|---|---|---|
| False-positive reduction (CAUTIOUS + DEFENSIVE periods) | ≥ 5% fewer losing BUY trades | — |
| Missed winner rate (false negatives introduced) | ≤ 3% increase in missed profitable BUY trades | > 8% increase triggers rollback |
| Win rate (overall BUY trades) | Neutral or improved | — |
| Profit factor | Neutral or improved | Drops > 10% vs baseline triggers rollback |
| BUY→WATCH downgrade count (CAUTIOUS) | Must be > 0 in bear periods (proves feature fires) | — |
| BUY→WATCH downgrade count (FAVORABLE) | Must be 0 (bonus must not cause spurious downgrades) | Any > 0 triggers bug fix |

### Rollback criteria

- Missed winner rate increases by more than 8% in the out-of-sample period.
- Profit factor drops more than 10% vs baseline.
- FEAT-004 fires incorrectly in FAVORABLE regime (downgrades or penalizes when it should not).
- Any unhandled exception propagates past the FEAT-004 try/except boundary.

**Rollback action:** Set `feat004_enabled = False` in config; no code changes required.

---

## 10. Main Failure Modes

| Failure Mode | Risk Level | Mitigation |
|---|---|---|
| Benchmark data fetch fails silently and ABSTAINED is not logged | High | Mandatory log check in unit test |
| Score adjustment pushes a WATCH-class stock to BUY via the +2.0 FAVORABLE cap miss | High | Enforce cap in code: `min(score + 2.0, 71.99)` if pre-score < 72 |
| Sector mapping produces wrong sector index | Medium | Config file peer-reviewed before activation; mapping validated against known sector constituents |
| DEFENSIVE regime over-fires in choppy-but-not-bear markets | Medium | Monitor BUY→WATCH downgrade rate during Stage A shadow mode; tighten conditions if necessary |
| Regime state computed from stale T-2 data on a holiday | Low | Staleness check enforced before computation; defaults to ABSTAINED if stale |
| Exception inside sector helper propagates to main path | Low | Sector block has independent try/except; outer FEAT-004 block has own try/except |

---

## 11. Brownfield Safety Confirmation

| Constraint | Status |
|---|---|
| No existing hard filters removed or weakened | ✅ Confirmed |
| Strict Buy Gate criteria unchanged | ✅ Confirmed (regime modifier adjusts composite score, not raw TA score) |
| No new autonomous agents created | ✅ Confirmed (SectorStrengthHelper is a utility function, not an agent) |
| BUY/WATCH/REJECT thresholds unchanged | ✅ Confirmed |
| Deterministic: same inputs → same outputs | ✅ Confirmed (no LLM inference in any path) |
| Missing data defaults to safe neutral behavior | ✅ Confirmed |
| No exceptions propagate to recommendation path | ✅ Confirmed (double try/except boundary) |
| Rollback requires only config flag change | ✅ Confirmed |

---

## 12. Implementation Stages

### Stage A — Shadow Mode
**Prerequisite:** None. Can be activated immediately.

- Compute `market_regime_state` and all derived fields every session.
- Write full logging schema to output.
- Apply **zero** score adjustment and **zero** downgrades.
- Run for a minimum of **30 trading sessions**.
- After Stage A: review logged `market_regime_state` distribution and correlation with actual BUY outcome accuracy.

### Stage B — Score-Affecting Mode
**Prerequisite:** Stage A validation passes all success metrics.

- Activate score adjustments per Section 5.
- Activate BUY→WATCH downgrade logic per Section 5.
- Log `feat004_stage = ACTIVE`.
- Monitor rollback criteria for first 30 sessions after activation.

---

## 13. Final Recommendation

**SHADOW MODE FIRST (Stage A), then Stage B after validation.**

Rationale: The regime overlay uses simple, robust indicators. The logic is deterministic and the fallback is safe. However, the score deltas (-3.0, -5.0) interact with existing thresholds in ways that can only be fully verified against live NSE data across multiple regime periods. Stage A costs nothing and provides the empirical evidence needed to tune the deltas before they affect real recommendations.

---

*End of FEAT-004 Specification v1.0*
