# FEAT-007 — Sector Relative Strength Overlay
**Version:** 1.1 — Specification
**Date:** 2026-07-12
**Status:** Ready for implementation (revised per ADR-003)

---

## Revision History

| Version | Date | Author | Change |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-07-11 | Specification author | Initial specification. Used the ratio formula (`sector_roc20 / benchmark_roc20`) with thresholds 1.10 / 0.90. |
| 1.1 | 2026-07-12 | Principal Software Architect | **Formula revision per ADR-003 (Accepted, Option C-Revised).** ADR-003's evidence report (10,827 real NSE observations) conclusively rejected the ratio formula: 40.3% binary disagreement, 27.2% quantile-matched disagreement, Spearman ρ = 0.188. The ratio is numerically unstable near benchmark ROC ≈ 0 (values range to ±4,453) and sign-flips in 93–96% of down-market observations. The difference formula (`sector_roc20 − benchmark_roc20`) is now canonical. This revision replaces every ratio-formula reference with the difference formula, updates classification from three-state (STRONG/NEUTRAL/WEAK on ratio thresholds) to binary (STRENGTH/WEAK on the difference scale), removes the safe-divide fallback (the difference formula is well-defined at all benchmark values), and updates all worked examples, log fields, and unit-test inputs accordingly. The score-delta mechanic (+1.5/−3.0), STRONG cap, REJECT immutability, pre-Gate placement, and evidence level are **unchanged** — ADR-003 scopes the change to the formula only. See `docs/adr/ADR-003_sector_relative_strength_formula.md` for the full decision record. |

---

## Candidate Idea Submission

| Field | Value |
| :--- | :--- |
| **Idea Name** | FEAT-007 — Sector Relative Strength Overlay |
| **One-Line Description** | Compute each stock's sector index relative strength vs the benchmark and apply it as a soft composite-score modifier with a borderline BUY→WATCH downgrade, inside `RecommendationAgent`. |
| **Primary Component Tag** | `COMP-REC` |
| **Secondary Component Tag** | `COMP-TA` (reuses the sector ROC computation utility already specified by FEAT-004) |
| **Primary Situation Tag** | `SIT-SR` |
| **Secondary Situation Tags** | `SIT-BMR` (the benchmark half of the relative-strength difference is a broad-market input) |
| **Target Implementation Class** | `RecommendationAgent` (primary); sector RS utility (secondary — per ADR-003, the canonical difference-formula computation resides in the live `SectorRelativeStrengthService`, not a new agent) |
| **Required Input Data** | Sector index OHLCV per stock (sector mapping already required by FEAT-004 §2); benchmark OHLCV (already required by FEAT-004 §2) |
| **Safe Fallback Behavior** | If sector data is unavailable, stale, or unmapped, set `sector_regime_state = UNKNOWN` and apply zero score delta; existing pipeline output unchanged. |
| **Deterministic Logic Check** | Given the same sector and benchmark OHLCV inputs on the same date, the sector RS value (difference), state, score delta, and downgrade decision are always identical — no LLM inference, no randomness, no ML model. |
| **Explainability Check** | A human can read the logged `sector_regime_state`, `sector_rs_value`, `sector_roc20`, and `benchmark_roc20` fields and verify the classification against two charts (the sector index and Nifty 500) with a calculator. |
| **Idea Type** | `soft-score-factor` (primary) with optional `watch-only-signal` (the borderline downgrade path) |
| **Known Gap Addressed** | FEAT-001 §8 **Gap #2** — *"No sector relative strength model"* |
| **Evidence Level (FEAT-005)** | **Level B** (see §6 of this document) |

---

## 1. Feature Title

**FEAT-007 — Sector Relative Strength Overlay**

---

## 2. One-Line Summary

Compute each stock's sector index relative strength versus the benchmark (Nifty 500), and apply it as a soft composite-score modifier inside `RecommendationAgent`, with an optional borderline BUY→WATCH downgrade for stocks in weak sectors — directly addressing FEAT-001 §8 Gap #2 (*"No sector relative strength model"*).

---

## 3. Why This Feature Is Needed

The engine currently scores every stock as if its sector does not exist. A stock in a structurally declining sector and an identical-looking stock in a leading sector receive identical composite scores. FEAT-001 §8 acknowledges this explicitly as Gap #2, and the engine's known-gap list flags it as a recognized deficiency — not a new discovery.

Sector relative strength is the single most actionable missing dimension because:

1. **It opens an untouched situation axis.** FEAT-002 defines `SIT-SR` (Sector Regime) as a first-class situation, but no feature currently uses it as a primary tag. FEAT-004 (Market Regime Overlay) addresses `SIT-BMR` only; its sector computation is explanation-only metadata (FEAT-004 §6 v1). FEAT-007 promotes that metadata into an actionable signal.

2. **It reuses existing infrastructure.** FEAT-004 already specifies the sector mapping table (FEAT-004 §2) and sector index OHLCV plumbing. Per ADR-003, the canonical sector RS computation uses the difference formula (`sector_roc20 − benchmark_roc20`), which is already implemented in the live `SectorRelativeStrengthService` (SR-003). FEAT-007 consumes this computation and attaches a score effect to a value the engine is already (or will already be) computing.

3. **It is the lowest-risk high-impact option.** It is a soft modifier on the composite score (not a hard filter), so it cannot silently drop stocks the way a multi-timeframe hard filter would. It avoids the Strict Buy Gate entirely (unlike a risk-reward overlay). And it does not duplicate FEAT-004 the way a second broad-market signal (market breadth, volatility regime) would.

---

## 4. Target Component

**`COMP-REC` — `RecommendationAgent`** (primary).

**Justification per FEAT-003 Rule 3 (Gating Order) and Rule 1 (Delta-Based Tagging):**

- FEAT-007 modifies the **final composite score** computed by `RecommendationAgent` and optionally downgrades `BUY → WATCH` in the synthesis layer. The code delta lives in `RecommendationAgent`.
- It is **not** `COMP-SCR` because it does not discard stocks before technical scoring.
- It is **not** `COMP-RISK` because it operates on the composite score at synthesis time, not as a post-synthesis failsafe. (Per FEAT-003 §4 trap table: post-synthesis *boolean downgrade of a borderline BUY* that depends on a synthesis-level modifier is still `COMP-REC` behavior; the Strict Buy Gate's independent criteria are untouched.)
- It is **not** `COMP-TA` as primary, because although the difference computation is a technical calculation, the *decision delta* — the score adjustment and the downgrade — is written in `RecommendationAgent`. The sector RS utility (where the difference is computed) is a `COMP-TA` secondary, exactly as FEAT-004 §1 already classifies it.

---

## 5. Target Market Situation

**`SIT-SR` — Sector Regime** (primary).

FEAT-002 §2 defines `SIT-SR`: *"Relative strength or trend changes in a specific industry sector."* The core signal — a stock's sector index outperforming or underperforming Nifty 500 — is the textbook `SIT-SR` trigger.

**`SIT-BMR` (Broad Market Regime)** is a valid secondary because the relative-strength difference is *relative to* the benchmark, so the benchmark half is a broad-market input. This dual tag is explicitly permitted by FEAT-003 Rule 2 (≤ 2 secondary situations) and matches FEAT-002 §5's note that sector logic may have a broad-market dimension.

**Misclassification guard (per FEAT-003 Instruction 6):** This is `SIT-SR`, **not** `SIT-BMR`, because the rule measures an *industry sub-sector index* (e.g., Nifty IT, Nifty Bank) against the benchmark — it is not a market-wide regime detector. Tagging it `SIT-BMR` would repeat the exact error FEAT-003 §4 warns against.

---

## 6. Evidence Level

**Level B — Professionally Established** (FEAT-005 §4).

### 6.1 Evidence dossier (per FEAT-005 §7)

| FEAT-005 Dimension | Score | Artefact basis |
| :--- | :--- | :--- |
| D1 — Academic literature support | 18 | Two independent peer-reviewed strands: (a) sector momentum / industry relative strength as a return factor (Moskowitz & Grinblatt, 1999, "Do Industries Explain Momentum?"; Asness et al. on relative-value and momentum factors); (b) the well-documented lead-lag and sector-rotation literature. |
| D2 — Practitioner / professional adoption | 25 | Sector rotation and relative-strength (RS) analysis is standard practitioner doctrine: Murphy *Intermarket Analysis*; Pring *Investment Psychology Explained*; implemented as RS lines in every major charting platform (TradingView, MetaStock, StockCharts); core to NSE sector-index methodology. |
| D3 — Empirical / statistical evidence | 17 | ≥ 1 out-of-sample empirical demonstration of sector-momentum alpha in the academic literature (Moskowitz & Grinblatt out-of-sample windows). |
| D4 — Independent replication | 6 | ≥ 1 independent confirmation (industry-momentum factor replicated in subsequent factor studies). |
| D5 — Evidence stability | 5 | Effect documented across bull and bear regimes in the literature; the *specific* NIFTY 500 parameterization (ROC20, difference-formula threshold at 0.0 pp) is calibrated to the live SR-003 reference implementation validated against 10,827 real NSE observations (ADR-003 evidence report). |
| **Total** | **71** | → **Level B** (FEAT-005 §5.3 threshold: 65–84) |

### 6.2 Acceptance criteria check (FEAT-005 §4 Level B)

- (i) ≥ 3 independent practitioner/textbook sources — **met** (Murphy, Pring, plus platform-standard RS methodology).
- (ii) Documented historical performance track record — **met** (factor literature).
- (iii) Implemented in ≥ 2 independent trading systems — **met** (standard across charting/analysis platforms).
- (iv) No major contradictory practitioner consensus — **met** (sector rotation is mainstream consensus).

### 6.3 Promotion path

FEAT-007 is **Level B at submission**. Under FEAT-006 §7.2, this makes it **activation-eligible (≥ B)** — unlike FEAT-004, which entered at Level C and is activation-blocked until promotion. A local backtest (Stage 10) is mandatory before shadow; the shadow-period correlations (Stage 14) can serve as a second independent confirmation toward Level A (FEAT-005 §9.2 B→A requires peer-reviewed replication, which is already partially present).

---

## 7. Lifecycle Placement

Per **FEAT-006** (all 17 stages), FEAT-007 is currently at **Stage 1 (Idea Submitted)**, advancing through Stages 2–5 via this document. The projected traversal:

| FEAT-006 Stage | FEAT-007 Status |
| :--- | :--- |
| 1. Idea Submitted | ✅ This document (Stage 1 artefact) |
| 2. Component + Situation Classification | ✅ `COMP-REC` primary / `SIT-SR` primary (this document §4, §5; validated against FEAT-003 Rules 1–4) |
| 3. Eight-Axis Evaluation | ✅ Documented in §15 (Validation Plan) and throughout |
| 4. Evidence Classification | ✅ Level B (this document §6) |
| 5. Architecture Review | **This document seeks approval** — see §13 Brownfield Safety |
| 6. Implementation Approval | ⏳ Awaiting System Owner sign-off |
| 7–9. Implementation / Unit / Integration | ⏳ Awaiting Stage 6 |
| 10. Backtesting | ⏳ Mandatory before shadow (Level B ≥ Stage 10 minimum of D) |
| 11. Walk-Forward Validation | ⏳ Mandatory (Level B ≥ Stage 11 minimum of C) |
| 12. Paper Trading | ⏳ Mandatory (Level B ≥ Stage 12 minimum of C) |
| 13. Production Candidate | Awaiting System Owner |
| 14. Shadow Mode | ⏳ Minimum 30 sessions (FEAT-004 §12 precedent) |
| 15. Production Activation | ✅ **Eligible at Level B** (FEAT-006 §7.2: activation requires ≥ B). *This is the key advantage over FEAT-004.* |
| 16. Production Monitoring | ⏳ Per §15 metric set |
| 17. Rollback | One-line config: `feat007.enabled = false` |

**Lifecycle ceiling note (FEAT-006 §7.2):** Because FEAT-007 enters at Level B, it is *not* activation-capped the way FEAT-004 is. It may still be held in shadow for observational reasons (Stage 14), but the evidence gate does not block activation.

---

## 8. Current Gap in the Engine

FEAT-001 §8 **Gap #2**: *"No sector relative strength model — Cannot rank stocks within sector or prefer strong sectors."*

**Concrete symptom:** Two stocks with identical technical, fundamental, backtest, and news scores — one in a leading sector (e.g., Nifty IT during an IT rally), one in a lagging sector (e.g., Nifty Metal during a metals drawdown) — receive identical composite scores and identical BUY/WATCH/REJECT labels. The engine has no mechanism to prefer the stock whose sector is supporting its move, or to flag suspicion on a stock whose sector is diverging from its price action.

**Why now:** FEAT-004 already introduces the data plumbing (sector mapping + sector index OHLCV). The live `SectorRelativeStrengthService` (SR-003) already computes the canonical difference-formula sector RS value (`sector_rs_20 = sector_roc20 − benchmark_roc20`). In its current form, SR-003 applies a binary post-Gate challenger downgrade. FEAT-007 is the natural next step: promote the sector RS computation from a *post-Gate binary downgrade* to a *pre-Gate soft score modifier*, with a conservative delta and cap.

---

## 9. Proposed Deterministic Logic

### 9.1 Inputs

- `sector_roc20: float | None` — 20-day rate of change of the stock's sector index (percentage).
- `benchmark_roc20: float | None` — 20-day rate of change of Nifty 500 (or Nifty 50 fallback) (percentage).
- `sector_rs_value: float | None` — `sector_roc20 − benchmark_roc20` (percentage points). The difference formula is well-defined at all benchmark values — no safe-divide or special-case handling is required.
- `composite_score: float` — the pre-FEAT-007 weighted composite from `RecommendationAgent`.
- `current_label: str` — the pre-FEAT-007 label (`BUY / WATCH / REJECT`).

FEAT-007 **does not fetch any data itself**. It consumes the values produced by the canonical difference-formula sector RS computation (the live `SectorRelativeStrengthService` per ADR-003, or a revised shared helper that uses the difference formula). If the sector RS computation is unavailable or abstained, FEAT-007 inherits the `UNKNOWN` state and applies zero delta.

### 9.2 Sector regime classification

Three discrete states, evaluated top-to-bottom, first match wins:

| Condition | `sector_regime_state` |
| :--- | :--- |
| `sector_rs_value` is `None` (sector unmapped, unavailable, or computation failed) | `UNKNOWN` |
| `sector_rs_value < 0` (sector underperforming benchmark) | `WEAK` |
| `sector_rs_value ≥ 0` (sector matching or outperforming benchmark) | `STRENGTH` |

**These thresholds align with the live SR-003 reference implementation** (`sector_rs_20 < 0` → WEAK), which ADR-003 retains as canonical. The binary WEAK/STRENGTH classification is the proven, audited starting point. A future evidence-backed revision may introduce a three-state classification with a NEUTRAL band on the difference scale (e.g., ±X percentage points); this is deferred per ADR-003 §0, which scopes mechanic upgrades as a "separate, evidence-backed step."

### 9.3 Score modifier (applied to composite score, post-synthesis, pre-Strict Buy Gate)

| `sector_regime_state` | Composite Score Delta | BUY→WATCH Downgrade Threshold | Notes |
| :--- | :--- | :--- | :--- |
| `STRENGTH` | +1.5 | None | Mild bonus; **cannot** push WATCH → BUY (cap enforced, §9.4) |
| `WEAK` | -3.0 | Apply if adjusted score < 74 | Soft penalty; borderline BUYs in weak sectors slip to WATCH |
| `UNKNOWN` | 0.0 | None | Preserve existing logic exactly (abstention propagates) |

**Insertion point:** The hook fires **after** FEAT-004's regime overlay (if active) and **before** the Strict Buy Gate. Order of overlays: `composite → FEAT-004 adjustment → FEAT-007 adjustment → Strict Buy Gate`. FEAT-007 reads the post-FEAT-004 score as its `composite_score` input.

### 9.4 Deterministic constraints (no-discretion guards)

1. **STRENGTH cap:** If `sector_regime_state == STRENGTH` AND pre-adjustment `composite_score < 72` (BUY threshold): `adjusted_score = min(pre + 1.5, 71.99)`. A strong sector cannot manufacture a BUY from a WATCH score. Mirrors FEAT-004 §5 FAVORABLE cap exactly.
2. **REJECT immutability:** If `current_label == REJECT`, no adjustment is applied and the label stays `REJECT`. A sector bonus cannot resurrect a rejected stock.
3. **Gate input isolation:** FEAT-007 adjusts the composite score only. The `raw_technical_score` passed to the Strict Buy Gate is **never modified** (same invariant as FEAT-004 §5).
4. **Monotonicity:** STRENGTH can only raise a score; WEAK can only lower it; UNKNOWN is a no-op. No state does both.
5. **Conservatism:** On any ambiguity (e.g., `sector_rs_value` exactly on a threshold boundary), the more conservative state wins: a difference of exactly 0.0 is `STRENGTH` (not WEAK), because `sector_rs_value ≥ 0` includes the boundary. This matches FEAT-004 §4's "when in doubt, be conservative" — a sector exactly matching the benchmark is not underperforming, so it does not receive a penalty.

### 9.5 Worked numeric examples

| Pre-score | Pre-label | Sector RS value (pp) | State | Delta | Adj-score | Adj-label | Why |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 80.0 | BUY | +5.0 | STRENGTH | +1.5 | 81.5 | BUY | Strong sector, solid BUY — bonus applied |
| 70.0 | WATCH | +5.0 | STRENGTH | capped | 71.5 | WATCH | Cap prevents WATCH→BUY (71.5 < 72) |
| 55.0 | REJECT | +5.0 | STRENGTH | 0.0 | 55.0 | REJECT | REJECT immutability (constraint 2) |
| 75.0 | BUY | −3.0 | WEAK | −3.0 | 72.0 | BUY | 72.0 ≥ 74 threshold → no downgrade |
| 76.0 | BUY | −3.0 | WEAK | −3.0 | 73.0 | **WATCH** | 73.0 < 74 threshold → downgrade |
| 68.0 | WATCH | −3.0 | WEAK | −3.0 | 65.0 | WATCH | WATCH stays WATCH (no further downgrade) |
| 80.0 | BUY | `None` | UNKNOWN | 0.0 | 80.0 | BUY | Abstention — no effect |
| 80.0 | BUY | 0.0 | STRENGTH | +1.5 | 81.5 | BUY | Boundary: 0.0 ≥ 0 → STRENGTH, not WEAK |

---

## 10. Required Inputs

| Input | Source | Already required by | New data? |
| :--- | :--- | :--- | :--- |
| Sector index OHLCV (per sector in universe) | FYERS API primary; yfinance fallback | FEAT-004 §2 | **No** |
| Sector mapping table (`symbol → sector_index_symbol`) | Static config file | FEAT-004 §2 | **No** |
| Benchmark index OHLCV (Nifty 500 / Nifty 50) | FYERS API primary; yfinance fallback | FEAT-004 §2 | **No** |
| `composite_score`, `current_label` | In-flight in `RecommendationAgent` | Existing pipeline | **No** |

**FEAT-007 introduces zero new external data dependencies.** Every input is either already in FEAT-001 §5 or already mandated by FEAT-004 §2. The sector RS computation itself (`sector_rs_value = sector_roc20 − benchmark_roc20`) is already implemented in the live `SectorRelativeStrengthService` (SR-003), which ADR-003 retains as the reference implementation. This is the core reason FEAT-007 is low implementation risk: the data plumbing and the formula computation already exist.

---

## 11. Expected Outputs

### 11.1 Score and label outputs

- `feat007_adjusted_score: float` — the post-FEAT-007 composite score.
- `feat007_adjusted_label: str` — the post-FEAT-007 label.

### 11.2 Log payload (added to the per-stock recommendation dict)

```
feat007_enabled                  = True | False
feat007_stage                    = SHADOW | ACTIVE | ABSTAINED
sector_regime_state              = STRENGTH | WEAK | UNKNOWN
sector_index_symbol              = string | null
sector_roc20                     = float | null
benchmark_roc20                  = float | null
sector_rs_value                  = float | null    # difference (percentage points)
feat007_pre_adjustment_score     = float
feat007_score_adjustment         = float           # +1.5, 0.0, -3.0
feat007_post_adjustment_score    = float
feat007_watch_downgrade_applied  = True | False
feat007_abstained_reason         = string | null
feat007_explanation              = string
```

This schema mirrors FEAT-004 §8 in shape, so monitoring tooling that consumes FEAT-004 logs consumes FEAT-007 logs without modification. The `sector_rs_value` field replaces the v1.0 `sector_relative_strength_ratio` field, reflecting the difference formula's output (percentage points, not a unitless multiplier).

### 11.3 Human-readable explanation string

> `"Sector: IT — STRENGTH vs Nifty 500 (RS +1.0 pp, sector ROC20 +4.8% vs benchmark +3.8%). Score adjusted by +1.5 (79.0 → 80.5)."`
> `"Sector: METAL — WEAK vs Nifty 500 (RS −3.0 pp, sector ROC20 +1.0% vs benchmark +4.0%). Score adjusted by −3.0 (76.0 → 73.0). BUY downgraded to WATCH."`
> `"Sector: UNKNOWN (no sector mapping for symbol). No adjustment applied."`

---

## 12. Safe Fallback Behavior

| Failure Scenario | Behavior | Log Entry |
| :--- | :--- | :--- |
| Sector RS computation unavailable or abstained (no sector data computed upstream) | `sector_regime_state = UNKNOWN`; zero delta; existing output unchanged | `feat007_abstained_reason = upstream_sector_rs_unavailable` |
| Sector mapping missing for symbol | `UNKNOWN`; zero delta | `feat007_abstained_reason = no_sector_mapping` |
| Sector index OHLCV unavailable or stale | `UNKNOWN`; zero delta | `feat007_abstained_reason = sector_index_unavailable` |
| Sector series < 50 candles | `UNKNOWN`; zero delta | `feat007_abstained_reason = insufficient_sector_history` |
| `benchmark_roc20` is `None` or sector ROC computation fails | `UNKNOWN`; zero delta | `feat007_abstained_reason = sector_rs_computation_failed` |
| Any exception inside FEAT-007 logic | Catch, log, return `UNKNOWN`; do not propagate | `feat007_abstained_reason = exception:{error_type}` |

**No exception from FEAT-007 may propagate into the recommendation path.** The entire FEAT-007 block is wrapped in a try/except that catches all exceptions and defaults to `UNKNOWN` (zero delta). This is the FEAT-004 §7 double-boundary pattern, reused verbatim.

**Note on the difference formula's robustness:** Unlike the ratio formula (which required a safe-divide fallback when `benchmark_roc20 == 0`), the difference formula is well-defined at all benchmark values. When `benchmark_roc20 == 0.0`, `sector_rs_value = sector_roc20 − 0.0 = sector_roc20` — a valid, meaningful result. No special-case handling is required. This is a direct advantage of ADR-003's formula decision (ADR-003 §4.1: "Well-defined at all benchmark values (no division-by-zero edge)").

---

## 13. Brownfield Safety Checks

| Constraint (FEAT-001 §2, FEAT-003 Instruction 8, FEAT-006 §13) | Status |
| :--- | :--- |
| No existing hard filter removed or weakened | ✅ Confirmed |
| Strict Buy Gate criteria unchanged | ✅ Confirmed (composite-only adjustment; `raw_technical_score` untouched) |
| No new autonomous agents created | ✅ Confirmed (sector RS utility is already live as `SectorRelativeStrengthService`, not a new agent) |
| BUY/WATCH/REJECT thresholds unchanged | ✅ Confirmed (72/55/55 preserved; FEAT-007 adjusts scores, not thresholds) |
| Deterministic: same inputs → same outputs | ✅ Confirmed (no LLM, no ML, no randomness — §9.4) |
| Missing data defaults to safe neutral behavior | ✅ Confirmed (§12 — all failures → `UNKNOWN` → zero delta) |
| No exceptions propagate to recommendation path | ✅ Confirmed (try/except boundary) |
| Rollback requires only config flag change | ✅ Confirmed (`feat007.enabled = false`) |
| Bounded delta to one named component | ✅ Confirmed (`RecommendationAgent` only) |
| No new external data dependencies | ✅ Confirmed (§10 — all inputs already required by FEAT-004 or already live in SR-003) |
| No new `COMP-*` or `SIT-*` tags | ✅ Confirmed (`COMP-REC`/`COMP-TA`, `SIT-SR`/`SIT-BMR` all pre-existing) |
| Does not duplicate FEAT-004 | ✅ Confirmed — FEAT-004 is broad-market; FEAT-007 is sector-relative. They compose, not compete. |
| Formula aligns with accepted ADR | ✅ Confirmed — uses the difference formula per ADR-003 (Accepted, Option C-Revised) |

---

## 14. Failure Modes

| Failure Mode | Risk Level | Mitigation |
| :--- | :--- | :--- |
| Sector RS computation unavailable → FEAT-007 silently inert, users confused why "no sector effect" | Medium | Log `feat007_abstained_reason = upstream_sector_rs_unavailable` explicitly; surface in explanation string |
| Sector mapping maps a symbol to the wrong sector index | Medium | Config file peer-reviewed before activation; mapping validated against known NSE sector constituents (FEAT-004 §10 mitigation, inherited) |
| WEAK penalty (−3.0) over-fires, downgrading too many valid BUYs in rotating sectors | Medium | Stage A shadow mode monitors downgrade rate before any score effect (FEAT-006 Stage 14, §15); threshold tunable via config |
| STRENGTH bonus (+1.5) cap miss pushes WATCH → BUY | High | Enforce cap in code: `min(pre + 1.5, 71.99)` if pre < 72 (§9.4 constraint 1) — unit-tested (§15) |
| Sector index data stale on a holiday → misclassification | Low | Staleness check inherited from FEAT-004 §7 / SR-003; defaults to `UNKNOWN` |
| FEAT-004 and FEAT-007 both apply penalties → double-counting regime weakness | Medium | Documented composition order (§9.3): FEAT-007 reads *post-FEAT-004* score; the two overlays are additive by design, not a bug — but Stage 15 monitors combined effect (§15) |
| Exception propagates past FEAT-007 boundary | Low | Double try/except boundary (FEAT-004 §7 pattern); unit-tested exception path |

---

## 15. Validation Plan

### 15.1 Eight-axis evaluation (FEAT-001 §10)

| Axis | Rating | Rationale |
| :--- | :--- | :--- |
| Profitability impact | Medium | Prefers stocks in supporting sectors; evidence (Level B) supports a real effect |
| False-positive risk | **Reduced** | WEAK downgrade filters borderline BUYs in declining sectors |
| False-negative risk | Low | Soft modifier (not a hard filter); STRENGTH is capped so it cannot over-promote |
| Overfitting risk | Medium | The −3.0/+1.5 deltas are single-party parameters — must be tuned via Stage 10 backtest |
| Data availability | High | All inputs already required by FEAT-004 §2 or already live in SR-003 |
| Implementation complexity | Low | Bounded delta to `RecommendationAgent`; reuses existing sector RS computation |
| Testability | High | Pure function of (sector_rs_value, score, label) → (adjusted_score, adjusted_label) |
| Explainability | High | One plain-English sentence with logged RS value and sector name (§11.3) |

### 15.2 Unit test plan (deterministic, fixed inputs — FEAT-006 Stage 8)

| # | Test | Input | Expected |
| :--- | :--- | :--- | :--- |
| 1 | `test_sector_strength_buy` | score=80, BUY, rs_value=+5.0 | adj=81.5, BUY |
| 2 | `test_sector_strength_cap_watch` | score=70, WATCH, rs_value=+5.0 | adj=71.5, WATCH (cap) |
| 3 | `test_sector_strength_reject_immune` | score=55, REJECT, rs_value=+5.0 | adj=55.0, REJECT |
| 4 | `test_sector_weak_no_downgrade` | score=75, BUY, rs_value=−3.0 | adj=72.0, BUY (≥74) |
| 5 | `test_sector_weak_downgrade` | score=76, BUY, rs_value=−3.0 | adj=73.0, WATCH (<74) |
| 6 | `test_sector_weak_watch_stays` | score=68, WATCH, rs_value=−3.0 | adj=65.0, WATCH |
| 7 | `test_sector_unknown_noop` | score=73, BUY, rs_value=None | adj=73.0, BUY |
| 8 | `test_sector_boundary_zero` | rs_value=0.0 | state=STRENGTH (conservative: 0.0 ≥ 0) |
| 9 | `test_sector_boundary_negative` | rs_value=−0.01 | state=WEAK (strictly < 0) |
| 10 | `test_sector_boundary_positive` | rs_value=+0.01 | state=STRENGTH (≥ 0) |
| 11 | `test_benchmark_zero_normal_evaluation` | benchmark_roc20=0, sector_roc20=+2.5 | rs_value=+2.5, STRENGTH (no special case) |
| 12 | `test_shadow_mode_no_effect` | stage=SHADOW, WEAK, score=76 | adj=76.0, BUY (no change) |
| 13 | `test_exception_returns_unknown` | inject exception | UNKNOWN, zero delta, original score preserved |
| 14 | `test_strict_buy_gate_input_unchanged` | any | `raw_technical_score` to Gate equals pre-FEAT-007 TA score |

### 15.3 Backtest plan (FEAT-006 Stage 10)

Reuse FEAT-004 §9's data split verbatim (in-sample A bull / B sideways / C bear / out-of-sample mixed). Isolation method:

1. Baseline: FEAT-007 disabled.
2. Treatment: FEAT-007 ACTIVE (score effect on).

| Metric | Minimum Acceptance | Rollback Trigger |
| :--- | :--- | :--- |
| False-positive reduction (WEAK periods) | ≥ 5% fewer losing BUY trades in weak sectors | — |
| Missed-winner rate (STRENGTH periods) | ≤ 3% increase in missed profitable BUYs | > 8% triggers rollback |
| Win rate (overall BUY) | Neutral or improved | — |
| Profit factor | Neutral or improved | Drops > 10% vs baseline triggers rollback |
| WEAK downgrade count in bear/rising-rate periods | > 0 (proves feature fires) | — |
| STRENGTH cap violations | 0 | Any > 0 triggers bug fix |

### 15.4 Shadow window (FEAT-006 Stage 14)

Minimum 30 trading sessions, log-only, zero score effect. Validate that `sector_regime_state` distributes across STRENGTH/WEAK and correlates with BUY outcome accuracy before Stage 15 activation.

---

## 16. Rollback Plan

**Rollback mechanism:** One-line config change. No code change required (FEAT-006 RI-1).

```yaml
feat007:
  enabled: false      # Master switch. false = FEAT-007 never runs.
```

| Rollback scenario (FEAT-006 §9.1) | Action | Target |
| :--- | :--- | :--- |
| Missed-winner rate ↑ > 8% out-of-sample | Set `feat007.stage = SHADOW` | Stage 14 (Shadow) |
| Profit factor drops > 10% vs baseline | Set `feat007.stage = SHADOW` | Stage 14 |
| STRENGTH cap violation observed (WATCH→BUY) | Set `feat007.enabled = false` + bug fix | Stage 7 (Implementation) |
| Exception propagates past boundary | Set `feat007.enabled = false` | Disabled (investigation) |
| Sector mapping found systematically wrong | Set `feat007.enabled = false` + fix mapping | Stage 7 |

After any rollback, recommendation outputs return to pre-FEAT-007 behavior (the overlay is purely additive to the composite score; disabling it restores the prior score and label exactly).

---

## 17. Final Recommendation

**Proceed to FEAT-006 Stage 6 (Implementation Approval) for FEAT-007, conditional on FEAT-004's sector data plumbing being available.**

Rationale:

1. **Highest value-to-risk ratio among the six candidates.** FEAT-007 is the only option that opens a new situation dimension (`SIT-SR`), addresses a top-acknowledged gap (Gap #2), and does so with Level B evidence — making it activation-eligible where FEAT-004 is not.
2. **Smallest implementation footprint.** It reuses the existing sector mapping, benchmark OHLCV, and the canonical difference-formula sector RS computation (per ADR-003, already implemented in the live `SectorRelativeStrengthService`). The delta is one overlay function in `RecommendationAgent`, mirroring FEAT-004's hook pattern.
3. **Zero new data dependencies.** Every input is either already mandated by FEAT-004 or already live in SR-003. If FEAT-004's data layer exists, FEAT-007 needs no additional fetching, mapping, or storage.
4. **Composes cleanly with FEAT-004.** Where FEAT-004 asks "is the *broad market* supportive?", FEAT-007 asks "is this stock's *sector* supportive?" These are orthogonal questions; applying both gives a two-dimensional regime view without double-counting (broad vs sector are distinct signals).
5. **Conservative by construction.** STRENGTH is capped (cannot over-promote), WEAK is a soft penalty (not a hard filter), REJECT is immutable, UNKNOWN is a no-op. The feature cannot make the engine more aggressive than it is today; it can only make it more selective in weak sectors.
6. **One-line rollback.** `feat007.enabled = false` restores pre-feature behavior immediately, with no code change.
7. **Formula is evidence-backed.** ADR-003's evidence report (10,827 real NSE observations) conclusively validated the difference formula over the ratio formula. The difference formula is well-defined at all benchmark values, linear, intuitive, and already live in production as SR-003.

**Dependency note:** FEAT-007 consumes the sector RS computation. Per ADR-003, the canonical computation uses the difference formula (`sector_roc20 − benchmark_roc20`), already implemented in the live `SectorRelativeStrengthService` (SR-003). FEAT-007's implementation upgrades SR-003's mechanic from a post-Gate binary challenger downgrade to a pre-Gate soft score modifier with deltas and cap, while retaining the same proven formula. The System Owner should decide sequencing at Stage 6.

---

*End of FEAT-007 Specification v1.1*
