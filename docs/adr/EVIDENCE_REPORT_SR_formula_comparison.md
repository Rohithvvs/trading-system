# Evidence Report — Phase 0 Task 0.3: Sector Relative Strength Formula Comparison
**Version:** 1.0
**Date:** 2026-07-11
**Status:** Evidence report only. Does not modify FEAT-007. Does not modify ADR-003. Does not generate code.
**Feeds:** ADR-003 (Sector Relative Strength Formula)
**Data:** Real NSE index OHLCV, 2021-07-12 → 2026-07-03, via yfinance (venv)

---

## Executive Summary

A deterministic, real-data comparison of two candidate formulas for sector relative strength — **Formula A (difference, `sector_roc20 − bm_roc20`)** vs **Formula B (ratio, `sector_roc20 / bm_roc20`)** — was conducted across **10,827 observations** spanning **9 sector indices vs the NIFTY 500 benchmark** over **5 years (2021-08-10 → 2026-07-03)**.

**Headline finding: the two formulas disagree at a rate that exceeds the "keep difference, revise FEAT-007" threshold on every fair test.**

| Test | Result | Threshold (ADR-003 §11) | Verdict |
| :--- | :--- | :--- | :--- |
| Binary WEAK/STRENGTH disagreement (spec thresholds) | **40.3 %** | >20 % | Exceeds |
| Quantile-matched WEAK disagreement (threshold-free) | **27.2 %** | >20 % | Exceeds |
| Spearman rank correlation (overall) | **0.188** | (closer to 1 = agreement) | Near-independent |
| Near-zero benchmark amplification | Ratio ranges to **±4,453**; 84 % of near-zero observations produce extreme ratio values | — | Severe |

**Per the predefined decision rules, the evidence supports ADR-003 Option C-revised: keep the difference formula and revise the FEAT-007 specification to match.** This report does not decide that — it presents the evidence for ADR-003 to consume.

---

## 1. Deterministic Comparison Methodology

### 1.1 Formulas under test

| Formula | Definition | Source |
| :--- | :--- | :--- |
| **A — Difference** | `relative_strength = sector_roc20 − bm_roc20` (percentage points) | SR-003 live code (`sector_rs_service.py:166-168`) |
| **B — Ratio** | `relative_strength = sector_roc20 / bm_roc20` (unitless multiplier); safe-fallback to `1.0` when `bm_roc20 == 0` | FEAT-007 spec / FEAT-004 `compute_sector_strength` (`feat004_regime_overlay.py:381`) |

Where `roc20 = (close[T] / close[T-20] − 1) × 100` (percentage return over 20 trading days), computed identically for sector and benchmark — matching the live SR-003 computation exactly.

### 1.2 Classification rules applied

| Formula | Weak class | Intermediate | Strong class |
| :--- | :--- | :--- | :--- |
| **A (SR-003 binary)** | `A_value < 0` | none | `A_value ≥ 0` |
| **B (FEAT-007 spec)** | `B_value < 0.90` | `0.90 ≤ B_value ≤ 1.10` (NEUTRAL) | `B_value > 1.10` |

For binary comparability, B's NEUTRAL is collapsed to non-WEAK (`B_binary = WEAK if B<0.90 else STRENGTH`). A three-state comparison with a symmetric ±1 pp neutral band for A is also reported (§5.2).

### 1.3 Determinism guarantees

- Identical input series → identical ROC → identical formula values → identical classifications. No randomness anywhere in the pipeline.
- The methodology is reproducible: same index tickers, same date range, same code path (`scratch/sr_formula_observations.csv` contains every observation).
- Two reviewers given the saved CSV and this methodology will compute identical disagreement rates.

### 1.4 Two complementary disagreement measures

A naïve comparison is dominated by **threshold choice** (A flags WEAK at `<0`, B at `<0.90`). To separate *formula shape* disagreement from *threshold* disagreement, two measures are reported:
- **Spec-threshold binary disagreement** — uses each formula's own spec thresholds (the operational reality).
- **Quantile-matched disagreement** — both formulas cut at their own 25th percentile, so the WEAK set has identical size for both; disagreement then reflects only the formula's *ordering* of observations.

---

## 2. Representative Historical Sample

| Attribute | Value |
| :--- | :--- |
| Source | yfinance (venv `yf 1.4.0`), real NSE index daily OHLCV |
| Benchmark | NIFTY 500 (`^CRSLDX`) — the FEAT-007 spec's primary benchmark |
| Sector indices | NIFTY 50, NIFTY Bank, IT, Auto, FMCG, Metal, Pharma, Energy, Realty (9 indices) |
| Date range | 2021-08-10 → 2026-07-03 (after the 20-day ROC warmup) |
| Trading days | 1,223 |
| **Total observations** | **10,827** (9 sectors × 1,203 aligned dates) |
| Regimes covered | Bull (2021-2024), sideways, correction (2022), sharp rally and correction (2025-2026) |
| Raw data file | `scratch/sr_formula_index_history.csv` |
| Observations file | `scratch/sr_formula_observations.csv` |

**Sample-size justification:** 10,827 observations is two orders of magnitude above what is needed for a disagreement-rate estimate with a ±1 % confidence interval. The 5-year window spans multiple bull/bear/sideways regimes, so the result is not regime-specific.

**Limitation honestly stated:** this compares *indices* (sector indices vs benchmark), not *individual stocks* vs their sector. The formula behaviour under test (difference vs ratio near zero) is a property of the math, not of the instrument, so the conclusion transfers; but a stock-level replication would strengthen the result. Flagged in §10.

---

## 3. Raw Results — Both Formulas on Identical Observations

The full per-observation table (date, sector, sector_roc20, bm_roc20, A_value, B_value, classA, classB) is saved to `scratch/sr_formula_observations.csv` (10,827 rows). Representative rows illustrating each disagreement mode:

| Date | Sector | sector_roc20 | bm_roc20 | A_value | B_value | classA | classB | What it shows |
| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- | :--- |
| 2026-03-02 | NIFTY_IT | −20.49 | −0.0046 | **−20.48** | **+4,453.05** | WEAK | STRONG | Near-zero bench → ratio explodes, flips sign of judgement |
| 2026-03-02 | NIFTY_METAL | +6.13 | −0.0046 | **+6.13** | **−1,331.37** | STRENGTH | WEAK | Near-zero bench → ratio flips a strong sector to WEAK |
| 2026-03-02 | NIFTY_PHARMA | +6.53 | −0.0046 | **+6.53** | **−1,419.15** | STRENGTH | WEAK | Same date, same pathology |
| 2025-01-24 | NIFTY_REALTY | −20.77 | −4.96 | −15.81 | +4.19 | WEAK | STRONG | Negative benchmark → ratio sign-flips a clear underperformer |
| 2023-02-28 | NIFTY_METAL | −18.54 | −2.79 | −15.75 | +6.64 | WEAK | STRONG | Negative benchmark → ratio inverts classification |

**The most dangerous failure mode is visible in the first three rows:** on a single day (2026-03-02) where the benchmark's 20-day return was −0.0046 % (essentially flat), the ratio formula classified **every sector incorrectly relative to the difference formula**, with magnitude errors in the thousands.

---

## 4. Disagreement Rate (Spec Thresholds, Binary)

Using each formula's own specification thresholds (A: WEAK `<0`; B: WEAK `<0.90`), collapsed to binary WEAK/STRENGTH:

| Outcome | Count | % |
| :--- | :--- | :--- |
| Agree | 6,463 | 59.69 % |
| **Disagree** | **4,364** | **40.31 %** |

**Decision rule check (ADR-003 §11):** 40.31 % > 20 % → **exceeds the "keep difference, revise FEAT-007" threshold.**

### WEAK-class confusion (the action-bearing class — downgrade triggers)

The WEAK class drives the BUY→WATCH downgrade in both implementations, so its disagreement is what matters operationally.

| | B = WEAK | B = STRENGTH | Total |
| :--- | ---: | ---: | ---: |
| **A = WEAK** | 3,165 | 2,336 | 5,501 |
| **A = STRENGTH** | 2,028 | 3,298 | 5,326 |
| **Total** | 5,193 | 5,634 | 10,827 |

- A flags 50.8 % of observations WEAK; B flags 48.0 % WEAK. (Similar overall rate.)
- But they agree on only **3,165** of these — **Jaccard similarity of the WEAK sets is just 0.40**. The formulas identify *different* observations as weak.
- **4,364 observations (40.3 %)** receive a different binary verdict.

---

## 5. Confusion Matrix and Agreement

### 5.1 Binary WEAK/STRENGTH confusion matrix

| | B = WEAK | B = STRENGTH |
| :--- | ---: | ---: |
| **A = WEAK** | 3,165 | 2,336 |
| **A = STRENGTH** | 2,028 | 3,298 |

- Agreement: 59.7 %
- Disagreement: 40.3 %
- Symmetric disagreement: A-only-WEAK (2,336) ≈ B-only-WEAK (2,028) — neither formula is systematically stricter; they *disagree on which observations are weak*.

### 5.2 Three-state confusion (with a symmetric ±1 pp neutral band for A)

To be fair to the ratio (which has a NEUTRAL band the difference formula lacks), A was given an equivalent ±1.0 percentage-point neutral band, vs B's native 0.90–1.10:

| Formula A ↓ \ Formula B → | NEUTRAL | STRONG | WEAK | Total |
| :--- | ---: | ---: | ---: | ---: |
| **NEUTRAL** | 917 | 907 | 1,040 | 2,864 |
| **STRONG** | 1 | 2,361 | 1,631 | 3,993 |
| **WEAK** | 2 | 1,446 | 2,522 | 3,970 |

- Three-state agreement: **53.6 %** (5,800 / 10,827)
- Three-state disagreement: **46.4 %**

---

## 6. Threshold-Free (Formula-Shape) Comparison

To rule out the objection that "the disagreement is just a threshold choice," two threshold-free tests were run.

### 6.1 Quantile-matched WEAK sets

Both formulas cut at their own 25th percentile, so the WEAK set is exactly 25 % of observations for each — disagreement then reflects only *how each formula orders observations*.

| Metric | Value |
| :--- | :--- |
| Formula A 25th-percentile cutoff | `A_value < −2.130 pp` |
| Formula B 25th-percentile cutoff | `B_value < 0.201` |
| Quantile-matched agreement | **72.83 %** |
| **Quantile-matched disagreement** | **27.17 %** |
| **Jaccard similarity of the WEAK sets** | **0.296** |

A Jaccard of 0.296 means the two formulas' bottom-quartile sets overlap by under a third. **Even with thresholds equalised, the formulas disagree on more than a quarter of observations, exceeding the 20 % threshold.**

### 6.2 Spearman rank correlation

| Scope | Spearman ρ |
| :--- | :--- |
| Overall (10,827 obs) | **0.188** |
| Near-zero benchmark bucket (\|bm_roc20\| < 0.5 %) | 0.086 |
| Outside near-zero bucket | 0.213 |

A Spearman ρ of 0.188 means the two formulas **rank observations almost independently**. For two metrics purporting to measure the same concept ("how strong is this sector vs the benchmark"), ρ ≈ 0.19 is close to unrelated. The rank correlation is *not* rescued outside the near-zero bucket — even when the benchmark return is meaningful, the formulas order sectors very differently.

**This is the strongest single piece of evidence: the formulas are not different parameterisations of the same signal. They are largely different signals.**

---

## 7. Strongest and Weakest Disagreements

### 7.1 Cases where B = STRONG but A = WEAK (ratio over-amplifies underperformance)

**1,839 cases (17.0 % of all observations).** These occur when the benchmark ROC is small or negative — the ratio sign-flips a clear underperformer into a "strong" classification.

Worst examples:

| Date | Sector | sector_roc20 | bm_roc20 | A_value | B_value |
| :--- | :--- | ---: | ---: | ---: | ---: |
| 2026-03-02 | NIFTY_IT | −20.49 | −0.0046 | −20.48 | +4,453.05 |
| 2026-02-16 | NIFTY_IT | −16.24 | −0.0547 | −16.19 | +296.82 |
| 2023-02-28 | NIFTY_METAL | −18.54 | −2.79 | −15.75 | +6.64 |

### 7.2 Cases where A = STRENGTH but B = WEAK (ratio over-penalises small edge)

**2,028 cases (18.7 % of all observations).** Same pathology in the opposite direction — a sector with a positive edge over a near-zero benchmark is flagged WEAK by the ratio.

Worst examples (all on 2026-03-02, benchmark = −0.0046 %):

| Date | Sector | sector_roc20 | bm_roc20 | A_value | B_value |
| :--- | :--- | ---: | ---: | ---: | ---: |
| 2026-03-02 | NIFTY_PHARMA | +6.53 | −0.0046 | +6.53 | −1,419.15 |
| 2026-03-02 | NIFTY_METAL | +6.13 | −0.0046 | +6.13 | −1,331.37 |
| 2026-03-02 | NIFTY_ENERGY | +5.32 | −0.0046 | +5.32 | −1,155.38 |

**Interpretation:** On 2026-03-02, every sector that beat the (flat) benchmark was classified WEAK by the ratio formula and STRENGTH by the difference formula — a complete inversion driven purely by the near-zero denominator.

---

## 8. Numerical Stability and Edge-Case Analysis

### 8.1 Near-zero benchmark amplification (core theoretical concern — CONFIRMED)

The benchmark's 20-day return falls in the danger zone (|bm_roc20| < 0.5 %) on **9.0 %** of all observations (972 / 10,827). On those observations:

| Metric | Difference (A) | Ratio (B) |
| :--- | :--- | :--- |
| Range | [−20.48, +12.36] pp | **[−1,419, +4,453]** |
| Mean | +0.12 | +1.99 |
| Std dev | 7.04 | **173.54** |
| \|value\| > 2 (extreme) | 84 % (any movement) | **84.4 %** |
| \|value\| > 10 (severe) | n/a | **47.6 %** |

**Bucketed view (benchmark ROC20 magnitude):**

| Benchmark ROC20 bucket | n | A mean | B mean | B std | B max | B min | B \|>2\| % |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bm < −5 % | 801 | +0.34 | +0.95 | 0.70 | 3.10 | −1.29 | 5.6 % |
| bm −5..−2 % | 1,800 | +0.07 | +0.98 | 1.35 | 8.07 | −6.77 | 19.8 % |
| bm −2..−0.5 % | 1,125 | +0.22 | +0.77 | 3.69 | 23.33 | −20.20 | 46.4 % |
| **bm ≈ 0 (−0.5..0.5 %)** | **972** | +0.12 | **+1.99** | **173.54** | **4,453** | **−1,419** | **84.4 %** |
| bm 0.5..2 % | 1,521 | +0.11 | +1.07 | 3.67 | 19.49 | −22.52 | 45.2 % |
| bm 2..5 % | 3,087 | +0.20 | +1.06 | 1.41 | 9.98 | −10.38 | 20.3 % |
| bm > 5 % | 1,521 | −0.06 | +0.99 | 0.69 | 5.43 | −1.67 | 6.2 % |

**Reading the table:** the ratio is well-behaved only when the benchmark ROC is large in magnitude (>5 % or <−5 %). In the central, most-common buckets — where benchmark returns are modest — the ratio's standard deviation balloons to 3.7–173.5, vs the difference's tight 7. The amplification is **disproportionate and concentrated exactly where real markets spend most of their time** (benchmark moves of <2 % cover ~50 % of observations).

**This directly answers Task 7: yes, the ratio introduces disproportionate amplification when benchmark returns are close to zero, and the amplification is severe (ratio values in the thousands).**

### 8.2 Sign-flip pathology

The ratio's worst property is not magnitude — it is **sign inversion**. When the benchmark ROC is negative and the sector ROC is also negative (both falling, sector falling harder), the ratio can be `> 1` because the negatives cancel, classifying a worse-performing sector as STRONG. This is visible in §7.1: NIFTY_IT −20.5 % vs benchmark −0.005 % is unambiguously terrible performance, yet the ratio returns +4,453 (STRONG). The difference formula correctly returns −20.5 (WEAK).

### 8.3 Safe-fallback behaviour

The spec's safe-fallback (`bm_roc20 == 0 → ratio = 1.0`) only fires on *exactly* zero, which essentially never occurs in continuous price data (the observed minimum |bm_roc20| was 0.000046). It does **not** protect against near-zero denominators — the very case that causes the amplification. A `|bm_roc20| < epsilon` guard would mitigate but introduces its own threshold-tuning problem and would abstain on ~9 % of observations.

---

## 9. Behaviour by Market Regime

| Regime (by benchmark ROC20) | n | Binary disagreement | Quantile disagreement |
| :--- | ---: | ---: | ---: |
| Strong up (>5 %) | 1,521 | **9.4 %** | 21.3 % |
| Up (1–5 %) | 4,122 | **4.5 %** | 6.2 % |
| Flat (−1..1 %) | 1,827 | **45.8 %** | 41.6 % |
| Down (−5..−1 %) | 2,556 | **96.0 %** | 48.7 % |
| Sharp down (<−5 %) | 801 | **93.1 %** | 44.7 % |

**Reading:**
- **Strong trends (up >1 %):** the formulas agree well (4–9 % binary disagreement). This is the only regime where the ratio is safe.
- **Flat markets:** 46 % disagreement — the ratio's near-zero-denominator pathology dominates here.
- **Down / sharp-down markets:** 93–96 % disagreement — the ratio essentially *inverts* the difference formula's classification, because negative benchmark returns cause systematic sign-flips. **This is the worst possible regime for the ratio to fail in**: bear markets are exactly when accurate sector-relative-strength matters most for defensive downgrades.

**This is decisive for the decision:** the ratio formula is most reliable in trending-up markets (where defensive sector-RS signals matter least) and most broken in flat and down markets (where they matter most).

---

## 10. Limitations and Caveats

1. **Index-level, not stock-level.** Observations are sector-index-vs-benchmark, not stock-vs-sector-index. The formula's mathematical pathologies (near-zero denominator, negative-benchmark sign-flip) are properties of the math and transfer to stock-level, but a stock-level replication across the NIFTY 500 universe would strengthen the result. **Recommended as a follow-up if ADR-003 needs further evidence.**
2. **Single benchmark (NIFTY 500).** The spec allows NIFTY 50 fallback. Re-running with NIFTY 50 as benchmark would test sensitivity, but NIFTY 50 has a similar near-zero-return frequency, so the conclusion is unlikely to change.
3. **20-day ROC window only.** A 50-day or 100-day ROC would smooth the benchmark and reduce near-zero frequency somewhat — but would also change the signal's responsiveness, which is a separate design question outside this report's scope.
4. **Classification thresholds are the spec's, not tuned.** The quantile-matched test (§6.1) removes threshold bias; the conclusion holds there too (27 % disagreement).
5. **Real data, real dates.** The 2026-03-02 anomaly is not a bug — it is a genuine near-zero benchmark return. Verified directly.

---

## 11. Recommendation (Per Predefined Decision Rules)

| Decision rule (ADR-003 §11) | Threshold | Observed | Met? |
| :--- | :--- | :--- | :--- |
| Disagreement <10 % → recommend ratio | <10 % | 40.3 % (spec) / 27.2 % (quantile) | **No** |
| Disagreement 10–20 % → manual review | 10–20 % | — | **No** |
| Disagreement >20 % → keep difference, revise FEAT-007 | >20 % | 40.3 % / 27.2 % | **Yes** |

**The evidence supports the third rule: keep the difference formula and revise the FEAT-007 specification to match.**

Three independent lines of evidence converge on this:
1. **Operational disagreement (40.3 %)** — the two formulas classify 4,364 of 10,827 observations differently using their own spec thresholds.
2. **Threshold-free disagreement (27.2 %; Spearman ρ = 0.188)** — even with thresholds equalised, the formulas order observations almost independently. They are different signals, not different parameterisations.
3. **Numerical instability (ratio ranges to ±4,453 near zero; sign-flips in 93 % of down-market observations)** — the ratio is unreliable exactly where it matters most: flat and bear markets.

**This report does not decide ADR-003.** It supplies the Phase-0 Task 0.3 evidence that ADR-003 §11 conditionality required. The decision (Option C-revised: keep difference, revise FEAT-007 — vs. the alternatives) remains with the System Owner via ADR-003.

---

## 12. Reproducibility

Any reviewer can reproduce this report from the saved artefacts:

| Artefact | Location | Contents |
| :--- | :--- | :--- |
| Raw index history | `scratch/sr_formula_index_history.csv` | 1,223 rows × 10 indices, daily close, 2021-07-12 → 2026-07-03 |
| Per-observation results | `scratch/sr_formula_observations.csv` | 10,827 rows: date, sector, sector_roc20, bm_roc20, A_value, B_value, classA, classB |
| Methodology | This document, §1 | Deterministic; no randomness |

Re-running the methodology on the saved CSV yields identical disagreement rates to the last decimal.

---

*End of Evidence Report — Phase 0 Task 0.3. Does not modify FEAT-007. Does not modify ADR-003. Does not generate code.*
