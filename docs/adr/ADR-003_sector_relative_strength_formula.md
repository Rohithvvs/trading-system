# ADR-003 — Sector Relative Strength Formula

**Status:** **Accepted** (2026-07-11) — Option C-Revised selected on the basis of the completed evidence report
**Date:** 2026-07-11
**Decides:** The canonical formula and implementation for sector relative strength, reconciling the live SR-003 (`SectorRelativeStrengthService`, difference formula) with the FEAT-007 specification (ratio formula)
**Supersedes:** None
**Superseded by:** None
**Blocks:** IMPLEMENTATION_MASTER_PLAN Phase 3
**Supporting evidence:** [`EVIDENCE_REPORT_SR_formula_comparison.md`](EVIDENCE_REPORT_SR_formula_comparison.md)

---

## 0. Final Architectural Decision (read first)

| Field | Value |
| :--- | :--- |
| **Decision** | **Option C-Revised** — the difference formula (`sector_roc20 − bm_roc20`) is the canonical sector-relative-strength formula for this system. The FEAT-007 specification must be revised to document the difference formula in place of the ratio formula it currently specifies. |
| **Selected option** | C-Revised (retain the difference formula; converge mechanics toward the spec; revise FEAT-007) |
| **Rejected option** | D (adopt the ratio formula `sector_roc20 / bm_roc20`) — rejected on evidence |
| **Status** | Accepted 2026-07-11 |
| **Evidence basis** | Phase-0 Task 0.3 evidence report — 10,827 real NSE observations, 2021-08-10 → 2026-07-03 |
| **Consequence for FEAT-007** | FEAT-007 specification must be revised: replace the ratio formula and STRONG/NEUTRAL/WEAK thresholds with the difference formula and its WEAK/STRENGTH classification. This revision is the responsibility of the FEAT-007 specification owner; ADR-003 does not modify FEAT-007 directly. |
| **Consequence for SR-003** | The live `SectorRelativeStrengthService` is retained as the reference implementation. Its mechanic (binary WEAK/STRENGTH, score cap 71.0, post-Gate placement) is the starting point; the IMPLEMENTATION_MASTER_PLAN Phase 3 may upgrade its mechanics (three-state, score deltas, pre-Gate placement) as a separate, evidence-backed step — but the *formula* is now fixed. |

> This ADR was originally **Proposed** with a recommendation for Option D *conditional on the Phase-0 disagreement-rate measurement being low*. The evidence report resolved the condition: disagreement is high on every fair test (40.3 % spec-threshold binary; 27.2 % quantile-matched; Spearman ρ = 0.188). The conditional is therefore resolved **against** Option D. Sections 1–11 below are preserved as the decision record; the change in recommendation is documented in §7 (updated) and §11 (updated), with the evidence summarised in §11.1.

---

## 1. Context

The codebase contains **two** sector-relative-strength implementations that use **different formulas** for the same conceptual quantity, plus a specification (FEAT-007) that matches the second. The IMPLEMENTATION_MASTER_PLAN flagged this as Decision D3. A formula disagreement is not a tuning difference — a difference metric and a ratio metric classify different stocks as strong/weak, so running both produces inconsistent recommendations. This ADR decides the canonical formula and which implementation survives.

The decision matters because sector-relative-strength is the mechanism for FEAT-001 §8 Gap #2 ("No sector relative strength model") and is the primary `SIT-SR` signal in the OS.

---

## 2. Existing Implementation

### 2.1 SR-003 — `SectorRelativeStrengthService` (LIVE)

File: `backend/app/services/sector_rs_service.py`. Invoked at `orchestrator_agent.py:594–598`; downgrade applied at `orchestrator_agent.py:612–620`.

**Formula — DIFFERENCE of ROC20 percentages** (`sector_rs_service.py:166–168`):
```
roc20_sector  = (close_sector[T] / close_sector[T-20] - 1) * 100
roc20_nifty50 = (close_nifty50[T] / close_nifty50[T-20] - 1) * 100
sector_rs_20  = roc20_sector - roc20_nifty50
```

**Benchmark:** `"NIFTY50-INDEX"`, hardcoded (`:99`). Sector symbol per stock from `config/sector_mappings.json` (~80 entries, 10 sectors).

**Classification** (`sector_filter_status`):
- `UNMAPPED` — no sector mapping.
- `INSUFFICIENT_HISTORY` — <20 sector rows, <21 aligned rows, NaN, or any exception. `downgrade_triggered=False`.
- `WEAK` — `sector_close < sector_ema20` (downtrend) **AND** `sector_rs_20 < 0` (underperforming). `downgrade_triggered=True`.
- `STRENGTH` — everything else.

Two effective outcomes (WEAK vs STRENGTH); no intermediate state.

**Downgrade mechanic:** service sets `downgrade_triggered`; orchestrator enforces: `if recommendation.action == "BUY" and downgrade_triggered: challenger_action = "WATCH"; challenger_score = min(challenger_score, 71.0)`.

**Placement:** **AFTER** the Strict Buy Gate, on the `challenger_recommendation`.

**Safe-fallback:** any missing/insufficient data → `INSUFFICIENT_HISTORY`, `downgrade_triggered=False` (no downgrade). Outer `except` also maps to `INSUFFICIENT_HISTORY`.

**Persistence:** `AnalysisHistory` columns `mapped_sector`, `sector_rs_20`, `sector_close_vs_ema20`, `sector_filter_triggered`, `original_signal`, `challenger_signal`, `reason_codes`.

### 2.2 FEAT-004's `compute_sector_strength` (DEAD, metadata-only)

File: `backend/app/services/feat004_regime_overlay.py:316–389`. Inside the FEAT-004 module. Computes the sector value but by contract "v1 MUST NOT change score" — metadata only. Also never called in production because FEAT-004 itself is never activated (see ADR-002).

**Formula — RATIO of ROC20** (`:381`):
```
relative_strength_ratio = round(sector_roc20 / benchmark_roc20, 4)
```
with safe fallback `ratio = 1.0` if `benchmark_roc20` is None/0 (`:373–379`).

**Benchmark:** `NIFTY500` (passed in from FEAT-004's benchmark resolution), not `NIFTY50`.

**Classification:**
- `STRONG` — ratio > 1.10
- `NEUTRAL` — 0.90 ≤ ratio ≤ 1.10
- `WEAK` — ratio < 0.90
- `UNKNOWN` — any missing input.

Three effective outcomes (plus UNKNOWN); has an explicit intermediate (`NEUTRAL`).

### 2.3 The FEAT-007 specification

Matches `compute_sector_strength`'s **ratio** formula and STRONG/NEUTRAL/WEAK classification. Adds: score deltas (`STRONG +1.5`, `WEAK −3.0`, `NEUTRAL/UNKNOWN 0.0`), a STRONG cap (cannot push WATCH→BUY), a WEAK downgrade threshold (adjusted score < 74), REJECT immutability, and **pre-Gate** placement on the composite (composite → FEAT-004 → FEAT-007 → Gate).

---

## 3. Proposed Implementation

Five candidate implementations in §11. The core question: which formula — **difference** (`roc_sector − roc_bm`) or **ratio** (`roc_sector / roc_bm`) — is canonical? And does the live SR-003 (post-Gate, binary WEAK/STRENGTH, score cap 71.0) or the spec (pre-Gate, three-state, score deltas, cap 74.0) define the downstream mechanic?

---

## 4. Technical Differences (SR-003 vs FEAT-007/spec)

| Dimension | SR-003 (live) | FEAT-007 (spec) / `compute_sector_strength` |
| :--- | :--- | :--- |
| **Formula** | Difference: `roc_sector − roc_nifty50` | Ratio: `roc_sector / roc_bm` |
| **Sign when benchmark ≈ 0** | Well-defined (subtraction) | Undefined → safe-fallback to 1.0 (NEUTRAL) |
| **Scale** | Percentage points (absolute) | Unitless multiplier (relative) |
| **Sensitivity** | Linear in both ROCs | Non-linear near benchmark ROC ≈ 0; compresses at large magnitudes |
| **Benchmark** | NIFTY50 (hardcoded) | NIFTY500 preferred, NIFTY50 fallback (configurable) |
| **States** | 2: WEAK / STRENGTH | 3: STRONG / NEUTRAL / WEAK (+ UNKNOWN) |
| **Trend condition** | WEAK requires `close < EMA20` (downtrend) **plus** underperformance | WEAK is formula-only (no separate trend gate) |
| **Effect** | Binary: BUY→WATCH, score cap 71.0 | Continuous: STRONG +1.5 (capped), WEAK −3.0, downgrade threshold 74.0 |
| **Placement** | Post-Gate, on challenger | Pre-Gate, on base composite |
| **REJECT handling** | Not applicable (only acts on BUY) | Explicit immutability (REJECT unaffected) |

### 4.1 Why difference ≠ ratio (the core technical point)

Consider a sector up 2 % and benchmark up 1 % over 20 days:
- **Difference:** `2 − 1 = +1.0` percentage point.
- **Ratio:** `2 / 1 = 2.0` → strongly STRONG.

Now consider sector up 0.2 % and benchmark up 0.1 %:
- **Difference:** `+0.1` (near-neutral).
- **Ratio:** `2.0` → still strongly STRONG.

The ratio over-amplifies tiny absolute movements when the benchmark ROC is small. Conversely, when both are large (sector +20 %, benchmark +18 %):
- **Difference:** `+2.0`.
- **Ratio:** `1.11` → barely STRONG.

The ratio compresses large movements and amplifies small ones. The two metrics will disagree on classification for a non-trivial fraction of stocks — the Phase-0 task 0.3 disagreement-rate table should quantify this before deciding. **This ADR's recommendation is conditional on that measurement.**

---

## 5. Advantages

**Of the difference formula (SR-003):**
- Well-defined at all benchmark values (no division-by-zero edge).
- Linear, intuitive ("sector beat benchmark by X points").
- Stable near benchmark ROC ≈ 0.
- Already live, audited, persisted.

**Of the ratio formula (FEAT-007/spec):**
- Scale-free (unitless), so comparable across regimes and time periods.
- Standard in practitioner RS literature (RS ratio/line).
- Three-state classification (NEUTRAL band) is more nuanced than binary.
- Spec-aligned (full documentation, score-delta mechanic, pre-Gate placement).
- STRONG bonus rewards sector leadership, not just penalises weakness.

---

## 6. Disadvantages

**Of the difference formula:**
- Scale-dependent (percentage points) — a "+2 point" edge means different things in calm vs. volatile markets.
- Binary outcome loses the neutral band.
- Post-Gate challenger placement means the Strict Buy Gate never sees the sector effect.
- Hardcoded NIFTY50 benchmark.

**Of the ratio formula:**
- Unstable near benchmark ROC ≈ 0 (mitigated by safe-fallback to 1.0, but the fallback masks signal).
- Non-linear amplification of small absolute movements.
- Never been live (metadata-only inside dead FEAT-004).
- Pre-Gate placement changes which score the Gate sees (a structural change).

---

## 7. Recommendation

**Option D — Adopt the ratio formula; migrate SR-003 to it; converge on the spec's pre-Gate, three-state mechanic** (see §11). **Conditional on the Phase-0 disagreement-rate measurement (task 0.3).**

Conditional logic:
- If the disagreement rate between difference and ratio is **low** (< ~10 % of stocks classified differently), the formulas are practically equivalent → adopt the spec's ratio for consistency with the OS documentation and migrate SR-003.
- If the disagreement rate is **high** (≥ ~20 %), the choice is substantive → retain the difference formula (SR-003) as canonical and **revise the FEAT-007 specification** to match, rather than migrating live behaviour to an unvalidated formula.

Either way, **converge on one formula and one mechanic**. The status quo (two formulas, two mechanics, two placements) is the worst option.

Rationale: the OS specifications are the long-term source of truth, and the ratio is the practitioner-standard RS metric. But a live, audited feature should not be silently swapped for a spec formula without measuring the behavioural difference — hence the conditional.

> **Update 2026-07-11 (decision resolved):** the condition above has been resolved — **against** Option D. The Phase-0 Task 0.3 evidence report ([`EVIDENCE_REPORT_SR_formula_comparison.md`](EVIDENCE_REPORT_SR_formula_comparison.md)) measured the disagreement rate across 10,827 real NSE observations and found it far exceeds the "adopt the ratio" threshold on every fair test: 40.3 % spec-threshold binary disagreement, 27.2 % quantile-matched disagreement, Spearman ρ = 0.188. Per the conditional logic stated in this section, high disagreement (≥ ~20 %) means the choice is substantive, so the live, audited difference formula is retained as canonical and the FEAT-007 specification is to be revised — i.e. **Option C-Revised** (see §0 and §11.1). The recommendation above is preserved as the historical record of the original proposal.

---

## 8. Migration Strategy

1. **Measure first** (Phase 0 task 0.3): run both formulas across a representative sample; produce the disagreement-rate table.
2. **Decide** (this ADR): ratio-if-low-disagreement (Option D), difference-if-high (Option C-revised).
3. **If Option D (ratio):**
   - Refactor `compute_sector_strength` into a standalone `feat007` service (or migrate `sector_rs_service` to the ratio).
   - Move placement from post-Gate (challenger) to pre-Gate (composite) per the spec.
   - Replace the binary WEAK/STRENGTH + 71.0 cap with STRONG/NEUTRAL/WEAK + score deltas + 74.0 threshold + STRONG cap + REJECT immutability.
   - Make the benchmark configurable (NIFTY500 primary, NIFTY50 fallback).
   - Shadow ≥30 sessions; FEAT-007 is Level B → activation-eligible after shadow.
4. **If Option C-revised (difference):** update the FEAT-007 specification to document the difference formula as canonical; keep SR-003's mechanic or upgrade it to three-state while retaining the difference formula.
5. **Either way:** remove the duplicate (`compute_sector_strength` or SR-003) so only one sector-RS path survives.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| Ratio formula over-amplifies small-movement noise → more WEAK/STRONG flips than warranted | Medium | Medium | Phase-0 disagreement measurement; band tuning (1.10/0.90) |
| Moving from post-Gate to pre-Gate changes which score the Strict Buy Gate sees | High (under Options C/D) | Medium | Integration test: `raw_technical_score` to Gate unchanged; full shadow |
| Benchmark change NIFTY50 → NIFTY500 shifts classifications | Medium | Medium | Verify NIFTY500 instrument support; shadow both benchmarks |
| Removing SR-003 loses its `close < EMA20` trend condition (the ratio formula has no separate trend gate) | Medium | Medium | Add an optional trend gate to the ratio path if backtest demands |
| Ratio unstable near benchmark ROC ≈ 0 | Medium | Low | Safe-fallback to 1.0 (NEUTRAL) already specified; audit how often it fires |

---

## 10. Rollback Strategy

- **SR-003 (today's live path):** the orchestrator call at `:594` is the seam. Gate it behind `feat007.enabled` or a `sr003.enabled` flag; disabling restores today's behaviour exactly.
- **FEAT-007 (new path):** `feat007.enabled = false`.
- **Formula migration:** if the ratio is adopted and later found wanting, the difference formula is recoverable from git history and the persisted `sector_rs_20` column; restoring SR-003 is a revert + flag flip.

---

## 11. Final Decision Options

### Option A — Keep SR-003 only; revise the FEAT-007 spec to match (difference formula)

Adopt the live difference formula as canonical; update the FEAT-007 specification to document the difference; delete `compute_sector_strength`.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Neutral (keeps a working signal) |
| Brownfield safety | Highest — nothing live changes |
| Determinism | High |
| Explainability | Medium — binary outcome, post-Gate |
| Implementation complexity | Trivial (doc update + delete dead helper) |
| Regression risk | None |
| Technical debt | Medium — spec and code diverge unless spec is revised; post-Gate placement retained |
| Long-term maintainability | Medium |

### Option B — Replace SR-003 with the spec's ratio formula and mechanic

Migrate live code to ratio + STRONG/NEUTRAL/WEAK + score deltas + pre-Gate placement. Remove SR-003.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Potentially positive (three-state, STRONG bonus) — but unvalidated |
| Brownfield safety | **Low** — replaces a live feature |
| Determinism | High |
| Explainability | High (spec-aligned) |
| Implementation complexity | Medium — migrate + re-place + re-validate |
| Regression risk | **High** — live behaviour changes; never shadowed |
| Technical debt | Low (after) |
| Long-term maintainability | High (after) |

### Option C — Keep the difference formula but upgrade SR-003 to the spec's three-state mechanic

Retain `roc_sector − roc_bm`; add a NEUTRAL band; add score deltas; move pre-Gate. Hybrid: live formula, spec's mechanic.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Positive — gains nuance without formula risk |
| Brownfield safety | Medium — mechanic changes (placement, states) |
| Determinism | High |
| Explainability | High |
| Implementation complexity | Medium |
| Regression risk | Medium — placement move affects Gate input |
| Technical debt | Low |
| Long-term maintainability | Medium — spec still needs revision to match the formula |

### Option D — Adopt the ratio formula; migrate SR-003; converge on spec (RECOMMENDED, conditional)

Move to ratio + three-state + score deltas + pre-Gate. Remove SR-003 and `compute_sector_strength`. **Conditional on Phase-0 disagreement-rate measurement being low.**

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Potentially highest — spec-aligned, scale-free, standard metric |
| Brownfield safety | Medium — live feature replaced, but staged via shadow |
| Determinism | High |
| Explainability | High — single canonical formula, spec-matched |
| Implementation complexity | Medium |
| Regression risk | Medium — mitigated by the disagreement-rate gate and shadow |
| Technical debt | Lowest — one formula, one path, spec and code aligned |
| Long-term maintainability | Highest |

### Option E — Keep both formulas, segmented by use case

E.g., difference for the downgrade decision (SR-003 post-Gate), ratio for an explanation-only display (compute_sector_strength). Both survive, formally separated.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Neutral |
| Brownfield safety | High |
| Determinism | High |
| Explainability | **Low** — two "sector RS" numbers in the audit trail confuse reviewers |
| Implementation complexity | Low |
| Regression risk | Low |
| Technical debt | High — two formulas for one concept |
| Long-term maintainability | Low |

**Recommended: Option D, conditional on the Phase-0 disagreement-rate measurement.** It is the only option that fully aligns code with the OS specification (the long-term source of truth) and collapses two formulas into one. The conditionality is honest: if the difference and ratio formulas disagree on a large fraction of stocks, the live, audited formula (Option C) should be retained and the spec revised instead. Option E is explicitly discouraged (two formulas for one concept is the core problem this ADR exists to solve).

**Gate to resolve before deciding:** Phase-0 task 0.3 (disagreement-rate table). Do not finalise this ADR without that data.

> **Update 2026-07-11 (gate resolved):** the Phase-0 Task 0.3 gate required above has been satisfied. The disagreement-rate table is in [`EVIDENCE_REPORT_SR_formula_comparison.md`](EVIDENCE_REPORT_SR_formula_comparison.md). The measured disagreement — 40.3 % binary, 27.2 % quantile-matched, Spearman ρ = 0.188 — exceeds the >20 % "keep the difference formula and revise FEAT-007" threshold. The conditional recommendation for Option D is therefore **withdrawn on evidence**, and **Option C-Revised** is accepted as the architectural decision (see §0). The option table above is preserved as the historical decision record; the evidence summary and the ratio-rejection rationale are in §11.1 below.

### 11.1 Evidence Summary and Resolution of the Condition

**Supporting artifact:** [`EVIDENCE_REPORT_SR_formula_comparison.md`](EVIDENCE_REPORT_SR_formula_comparison.md) — Phase-0 Task 0.3. Deterministic and reproducible from the saved per-observation CSV (`scratch/sr_formula_observations.csv`, 10,827 rows).

**Data scope:** 10,827 real NSE observations — 9 sector indices (NIFTY 50, Bank, IT, Auto, FMCG, Metal, Pharma, Energy, Realty) vs the NIFTY 500 benchmark — over 5 years (2021-08-10 → 2026-07-03), spanning bull, sideways, and correction regimes.

**Headline results:**

| Test | Result | ADR-003 §11 decision rule | Verdict |
| :--- | :--- | :--- | :--- |
| Binary WEAK/STRENGTH disagreement (spec thresholds) | **40.3 %** | >20 % → keep difference, revise FEAT-007 | Exceeds |
| Quantile-matched WEAK disagreement (threshold-free) | **27.2 %** | >20 % → keep difference, revise FEAT-007 | Exceeds |
| Spearman rank correlation (overall) | **0.188** | closer to 1 = agreement | Near-independent |

**Why the ratio formula (`sector_roc20 / bm_roc20`) was rejected:**

1. **Operational disagreement is severe.** The two formulas classify 4,364 of 10,827 observations (40.3 %) differently using their own specification thresholds. A difference metric and a ratio metric flag *different* stocks as weak, so running both produces inconsistent BUY→WATCH downgrades — this is not a tuning difference.
2. **The disagreement is not a threshold artefact.** With thresholds equalised (each formula cut at its own 25th percentile), disagreement remains 27.2 % and the Jaccard similarity of the WEAK sets is 0.296 — the bottom-quartile sets overlap by under a third. The formulas *order* observations almost independently.
3. **The formulas are near-independent signals, not reparameterisations of one signal.** A Spearman ρ of 0.188 is close to unrelated for two metrics purporting to measure the same concept ("how strong is this sector vs the benchmark").
4. **The ratio is numerically unstable where markets spend most of their time.** When the benchmark 20-day return is near zero (|bm_roc20| < 0.5 %; 9 % of observations), the ratio ranges to ±4,453 with a standard deviation of 173.5, vs the difference's tight [−20.5, +12.4] pp. The spec's `bm_roc20 == 0` safe-fallback fires only on *exactly* zero (essentially never in continuous price data), so it does not protect against the near-zero-denominator pathology that causes the amplification.
5. **The ratio sign-flips in exactly the regimes where sector-RS matters most.** In down and sharp-down markets (benchmark ROC < −1 %), binary disagreement reaches 93–96 %: negative benchmark returns cancel against negative sector returns, so the ratio classifies a harder-falling sector as STRONG. The ratio is most reliable in strong up-trends (4–9 % disagreement) — where defensive sector-RS downgrades matter least — and most broken in flat and bear markets, where they matter most.

**Resolution of the §7 / §11 condition.** The predefined decision rule set in this ADR was: disagreement <10 % → adopt the ratio (Option D); 10–20 % → manual review; >20 % → keep the difference formula and revise FEAT-007 (Option C-Revised). The measured disagreement (40.3 % binary, 27.2 % quantile) sits well above the >20 % threshold. **The condition is resolved against Option D and for Option C-Revised.**

**Consequence.** The difference formula (`sector_roc20 − bm_roc20`) is the canonical sector-relative-strength formula for this system. The FEAT-007 specification is to be revised to document the difference formula in place of the ratio formula; that revision is the responsibility of the FEAT-007 specification owner and is not made by this ADR. The live `SectorRelativeStrengthService` (SR-003) is retained as the reference implementation; any mechanic upgrade (three-state, score deltas, pre-Gate placement) is a separate, evidence-backed step under the IMPLEMENTATION_MASTER_PLAN, not a formula change.

---

*End of ADR-003 — Accepted (Option C-Revised), 2026-07-11.*
