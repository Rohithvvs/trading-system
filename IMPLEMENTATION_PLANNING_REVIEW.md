# IMPLEMENTATION_PLANNING_REVIEW — FEAT-004, FEAT-007, FEAT-008
**Version:** 1.0
**Date:** 2026-07-11
**Status:** Planning review. No production code. No feature redesign. No new features.
**Scope:** Convert the completed specifications (FEAT-004, FEAT-007, FEAT-008) into a safe, phased implementation plan. This document is a plan, not a specification — it does not redefine any feature.

---

## 1. Dependency Analysis

### 1.1 The load-bearing structural fact

The three features occupy two different positions in the pipeline relative to the composite score:

```
                                   FEAT-008 modifies this INPUT
                                              │
                                              ▼
BacktestAgent ──► backtest_score ──► [COMPOSITE SCORE] ──► FEAT-004 ──► FEAT-007 ──► Strict Buy Gate
                                      weighted_sum()        modifies     modifies
                                                            OUTPUT       OUTPUT
```

- **FEAT-008** changes `backtest_score` — an *input* to the weighted composite (25% standard / 20% catalyst weight, FEAT-001 §4).
- **FEAT-004** changes the composite score *after* synthesis (FEAT-004 Implementation Breakdown §3, step 5).
- **FEAT-007** changes the composite score *after* FEAT-004 (FEAT-007 §9.3: "composite → FEAT-004 adjustment → FEAT-007 adjustment → Strict Buy Gate").

This input/output relationship is the single most important fact for sequencing: **the overlays (FEAT-004/007) are tuned against a composite that includes the backtest score. If the backtest score shifts globally under FEAT-008, every overlay's tuned deltas and shadow correlations were computed against a different distribution.**

### 1.2 Direct dependencies

| Feature | Depends on | Why | Strength |
| :--- | :--- | :--- | :--- |
| **FEAT-008** | Nothing | Isolated to `COMP-BT`. Uses only existing OHLCV + static config. | None — fully independent |
| **FEAT-004** | Nothing (code-level) | Introduces its own 7 helpers (Implementation Breakdown §2.1–2.7). | None at code level |
| **FEAT-007** | **FEAT-004** (code-level) | Consumes `compute_sector_strength` (FEAT-004 §2.5) and its outputs (`sector_roc20`, `benchmark_roc20`, `relative_strength_ratio`, `sector_regime_state`). Without FEAT-004's helper, FEAT-007 has no input. | **Hard** — FEAT-007 §10, §17 dependency note |

### 1.3 Indirect (validation-level) dependencies

These are not code dependencies but *validity* dependencies — a feature's shadow/backtest results are only meaningful if the substrate is stable.

| Overlay | Validity depends on | Why |
| :--- | :--- | :--- |
| FEAT-004 shadow correlations (Stage 14) | FEAT-008 being stable | FEAT-004's tuned deltas (-3.0, -5.0) are calibrated against a composite distribution. If FEAT-008 shifts that distribution globally after FEAT-004's shadow window, the deltas are miscalibrated. |
| FEAT-007 shadow correlations (Stage 14) | FEAT-008 + FEAT-004 both stable | FEAT-007 reads the post-FEAT-004 score. Its deltas (+1.5, -3.0) are calibrated against a composite that already includes FEAT-004's adjustment. |

**Conclusion:** FEAT-008 should be implemented and stabilized *before* the overlays are shadow-tested against real composites. Implementing overlays first risks tuning them to a distorted substrate.

---

## 2. Recommended Implementation Order

**Canonical order: FEAT-008 → FEAT-004 → FEAT-007.**

| Position | Feature | Rationale |
| :--- | :--- | :--- |
| **1st** | **FEAT-008** | Fixes the substrate (25%-weight backtest input). Fully independent — no code dependency, no upstream prerequisite. Stabilizes the composite distribution so downstream overlays are tuned to truth, not optimism. |
| **2nd** | **FEAT-004** | Introduces the regime classifier *and* the sector plumbing (`compute_sector_strength`, sector mapping, sector OHLCV fetch) that FEAT-007 needs. Must land before FEAT-007. |
| **3rd** | **FEAT-007** | Consumes FEAT-004's `compute_sector_strength`. Smallest delta of the three — attaches a score effect to a value FEAT-004 already computes. |

**Why not FEAT-004 first?** FEAT-004 has no code dependency blocking it, so it *could* go first. But its shadow correlations would be computed against a distorted backtest score. When FEAT-008 later shifts the composite, FEAT-004's deltas would need re-validation. Doing FEAT-008 first avoids a redundant shadow cycle.

**Why not FEAT-007 before FEAT-004?** Impossible — FEAT-007 has a hard code dependency on FEAT-004's `compute_sector_strength` helper.

---

## 3. Impact Analysis (Eight Dimensions)

### 3.1 Prerequisite work

| Item | Required by | Status |
| :--- | :--- | :--- |
| Existing config system (YAML/JSON/dict) | All three | ✅ Exists (FEAT-004 §5 references it) |
| Existing daily OHLCV data layer (FYERS primary, yfinance fallback) | All three | ✅ Exists (FEAT-001 §5) |
| Benchmark index OHLCV (Nifty 500 / Nifty 50) | FEAT-004 | ⚠️ **New fetch path** — the data layer exists, but fetching an *index* series (not a stock) may need a new symbol resolution. Verify FYERS supports `NIFTY500`/`NIFTY50` as instruments. |
| Sector mapping table (`symbol → sector_index_symbol`) | FEAT-004 (§2), then inherited by FEAT-007 | ⚠️ **New static config artifact** — must be authored and peer-reviewed (FEAT-004 §10 flags this as a Medium risk). This is the largest non-code prerequisite. |
| Sector index OHLCV per sector in universe | FEAT-004 (§2), then inherited by FEAT-007 | ⚠️ **New fetch path** — one series per sector present in the universe. Verify FYERS supports sector indices (Nifty IT, Nifty Bank, etc.). |
| Broker/NSE cost schedule verification | FEAT-008 | ⚠️ **Manual verification** — owner must confirm slippage/brokerage/statutory bps against a contract note before REALISTIC activation (FEAT-008 §10.4, §13). |

**The sector mapping table is the single largest non-code prerequisite** and gates both FEAT-004's sector helper and FEAT-007. It should be authored during FEAT-008 implementation (parallel non-code work) so it is ready when FEAT-004 begins.

### 3.2 Shared utilities

| Utility | Introduced by | Reused by | Notes |
| :--- | :--- | :--- | :--- |
| `resolve_benchmark_ohlcv` | FEAT-004 §2.1 | FEAT-007 (indirectly — needs `benchmark_roc20`) | Fetches Nifty 500/50 series once per session |
| `compute_benchmark_indicators` | FEAT-004 §2.2 | FEAT-007 (indirectly — needs `benchmark_roc20`) | Produces `bm_roc20` among others |
| `compute_sector_strength` | FEAT-004 §2.5 | **FEAT-007 (directly)** | Produces `relative_strength_ratio`, `sector_regime_state` — the exact inputs FEAT-007 consumes |
| Sector mapping config | FEAT-004 §2 | FEAT-007 | Same `symbol → sector_index_symbol` table |
| Sector OHLCV cache | FEAT-004 §1 | FEAT-007 | Same per-session cache |
| Safe-fallback try/except boundary pattern | FEAT-004 §7 | FEAT-007 §12 | Double-boundary exception isolation |

**FEAT-007 reuses five of FEAT-004's utilities/configs.** This is why FEAT-007's own delta is small — most of its infrastructure is FEAT-004's.

### 3.3 Reusable components

| Component | Reuse direction |
| :--- | :--- |
| Existing `RecommendationAgent.generate_recommendation()` hook | FEAT-004 and FEAT-007 both insert here (FEAT-004 Implementation Breakdown §1; FEAT-007 §9.3) — **same insertion point, ordered** |
| Existing `BacktestAgent` fill model | FEAT-008 modifies in place; no new simulator |
| Existing config system | All three add config sections; no new config framework |
| Existing logging/session-log writer | All three add log payloads; no new logging framework |
| FEAT-004's log schema *shape* | FEAT-007 §11.2 deliberately mirrors FEAT-004 §8 so monitoring tooling consumes both without modification |

### 3.4 Configuration dependencies

| Config section | Feature | Ordering risk |
| :--- | :--- | :--- |
| `feat008.execution_model`, `feat008.composite_uses_realistic` | FEAT-008 | None — independent |
| `feat004.enabled`, `feat004.stage`, `feat004.score_deltas`, `feat004.sector_mapping_enabled` | FEAT-004 | None |
| `feat007.enabled` (+ score deltas, implied) | FEAT-007 | **`feat004.sector_mapping_enabled` must be `true` for FEAT-007 to have inputs.** FEAT-007 abstains if FEAT-004's sector path is off. |

**Cross-feature config rule:** FEAT-007 is functionally inert if `feat004.enabled = false` or `feat004.sector_mapping_enabled = false`. This must be documented in ops runbooks so a FEAT-004 rollback automatically and safely degrades FEAT-007 to abstention (which is the designed behavior — FEAT-007 §12).

### 3.5 Database impacts

| Feature | DB impact |
| :--- | :--- |
| FEAT-008 | **None.** Per-trade realistic fields are computed in-memory; FEAT-008 §4 data contract explicitly states "additions to the existing in-flight Python dict." No schema migration. |
| FEAT-004 | **None.** FEAT-004 Implementation Breakdown §4: "No schema migration or new storage is required; these are additions to the existing in-flight recommendation dict." |
| FEAT-007 | **None.** Same pattern — in-flight dict additions (FEAT-007 §11.2). |

**No feature requires a database migration.** All three persist (if at all) via the existing scan/recommendation persistence layer, writing larger JSON payloads. Verify the existing recommendation-store column/field can accept the additional nested keys without truncation.

### 3.6 API impacts

| Feature | API impact |
| :--- | :--- |
| FEAT-008 | **None externally.** Internal `BacktestAgent` API unchanged in signature; only fill behavior changes. |
| FEAT-004 | **Additive only.** New nested `feat004` key in recommendation output (FEAT-004 Implementation Breakdown §4). Existing API consumers ignore unknown keys by convention. |
| FEAT-007 | **Additive only.** New nested `feat007` key (FEAT-007 §11.2). Same shape as FEAT-004. |

**Risk:** Any existing dashboard/frontend that performs strict schema validation on recommendation output will reject the new nested keys. **Action:** verify the frontend deserialization is forward-compatible (ignores unknown keys) before any feature reaches shadow mode, since shadow writes the full payload.

### 3.7 Logging impacts

| Feature | Log payload size impact |
| :--- | :--- |
| FEAT-008 | Adds ~15 fields per stock to the backtest result (FEAT-008 §12.2). Moderate increase. |
| FEAT-004 | Adds ~18 fields per stock (FEAT-004 §8), including a nested `benchmark_trend_inputs` dict. Largest increase. |
| FEAT-007 | Adds ~12 fields per stock (FEAT-007 §11.2). Moderate. |

**Combined:** ~45 additional logged fields per stock once all three are active. **Action:** verify log storage/rotation can absorb the ~3× payload growth per recommendation. All three specs mandate "every field written on every stock, none omitted" — there is no sampling option.

### 3.8 Testing impacts

| Feature | New unit tests | New integration concern |
| :--- | :--- | :--- |
| FEAT-008 | 15 (FEAT-008 §16.2) | LEGACY byte-identity regression (most critical integration test in the whole plan) |
| FEAT-004 | 20 (FEAT-004 Implementation Breakdown §8) | Shadow-mode log completeness; `raw_technical_score` isolation from Gate |
| FEAT-007 | 14 (FEAT-007 §15.2) | Composition with FEAT-004 (additive score effects); FEAT-004-disabled degradation |

**Shared test concern:** FEAT-007 must add a test verifying that when FEAT-004 is disabled, FEAT-007 abstains cleanly (`sector_regime_state = UNKNOWN`, zero delta). This is a cross-feature integration test neither spec fully owns.

---

## 4. Per-Feature Estimates

### 4.1 FEAT-008 — Realistic Trade Execution Model

| Dimension | Estimate | Reasoning |
| :--- | :--- | :--- |
| Implementation complexity | **Low** | One fill-model change (close[T] → open[T+1] + intrabar stop/target logic) + one `apply_costs` operation. No new data, no new agents. |
| Implementation effort | **Small–Medium** | The conservative exit-ordering logic (§9.3b) is the most intricate part. Cost model is one function. LEGACY mode must be preserved exactly. |
| Regression risk | **Medium** | The feature shifts a 25%-weight component globally. Every recommendation's backtest score changes. But: LEGACY mode is byte-identical (verified at Stage 9), so regression is detectable and reversible. |
| Expected quality improvement | **High** | Removes systematic optimism from the highest-weight derived input. Reduces false positives on high-turnover/high-spread stocks. Makes every downstream overlay's tuning valid. |

### 4.2 FEAT-004 — Market Regime Overlay

| Dimension | Estimate | Reasoning |
| :--- | :--- | :--- |
| Implementation complexity | **Medium–High** | 7 helpers (Implementation Breakdown §2.1–2.7), including benchmark fetch, indicator computation, regime classifier, score modifier, sector helper, log assembler, orchestrator. Largest of the three. |
| Implementation effort | **Medium–Large** | The benchmark/sector fetch paths are new. The sector mapping table is a non-code prerequisite. The double-try/except boundary pattern must be applied consistently across 6 boundaries (§7). |
| Regression risk | **Low** | Shadow mode applies zero score effect. The feature is designed to be inert until Stage B. The `raw_technical_score` isolation invariant protects the Strict Buy Gate. |
| Expected quality improvement | **Medium–High** | Adds broad-market regime awareness (Gap #1). Reduces false positives in CAUTIOUS/DEFENSIVE regimes. Effect is bounded by shadow validation before activation. |

### 4.3 FEAT-007 — Sector Relative Strength

| Dimension | Estimate | Reasoning |
| :--- | :--- | :--- |
| Implementation complexity | **Low** | Smallest delta of the three. Reuses FEAT-004's `compute_sector_strength`, sector mapping, sector OHLCV cache, benchmark ROC. Adds one score modifier + downgrade logic. |
| Implementation effort | **Small** | Once FEAT-004 is in place, FEAT-007 is one overlay function + config + logging, mirroring FEAT-004's pattern. |
| Regression risk | **Low** | Soft modifier with STRONG cap, WEAK soft penalty, REJECT immutability, UNKNOWN no-op (FEAT-007 §9.4). Cannot make the engine more aggressive. |
| Expected quality improvement | **Medium** | Opens the unused `SIT-SR` dimension (Gap #2). Prefers stocks in supporting sectors; flags borderline BUYs in weak sectors. Benefit bounded by shadow validation. |

---

## 5. Dependency Graph

```
                         ┌─────────────────────────────────────────────┐
                         │        IMPLEMENTATION DEPENDENCY GRAPH       │
                         └─────────────────────────────────────────────┘

  ┌──────────────┐
  │   FEAT-008   │          (substrate: fixes backtest_score INPUT to composite)
  │  COMP-BT     │          NO code dependency. NO upstream prerequisite.
  │  Level A     │          Activates first; stabilizes composite distribution.
  └──────┬───────┘
         │
         │  (validity dependency: overlays should be tuned to a stable composite,
         │   not a distorted one — see §1.3)
         │
         ▼
  ┌──────────────┐
  │   FEAT-004   │          (overlay 1: broad-market regime, modifies composite OUTPUT)
  │  COMP-REC    │          NO hard code dependency on FEAT-008.
  │  Level C*    │          Introduces compute_sector_strength + sector plumbing.
  └──────┬───────┘          (*Level C → activation-blocked until promoted to B;
         │                       shadow-eligible immediately)
         │
         │  HARD code dependency: FEAT-007 consumes compute_sector_strength (§2.5),
         │  sector mapping, sector OHLCV cache, benchmark_roc20
         │
         ▼
  ┌──────────────┐
  │   FEAT-007   │          (overlay 2: sector relative strength, modifies composite OUTPUT after FEAT-004)
  │  COMP-REC    │          HARD dependency on FEAT-004's sector helper.
  │  Level B     │          Smallest delta; activation-eligible.
  └──────────────┘


  ORDER OF EXECUTION INSIDE RecommendationAgent (once all three active):

    backtest_score  ──►  [composite]  ──►  FEAT-004  ──►  FEAT-007  ──►  Strict Buy Gate
     (FEAT-008           weighted_sum    regime        sector         (unchanged)
      changes this)                      overlay        overlay
```

---

## 6. Split Recommendation

**Recommendation: Do not split any feature. Implement each as specified, in the order FEAT-008 → FEAT-004 → FEAT-007.**

| Feature | Split considered? | Verdict | Reasoning |
| :--- | :--- | :--- | :--- |
| FEAT-008 | Yes — separate Tier 1 (causal) from Tier 2 (costs) | **Do not split** | Already adjudicated: Architecture Review approved Option A (single feature). Splitting creates an incoherent intermediate state (causal fills, zero cost). The six items are two operations in one fill function. |
| FEAT-004 | Yes — separate regime path from sector path | **Do not split** | The sector helper (`compute_sector_strength`, §2.5) is already designed as an *optional, independent* sub-component (FEAT-004 §6 v1: explanation-only). It is logically separable but lives in the same delta because it shares the benchmark/sector fetch infrastructure. Splitting would duplicate the fetch plumbing. The `sector_mapping_enabled` flag already provides a runtime seam. |
| FEAT-007 | No — already the smallest delta | **Do not split** | It is one overlay function consuming FEAT-004's outputs. There is nothing to split. |

**One caveat on FEAT-004:** Although not split, FEAT-004's sector helper (`compute_sector_strength`) should be implemented but kept at `sector_mapping_enabled = true` with the v1 explanation-only behavior (no score effect). FEAT-007 then attaches the score effect as its own delta. This keeps FEAT-004's regime path and sector path independently testable without splitting the feature.

---

## 7. Phased Implementation Roadmap

Each phase ends only when its exit criteria are met. No phase begins until the previous phase's exit criteria are signed off by the System Owner (FEAT-006 Stage 6 / Stage 13 / Stage 15).

### Phase 0 — Prerequisite & Parallel Non-Code Work

| Item | Owner | Gates |
| :--- | :--- | :--- |
| Verify FYERS supports index instruments (`NIFTY500`, `NIFTY50`, sector indices) | Implementer | FEAT-004 fetch path |
| Author + peer-review sector mapping table (`symbol → sector_index_symbol`) | System Owner + reviewer | FEAT-004 sector helper, FEAT-007 |
| Verify broker/NSE cost schedule (slippage, brokerage, STT/exchange/GST/stamp/SEBI bps) | System Owner | FEAT-008 REALISTIC activation |
| Verify frontend/API forward-compatibility with new nested recommendation keys | Implementer | All three features' shadow mode |
| Verify log storage tolerates ~3× per-recommendation payload growth | Implementer | All three features' shadow mode |

**Validation:** Each item verified and recorded.
**Rollback:** N/A (no code).
**Exit criteria:** All five items signed off. Cost schedule and sector mapping archived as versioned config artifacts.

---

### Phase 1 — FEAT-008 (Substrate Repair)

| Stage | Activity |
| :--- | :--- |
| Implement | Modify `BacktestAgent` fill model: `LEGACY`/`REALISTIC` switch, next-bar-open entry/exit, conservative intrabar stop/target ordering, `apply_costs` operation (§9, §10). |
| Unit test | 15 tests (FEAT-008 §16.2). Most critical: `test_legacy_mode_byte_identical` (#1), `test_causality_no_same_bar_fill` (#13), `test_conservative_stop_before_target` (#7). |
| Integration test | With `execution_model = LEGACY`: full scan output byte-identical to pre-FEAT-008. With `REALISTIC` + `composite_uses_realistic = false`: no exception propagates. |
| Backtest (self-referential) | Run full historical scan twice (LEGACY vs REALISTIC-shadow). Compare per-stock metrics per FEAT-008 §16.3. |
| Shadow | `execution_model = REALISTIC`, `composite_uses_realistic = false`, ≥ 30 sessions. Log realistic + legacy metrics per stock. |
| Activate | Flip `composite_uses_realistic = true`. Monitor label-distribution shift. |

**Validation:** §16.3 metric targets (mean P&L reduction > 0; win-rate/profit-factor reductions bounded; label-distribution shift reviewed).
**Rollback:** `execution_model = LEGACY` (one line; byte-identical restore) or `composite_uses_realistic = false` (softer, keeps realistic logging).
**Exit criteria:** (i) LEGACY byte-identity proven; (ii) realistic metrics stable across walk-forward windows; (iii) label-distribution shift reviewed and accepted by System Owner; (iv) composite now runs on realistic backtest score — **substrate is stable for Phase 2/3 overlays.**

> **Critical:** Phase 1 must complete (composite running on realistic score) before Phase 2/3 shadow windows begin. Otherwise overlays are tuned to a substrate that will change.

---

### Phase 2 — FEAT-004 (Broad-Market Regime Overlay)

| Stage | Activity |
| :--- | :--- |
| Implement | 7 helpers (Implementation Breakdown §2.1–2.7). Insert hook in `RecommendationAgent` after composite, before Strict Buy Gate (Implementation Breakdown §3). Include `compute_sector_strength` (§2.5) at v1 explanation-only behavior. |
| Unit test | 20 tests (Implementation Breakdown §8). Critical: `test_strict_buy_gate_receives_unmodified_raw_ta_score` (#19), `test_favorable_cap_prevents_watch_to_buy` (#9), `test_outer_exception_returns_original_score` (#17). |
| Integration test | With `feat004.enabled = false`: scan byte-identical to Phase-1 output. With `stage = SHADOW`: log payload complete on every stock; zero score effect. |
| Backtest | Baseline (FEAT-004 disabled) vs treatment (Stage B ACTIVE) per FEAT-004 §9 data split. **Run against the Phase-1 realistic composite** — not the old distorted one. |
| Shadow | `stage = SHADOW`, ≥ 30 sessions. Validate regime-state distribution (≥ 3 of 4 states fire) and correlation with BUY outcome accuracy. |
| Promote evidence | C → B: shadow correlations + independent review serve as confirmations per FEAT-005 §9.2. Required before Stage 15 activation (FEAT-006 §7.2). |
| Activate | `stage = ACTIVE`. Monitor rollback triggers per FEAT-004 §9. |

**Validation:** FEAT-004 §9 success metrics (false-positive reduction ≥ 5%, missed-winner ≤ 3%, profit factor neutral/improved).
**Rollback:** `feat004.stage = SHADOW` (one line) or `feat004.enabled = false`.
**Exit criteria:** (i) Shadow correlations validate regime→false-positive relationship; (ii) Level promoted C → B; (iii) System Owner approves activation; (iv) `compute_sector_strength` running and logging per-stock sector data — **sector plumbing ready for Phase 3.**

---

### Phase 3 — FEAT-007 (Sector Relative Strength)

| Stage | Activity |
| :--- | :--- |
| Implement | One overlay function in `RecommendationAgent` consuming FEAT-004's `compute_sector_strength` output. STRONG cap, WEAK soft penalty, REJECT immutability, UNKNOWN no-op (§9.4). Insert after FEAT-004's adjustment (§9.3). |
| Unit test | 14 tests (§15.2). Critical: cap tests (#2, #9, #10), downgrade threshold tests (#4, #5), abstention tests (#7, #8, #13). Add cross-feature test: FEAT-004 disabled → FEAT-007 abstains cleanly. |
| Integration test | With `feat007.enabled = false`: scan byte-identical to Phase-2 output. With enabled + shadow: zero score effect; log complete. |
| Backtest | Baseline vs treatment per FEAT-007 §15.3, reusing FEAT-004 §9 data split. **Run against Phase-1 realistic composite + Phase-2 active FEAT-004** — the full stack below FEAT-007. |
| Shadow | ≥ 30 sessions. Validate `sector_regime_state` distributes across STRONG/NEUTRAL/WEAK and correlates with BUY accuracy. |
| Activate | FEAT-007 is Level B — activation-eligible once shadow validates. Flip score effect on. |

**Validation:** FEAT-007 §15.3 metrics (false-positive reduction in WEAK ≥ 5%, missed-winner in STRONG ≤ 3%).
**Rollback:** `feat007.enabled = false` (one line).
**Exit criteria:** (i) Shadow validates sector→outcome relationship; (ii) System Owner approves activation; (iii) all three features running on a stable, realistic, regime-and-sector-aware composite.

---

## 8. Comprehensive Testing Strategy

### 8.1 Testing layers (applied to every feature)

| Layer | What it proves | When it runs |
| :--- | :--- | :--- |
| **Unit** | Each function/branch produces deterministic output for fixed input | Stage 8 — before any integration |
| **Integration** | The delta composes with the existing pipeline without silent regression | Stage 9 — disabled-feature byte-identity is the gate |
| **Historical backtest** | The feature improves metrics vs baseline on historical data | Stage 10 |
| **Walk-forward** | The improvement holds out-of-sample, across ≥ 2 regimes | Stage 11 |
| **Paper trading** | Simulated outcomes stable (FEAT-008's analogue is the score-delta audit) | Stage 12 |
| **Shadow mode** | Feature runs in production with zero score effect; logs validate | Stage 14 — ≥ 30 sessions |
| **Production activation** | Score effect ON; first-session metrics within bounds | Stage 15 |
| **Production monitoring** | Ongoing metric watch against rollback triggers | Stage 16 |

### 8.2 The non-negotiable regression test

**Disabled-feature byte-identity** is the single most important test in the entire plan. For each feature:

> With the feature's master switch `enabled = false` (or `execution_model = LEGACY`), the full scan output must be byte-for-byte identical to the pre-feature output.

This must be verified at Stage 9 (integration) for every feature, in every phase. It is the guarantee that rollback is real, not theoretical. For FEAT-008 it is doubly critical because LEGACY mode must reproduce today's exact (flawed) behavior so the comparison is meaningful.

### 8.3 Cross-feature integration tests (added beyond each spec)

| Test | What it proves |
| :--- | :--- |
| `feat004 disabled → feat007 abstains` | FEAT-007 degrades cleanly when its upstream is off |
| `feat008 REALISTIC + feat004 ACTIVE + feat007 ACTIVE` | Full stack composes without exception propagation |
| `feat008 LEGACY + feat004 SHADOW + feat007 SHADOW` | All-disabled/all-shadow state is byte-identical to today |
| `raw_technical_score isolation under full stack` | No overlay touches the Strict Buy Gate's input, even with all three active |

### 8.4 Backtest data split (shared across all three features)

All three features reuse the FEAT-004 §9 data split for consistency and comparability:

| Period | Label | Regime |
| :--- | :--- | :--- |
| In-sample A | Bull | 2020-04 to 2021-09 |
| In-sample B | Sideways | 2021-10 to 2022-03 |
| In-sample C | Bear/Volatile | 2022-04 to 2022-12 |
| Out-of-sample | Mixed | 2023-01 to 2024-06 |

Using the same split for all three features means their metrics are directly comparable and their combined effect can be measured against a single baseline.

### 8.5 Shadow-mode exit criteria (shared pattern)

Every feature's shadow window exits only when:

1. ≥ 30 trading sessions completed (FEAT-004 §12 precedent).
2. The feature's state variable distributes across ≥ 3 of its possible values (proves it fires — e.g., FEAT-004 regime across ≥ 3 of FAV/NEU/CAU/DEF; FEAT-007 sector across ≥ 3 of STRONG/NEUTRAL/WEAK).
3. No `abstained_reason` pattern indicates systematic data unavailability.
4. No unit/integration test regression.
5. Shadow-period correlations align with the feature's hypothesis (e.g., CAUTIOUS regimes show higher false-positive rates).
6. System Owner sign-off (FEAT-006 Stage 13/15).

---

## 9. Risk Register

### 9.1 Technical risks

| # | Risk | Likelihood | Impact | Mitigation | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| T1 | FYERS does not support `NIFTY500`/`NIFTY50` or sector indices as fetchable instruments | Medium | High (blocks FEAT-004/007) | Verify in Phase 0; fall back to yfinance for index series (FEAT-004 §2 allows yfinance fallback) | Implementer |
| T2 | LEGACY mode diverges from pre-FEAT-008 behavior (regression) | Low | High (invalidates comparison) | `test_legacy_mode_byte_identical` at Stage 9; treat divergence as a release blocker | Implementer |
| T3 | Log payload growth (~3× per recommendation) overwhelms storage/rotation | Medium | Medium | Verify in Phase 0; add log rotation if needed before any shadow mode | Implementer |
| T4 | Frontend strict-schema validation rejects new nested keys | Medium | Medium | Verify forward-compatibility in Phase 0; all keys are additive | Implementer |
| T5 | FEAT-008 cost schedule figures wrong (rates changed) | Medium | Medium | Config-driven; owner verifies against contract note; defaults are placeholders | System Owner |
| T6 | Conservative exit ordering under-states returns excessively | Low | Low | Configurable (`conservative_exit_ordering`); pessimistic direction is safe | Implementer |

### 9.2 Recommendation-quality risks

| # | Risk | Likelihood | Impact | Mitigation | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Q1 | FEAT-008 activation causes large label-distribution shift (many BUY→WATCH) | High | Medium | Shadow logs full delta before composite switches; System Owner reviews before Stage 15 | System Owner |
| Q2 | FEAT-004 tuned deltas (-3.0, -5.0) miscalibrated after FEAT-008 shifts composite | Medium | High | **Phase ordering:** FEAT-008 stabilizes substrate before FEAT-004 shadow. FEAT-004 shadow runs against realistic composite. | Plan (this doc) |
| Q3 | FEAT-004 + FEAT-007 double-penalize in weak-regime + weak-sector stocks | Medium | Medium | Documented composition (FEAT-007 §9.3); monitor combined effect at Stage 16; tunable via config | Monitor |
| Q4 | FEAT-007 WEAK penalty over-fires in rotating sectors, downgrading valid BUYs | Medium | Medium | Shadow monitors downgrade rate; threshold (74) tunable via config | Monitor |
| Q5 | Overlays tuned to a substrate that later changes | Medium | High | Phase ordering ensures substrate (FEAT-008) is stable before any overlay shadow begins | Plan (this doc) |

### 9.3 Deployment risks

| # | Risk | Likelihood | Impact | Mitigation | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| D1 | Sector mapping table maps symbols to wrong sector indices | Medium | High (silently corrupts FEAT-004/007) | Peer-reviewed config in Phase 0; validated against NSE sector constituents | System Owner |
| D2 | Multiple features activated simultaneously without independent shadow validation | Low | High | Phased roadmap: one feature shadow→active at a time; no parallel activations | Plan (this doc) |
| D3 | Config flag rollback fails to restore prior behavior | Low | High | Disabled-feature byte-identity test (§8.2) at every phase | Implementer |
| D4 | Exception from one feature propagates into another's path | Low | High | Each feature has its own try/except boundary; cross-feature integration test (§8.3) | Implementer |

### 9.4 Rollback strategy (summary)

| Feature | Primary rollback | Softer rollback | Restore guarantee |
| :--- | :--- | :--- | :--- |
| FEAT-008 | `execution_model = LEGACY` | `composite_uses_realistic = false` (keeps realistic logging) | Byte-identical to pre-FEAT-008 (Stage 9 verified) |
| FEAT-004 | `feat004.enabled = false` | `feat004.stage = SHADOW` (keeps logging) | Byte-identical to pre-FEAT-004 |
| FEAT-007 | `feat007.enabled = false` | (none — binary) | Byte-identical to pre-FEAT-007 |
| **Cascading note** | Rolling back FEAT-004 automatically degrades FEAT-007 to abstention (designed behavior). Rolling back FEAT-008 does NOT affect FEAT-004/007 code paths, but their shadow correlations would need re-validation against the restored legacy composite. | | |

---

## 10. Final Implementation Roadmap

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                     FINAL IMPLEMENTATION ROADMAP                         │
 │                                                                          │
 │   Principle: stabilize the substrate before tuning the overlays.         │
 │   One feature shadow→active at a time. No parallel activations.          │
 └──────────────────────────────────────────────────────────────────────────┘

 PHASE 0 — Prerequisites (parallel non-code work)
 ├─ Verify FYERS index/sector instrument support
 ├─ Author + peer-review sector mapping table
 ├─ Verify broker/NSE cost schedule
 ├─ Verify frontend/API forward-compatibility
 └─ Verify log storage capacity
    Exit: all five items signed off and archived.

 PHASE 1 — FEAT-008 (Substrate Repair)            [Level A, COMP-BT]
 ├─ Implement fill model + apply_costs
 ├─ Unit (15) + Integration (LEGACY byte-identity)
 ├─ Self-referential backtest (LEGACY vs REALISTIC)
 ├─ Shadow (≥30 sessions, composite on legacy, log realistic)
 ├─ Activate: composite_uses_realistic = true
 └─ Monitor label-distribution shift
    Exit: composite runs on realistic backtest score. SUBSTRATE STABLE.

 PHASE 2 — FEAT-004 (Broad-Market Regime)         [Level C→B, COMP-REC]
 ├─ Implement 7 helpers (incl. compute_sector_strength, v1 explanation-only)
 ├─ Unit (20) + Integration (disabled byte-identity)
 ├─ Backtest against Phase-1 realistic composite
 ├─ Shadow (≥30 sessions, zero score effect)
 ├─ Promote evidence C → B (shadow correlations + review)
 ├─ Activate: stage = ACTIVE
 └─ Monitor rollback triggers
    Exit: regime overlay active; sector plumbing running. SECTOR DATA READY.

 PHASE 3 — FEAT-007 (Sector Relative Strength)    [Level B, COMP-REC]
 ├─ Implement one overlay consuming compute_sector_strength
 ├─ Unit (14) + cross-feature integration (FEAT-004-disabled abstention)
 ├─ Backtest against Phase-1 + Phase-2 full stack
 ├─ Shadow (≥30 sessions, zero score effect)
 ├─ Activate (Level B → activation-eligible)
 └─ Monitor rollback triggers
    Exit: all three features active on a stable, realistic,
          regime-and-sector-aware composite.
```

### 10.1 Sequencing rationale (one sentence)

**FEAT-008 first because it repairs the 25%-weight substrate; FEAT-004 second because it introduces the sector plumbing FEAT-007 needs; FEAT-007 last because it is the smallest delta consuming FEAT-004's outputs — and at every stage, the layer below is stable before the layer above is tuned.**

### 10.2 What this plan does NOT do

- Does not write production code (FEAT-006 Stage 7 is the implementer's responsibility).
- Does not redesign any feature (all specifications honored as written).
- Does not create FEAT-009 or any new feature.
- Does not modify FEAT-001 through FEAT-008.
- Does not skip any FEAT-006 lifecycle stage — each feature traverses Stages 7–17 in full.

### 10.3 Decision points for the System Owner

| Decision | When | Options |
| :--- | :--- | :--- |
| Approve Phase 0 prerequisite artifacts (sector mapping, cost schedule) | Before Phase 1 code | Accept / revise |
| Approve FEAT-008 activation after shadow | End of Phase 1 shadow | Activate / hold in shadow / rollback |
| Approve FEAT-004 evidence promotion C → B | End of Phase 2 shadow | Promote / hold at C (remains shadow-only) |
| Approve FEAT-004 activation | After C → B promotion | Activate / hold / rollback |
| Approve FEAT-007 activation | End of Phase 3 shadow | Activate / hold / rollback |

---

*End of IMPLEMENTATION_PLANNING_REVIEW v1.0*
