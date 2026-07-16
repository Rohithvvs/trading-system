# IMPLEMENTATION_MASTER_PLAN — FEAT-004, FEAT-007, FEAT-008
**Version:** 1.0
**Date:** 2026-07-11
**Status:** Engineering execution guide. No production code. No feature redesign.
**Scope:** Convert the approved specifications into an actionable engineering roadmap, **grounded in the actual current state of the codebase** (audited 2026-07-11).

---

## ⚠️ Read This First — Codebase Reality vs. Specification

A full codebase audit (2026-07-11) established that **substantial implementation already exists under different internal labels**. The three approved FEAT specifications were written against the *architectural description* in FEAT-001, not against a line-by-line reading of the current code. The result is that the specifications and the codebase disagree in several places.

**This plan is a reconciliation plan, not a greenfield implementation plan.** Implementing the specs naively (as if nothing exists) would create duplicated logic and conflicting vocabularies. The plan below states, for every feature, what already exists, what conflicts, and what the actual delta is.

The three most important reconciliation findings — any one of which warrants System Owner attention before coding begins — are surfaced here and referenced throughout:

> **R1 — FEAT-008 is ~85% already implemented.** `backtest_service.py` already does causal next-bar-open execution (Pass 2), full Indian cost stack (STT, stamp, SEBI, exchange, GST, DP, brokerage), slippage (3 tiers), position sizing, gross/net dual reporting, and DB persistence (10 columns). **Missing only:** the `LEGACY`/`REALISTIC` execution-model switch (both passes are hardwired to run together), and FEAT-008 naming/branding. The largest single risk (FEAT-008's 25%-weight global shift) is *already live in the codebase* if Pass 2 metrics feed the composite — that question must be answered before any planning assumption holds.

> **R2 — There are already TWO market-regime implementations and the spec is a third.** (a) `MarketPermissionService` ("SR-004", live) classifies FAVORABLE/CAUTIOUS/HIGHRISK/DEFENSIVE via VIX + breadth + trend and downgrades in the orchestrator. (b) `feat004_regime_overlay.py` (the FEAT-004 spec module, complete + tested, but **never wired in** — effectively dead code) classifies FAV/NEU/CAU/DEF via SMA/ROC. (c) FEAT-004's spec. SR-004 and FEAT-004 use **different state vocabularies** and **different inputs** and overlap heavily in intent.

> **R3 — There are already TWO sector-RS implementations with different formulas.** (a) `sector_rs_service.py` ("SR-003", live) computes `sector_rs_20 = sector_roc20 − nifty50_roc20` (a **difference**), classifies WEAK/STRENGTH, and downgrades in the orchestrator. (b) `feat004_regime_overlay.compute_sector_strength` (inert, metadata-only) computes `relative_strength_ratio = sector_roc20 / bm_roc20` (a **ratio**), classifies STRONG/NEUTRAL/WEAK. FEAT-007's spec uses the **ratio** formula. These are not equivalent.

**Implication:** Before Phase 1 begins, the System Owner must make three reconciliation decisions (§4.4). This plan documents the options; it does not pre-decide them, because they change what gets built.

---

## 1. Executive Summary

This document is the engineering execution guide for landing FEAT-004 (Market Regime Overlay), FEAT-007 (Sector Relative Strength), and FEAT-008 (Realistic Trade Execution Model) into the existing brownfield codebase.

The approved IMPLEMENTATION_PLANNING_REVIEW established the canonical order — **FEAT-008 → FEAT-004 → FEAT-007** — on the principle of *stabilize the substrate before tuning the overlays*. That order is reaffirmed here, but every phase is reframed as **reconciliation + completion + wiring**, not greenfield authoring, because the audit proved the codebase is far along under different labels.

| Phase | Feature | True nature of the work | Effort |
| :--- | :--- | :--- | :--- |
| 0 | Prerequisites + reconciliation decisions | Non-code artifacts + 3 System Owner decisions | Small |
| 1 | FEAT-008 | **Complete + wire** the existing realism layer; add the LEGACY/REALISTIC switch; verify which pass feeds the composite | Small–Medium |
| 2 | FEAT-004 | **Wire in** the existing (dead-code) `feat004_regime_overlay`; reconcile with live SR-004; add config + benchmark fetch | Medium |
| 3 | FEAT-007 | **Reconcile** existing SR-003 with the spec's ratio formula; converge or formally document divergence | Small–Medium |

The plan is governed end-to-end by FEAT-006 (lifecycle): each feature traverses Stages 7→17, one feature shadow→active at a time, no parallel activations.

---

## 2. Overall Dependency Graph

### 2.1 Code-level dependencies (as they actually exist)

```
                          ┌──────────────────────────────────────────────┐
                          │   backend/app/services/backtest_service.py    │
                          │   Pass 1 (gross/legacy) + Pass 2 (realistic)  │  ← FEAT-008 lives here
                          │   calculate_transaction_costs()              │
                          │   COST_SCENARIOS, PercentEquityPositionSizer │
                          └──────────────────────────────────────────────┘
                                            │
                                            ▼  backtest_score (which pass? — R1)
                          ┌──────────────────────────────────────────────┐
                          │  recommendation_service.build()              │
                          │  composite = weighted_sum(tech, fund, bt, news)
                          │  → apply_feat004_regime_overlay(...)         │  ← FEAT-004 hook (exists, disabled)
                          └──────────────────────────────────────────────┘
                                            │
                                            ▼  adjusted composite
                          ┌──────────────────────────────────────────────┐
                          │  orchestrator_agent.py                        │
                          │  → _enforce_strict_buy_gate (raw_ta_score)   │  ← Strict Buy Gate (unchanged)
                          │  → SR-003 sector_rs_service (LIVE)           │  ← overlaps FEAT-007
                          │  → SR-004 market_permission_service (LIVE)   │  ← overlaps FEAT-004
                          └──────────────────────────────────────────────┘

  EXISTING (live):   backtest_service realism  ·  SR-003 sector  ·  SR-004 market permission
  EXISTING (dead):   feat004_regime_overlay.py (complete, never wired) · compute_sector_strength (metadata-only)
  MISSING:           LEGACY/REALISTIC switch · feat004 config+benchmark fetch · FEAT-007 ratio wiring · feat007/feat008 naming
```

### 2.2 Specification dependency edges (reaffirmed from PLANNING_REVIEW §5)

```
  FEAT-008 ──(validity)──► FEAT-004 ──(hard code)──► FEAT-007
  (substrate)              (overlay 1)               (overlay 2, consumes compute_sector_strength)
```

The validity edge (FEAT-008 before FEAT-004) is even more important now: if the composite is already fed by Pass-2 realistic metrics, FEAT-004's shadow correlations were computed against an unknown substrate. R1 must be resolved first.

---

## 3. Implementation Order

**Canonical order: FEAT-008 → FEAT-004 → FEAT-007.** Reaffirmed. Reframed per the audit:

| Order | Feature | Reframed objective |
| :--- | :--- | :--- |
| 1st | FEAT-008 | **Resolve R1** (which pass feeds the composite today?), add the LEGACY/REALISTIC switch, brand as FEAT-008, verify the existing realism tests still pass |
| 2nd | FEAT-004 | **Wire in** the existing dead-code overlay; **resolve R2** (converge with SR-004 or document the split); add config + benchmark fetch |
| 3rd | FEAT-007 | **Resolve R3** (converge SR-003 with the spec's ratio, or document the divergence); wire the chosen formula into the spec's score modifier |

---

## 4. Repository Preparation

### 4.1 Branch strategy

| Branch | Purpose | Base | Lifetime |
| :--- | :--- | :--- | :--- |
| `feat-008-realistic-execution` | FEAT-008 reconciliation + switch + branding | `SAI_CHANDRA` (current) | Until Phase 1 exits Stage 16 |
| `feat-004-regime-overlay` | FEAT-004 wiring + SR-004 reconciliation | post-Phase-1 `SAI_CHANDRA` | Until Phase 2 exits Stage 16 |
| `feat-007-sector-rs` | FEAT-007 reconciliation + wiring | post-Phase-2 `SAI_CHANDRA` | Until Phase 3 exits Stage 16 |

One feature per branch. Branches merge sequentially (Phase N+1 branches from the merged Phase N result). No long-lived integration branch; each phase merges to `SAI_CHANDRA` only after its exit criteria pass.

### 4.2 Existing assets to inventory and preserve (do not rewrite)

| Asset | Location | Status | Action |
| :--- | :--- | :--- | :--- |
| Realism two-pass engine | `backtest_service.py:211-498` | Live, tested | Preserve; add switch |
| `calculate_transaction_costs` | `backtest_service.py:58-127` | Live, tested | Preserve as-is |
| `COST_SCENARIOS` (LOW/BASE/STRESS) | `backtest_service.py:19-56` | Live | Preserve; map to spec config |
| `PercentEquityPositionSizer` | `backtest_service.py:156-164` | Live, tested | Preserve |
| Realism migration (10 cols) | `alembic/versions/add_backtest_realism_metrics.py` | Applied | Preserve |
| Realism tests (11) | `app/tests/test_backtest_realism.py` | Passing (assumed) | Preserve; extend |
| `feat004_regime_overlay.py` | `services/feat004_regime_overlay.py` | Complete, dead-code | Wire in (Phase 2) |
| `compute_sector_strength` | inside `feat004_regime_overlay.py` | Metadata-only | Decide formula (Phase 3) |
| `sector_rs_service.py` ("SR-003") | `services/sector_rs_service.py` | Live | Reconcile with FEAT-007 (Phase 3) |
| `market_permission_service.py` ("SR-004") | `services/market_permission_service.py` | Live | Reconcile with FEAT-004 (Phase 2) |
| `sector_mappings.json` | `config/sector_mappings.json` | ~80 symbols, 10 sectors | Preserve; the Phase-0 prerequisite is **already done** |
| `settings.py` | `config/settings.py` | Pydantic BaseSettings | Add feat004/007/008 sections |

### 4.3 Phase-0 prerequisites — revised against actual state

The PLANNING_REVIEW listed five prerequisites. The audit revises four of them:

| Prerequisite | PLANNING_REVIEW assumed | Actual state | Revised action |
| :--- | :--- | :--- | :--- |
| Sector mapping table | Must be authored | **Already exists** (`sector_mappings.json`, ~80 entries) | Review for completeness against NIFTY 500; extend if < 500 coverage |
| Cost schedule verification | Must be verified | **Already modeled** (7 components, intraday/delivery branching) | Verify against current contract note; values exist, may be stale |
| FYERS index/sector instrument support | Must be verified | `NIFTY50-INDEX` **already fetched** by SR-003/SR-004 | Verify `NIFTY500-INDEX` and sector indices specifically |
| Frontend/API forward-compat | Must be verified | Unchanged | Verify nested-key tolerance |
| Log storage capacity | Must be verified | Unchanged | Verify ~3× payload |

**Net:** Phase 0 is smaller than originally planned because the sector mapping and cost schedule already exist. The largest Phase-0 work is now the three reconciliation decisions below.

### 4.4 The three System Owner reconciliation decisions (gate for all phases)

These must be decided and recorded before Phase 1 coding. Each is a design decision, not an implementation detail.

#### Decision D1 — Which backtest pass feeds the composite today, and which should? (resolves R1)

| Question | Why it matters |
| :--- | :--- |
| Does `RecommendationService.build()` receive Pass-1 (gross/legacy) or Pass-2 (realistic) metrics as `backtest_score`? | If Pass-2 already feeds the composite, FEAT-008's "substrate shift" has *already happened* and FEAT-004/007 shadow correlations are already against the realistic substrate. If Pass-1 feeds it, the substrate shift is still ahead. |
| Which should feed it after FEAT-008? | Spec says REALISTIC. Confirm. |

**Options:** (a) Pass 1 today → migrate to Pass 2 (full FEAT-008 per spec); (b) Pass 2 today → FEAT-008 is mostly branding + switch + verification; (c) neither — composite uses a different backtest path not yet examined.

#### Decision D2 — Does FEAT-004 replace, coexist with, or defer to SR-004? (resolves R2)

| Question | Why it matters |
| :--- | :--- |
| SR-004 (`MarketPermissionService`) is live, classifies a market regime, and downgrades BUY→WATCH. FEAT-004 does the same thing with a different formula and vocabulary. Running both double-counts broad-market weakness. | Cannot wire FEAT-004 without deciding its relationship to SR-004. |

**Options:** (a) FEAT-004 **replaces** SR-004 (deprecate SR-004); (b) FEAT-004 and SR-004 **coexist** with formally separated responsibilities (e.g., FEAT-004 = SMA/ROC trend regime score modifier; SR-004 = VIX/volatility permission gate) — requires explicit non-overlap documentation; (c) **defer** FEAT-004 until SR-004 is evaluated.

#### Decision D3 — Does FEAT-007 replace or align with SR-003? (resolves R3)

| Question | Why it matters |
| :--- | :--- |
| SR-003 (`sector_rs_service`) is live and uses `sector_roc20 − nifty50_roc20` (difference). FEAT-007's spec uses `sector_roc20 / bm_roc20` (ratio). These produce different classifications. Running both is incoherent. | The spec's formula and the live formula disagree. |

**Options:** (a) FEAT-007 **replaces** SR-003 (adopt ratio, deprecate SR-003); (b) **align** SR-003 to the ratio formula (migrate the live code); (c) **formally document** the difference as intentional and keep only one.

**Until D1–D3 are decided, the effort estimates and file lists in Phases 1–3 below are best-case (assume "complete + wire", minimal rewrite). If any decision is "replace", add migration + deprecation work to that phase.**

---

## 5. Phase 0 — Prerequisites & Reconciliation

### Goal
Land all non-code prerequisites and record the three reconciliation decisions so Phases 1–3 have unambiguous scope.

### Tasks

| # | Task | Type | Owner |
| :--- | :--- | :--- | :--- |
| 0.1 | Audit which backtest pass feeds `recommendation_service.build()` today (instrument the call or read the data flow). Record finding → informs D1. | Investigation | Implementer |
| 0.2 | Compare SR-004 vs FEAT-004: inputs, states, trigger conditions, downstream effect. Produce a one-page divergence memo → informs D2. | Investigation | Implementer |
| 0.3 | Compare SR-003 vs FEAT-007 formulas on a sample of stocks. Produce a disagreement-rate table (how often do difference-vs-ratio classify differently?) → informs D3. | Investigation | Implementer |
| 0.4 | System Owner records D1, D2, D3 decisions in a decision log (append to this plan or a separate `DECISIONS.md`). | Decision | System Owner |
| 0.5 | Review `sector_mappings.json` coverage vs NIFTY 500; extend to ≥ 500 if coverage is well below. | Data | Implementer |
| 0.6 | Verify cost-schedule values in `COST_SCENARIOS` against a current broker/NSE contract note. | Verification | System Owner |
| 0.7 | Verify FYERS supports `NIFTY500-INDEX` and the 10 sector indices in the mapping. | Verification | Implementer |
| 0.8 | Verify frontend/API forward-compatibility with nested `feat004`/`feat007` keys; verify log storage tolerates ~3× payload. | Verification | Implementer |

### Files expected to change
- `sector_mappings.json` (extend coverage, 0.5)
- A new `DECISIONS.md` or append-only section (0.4)
- No source-code changes

### Validation
- D1–D3 recorded with rationale.
- Mapping coverage reported; cost values confirmed or corrected.

### Exit criteria
- All eight tasks complete.
- D1, D2, D3 recorded. **Phase 1 cannot start without D1.**

---

## 6. Phase 1 — FEAT-008 (Realistic Trade Execution Model)

### Goal
Make the existing realism layer selectable via a `LEGACY`/`REALISTIC` execution-model switch, brand it as FEAT-008, and ensure the composite uses the correct pass per D1.

### Per-phase summary (per required template)

| Attribute | Value |
| :--- | :--- |
| **Files expected to change** | `backend/app/services/backtest_service.py` (add switch); `backend/app/agents/backtest_agent.py` (pass-through param); `backend/app/config/settings.py` (feat008 section); `backend/app/schemas/analysis.py` (expose `feat008_*` fields if persisted); possibly `backend/app/models/analysis.py` if new cols |
| **Classes expected to change** | `BacktestService`, `BacktestAgent`, `Settings` |
| **APIs affected** | `BacktestService.run()` signature gains `execution_model` param (default `LEGACY` for byte-identity); internal only |
| **Database impact** | **Likely none** — the 10 realism columns already exist. If `feat008_execution_model` / `feat008_score_used` need persistence, a small additive migration. |
| **Estimated effort** | **Small–Medium.** Most logic exists. Main work: the switch, default-LEGACY byte-identity verification, branding, config. |
| **Risks** | (i) Discovering Pass 2 already feeds the composite changes the "substrate shift" narrative — handle per D1. (ii) End-of-data `TEMPORARY_ASSUMPTION` close-at-final-close is a residual non-causal edge case (logged) — decide whether to fix or document. (iii) Byte-identity test must prove `LEGACY` reproduces today's *exact* output. |

### Engineering tasks (small, ordered)

| # | Task | Done when |
| :--- | :--- | :--- |
| 1.1 | Add `execution_model: Literal["LEGACY","REALISTIC"]` param to `BacktestService.run()` (default `LEGACY`) and to `BacktestAgent.run()` pass-through. | Signature present; default LEGACY. |
| 1.2 | Route `LEGACY` → return only Pass-1 (gross) metrics as the primary result; `REALISTIC` → return Pass-2 metrics as primary, Pass-1 retained as `legacy_*` for shadow delta. | Both paths return correct shape; existing dual-reporting preserved. |
| 1.3 | Add `feat008` section to `settings.py`: `enabled`, `execution_model`, `composite_uses_realistic`, scenario name (`BASE_COST`). | Config present; defaults = disabled/LEGACY. |
| 1.4 | Implement `composite_uses_realistic` gate at the point where `backtest_score` is selected for the composite (per D1). | Shadow vs active composite selection is one config flag. |
| 1.5 | Write/extend `test_legacy_mode_byte_identical`: with `execution_model = LEGACY`, full scan output byte-identical to pre-Phase-1. | Test passes. |
| 1.6 | Extend realism tests with the FEAT-008 §16.2 cases not already covered (conservative stop-before-target ordering if not present; LEGACY purity; causality guard). | All tests green. |
| 1.7 | Add `feat008_*` log fields to the backtest result payload (model/dict). | Payload complete; absent fields explicitly null. |

### Validation steps (FEAT-006 Stages 8–14)
- **Unit (Stage 8):** existing 11 realism tests + new §16.2 cases.
- **Integration (Stage 9):** `LEGACY` byte-identity (1.5) — the non-negotiable regression gate.
- **Backtest (Stage 10, self-referential):** run full historical scan in LEGACY vs REALISTIC-shadow; compare per FEAT-008 §16.3.
- **Shadow (Stage 14):** `execution_model = REALISTIC`, `composite_uses_realistic = false`, ≥ 30 sessions. Log both metric sets.

### Exit criteria
- LEGACY byte-identity proven.
- D1 substrate question resolved and documented.
- Realistic metrics stable across walk-forward windows.
- System Owner reviews label-distribution shift and approves `composite_uses_realistic = true` (Stage 15).

---

## 7. Phase 2 — FEAT-004 (Market Regime Overlay)

### Goal
Bring the existing dead-code `feat004_regime_overlay.py` into production per D2, with config, benchmark fetch, and wiring through `RecommendationAgent.run → RecommendationService.build`.

### Per-phase summary

| Attribute | Value |
| :--- | :--- |
| **Files expected to change** | `backend/app/agents/recommendation_agent.py` (forward feat004 kwargs), `backend/app/agents/orchestrator_agent.py` (fetch benchmark OHLCV, build feat004_config, reconcile with SR-004 per D2), `backend/app/config/settings.py` (feat004 section), `backend/app/schemas/analysis.py` (expose `feat004` on `StockAnalysisResult`/`FinalRecommendation`), possibly `backend/app/models/analysis.py` (FEAT-004 persistence cols if desired) |
| **Classes expected to change** | `RecommendationAgent`, `OrchestratorAgent` (or equivalent), `Settings`, schema classes |
| **APIs affected** | `RecommendationAgent.run()` must forward `feat004_config`, `benchmark_ohlcv`, `sector_mapping`, `sector_ohlcv_cache` (currently dropped). New helper: benchmark OHLCV fetch once per session. |
| **Database impact** | Optional additive migration for FEAT-004 log persistence (`market_regime_state`, `bm_roc20`, etc.) on `AnalysisHistory`. **Not required for shadow** — in-flight dict suffices. |
| **Estimated effort** | **Medium.** The overlay module exists and is tested. Work is wiring + config + benchmark fetch + SR-004 reconciliation (D2). |
| **Risks** | (i) D2 unresolved → double-counting with SR-004. (ii) Benchmark fetch must run once per session, not per stock (perf). (iii) `RecommendationAgent.run` currently drops the kwargs — easy to miss in review. (iv) FEAT-004 is Level C → activation-blocked until promoted to B (shadow correlations + independent review). |

### Engineering tasks

| # | Task | Done when |
| :--- | :--- | :--- |
| 2.1 | Resolve D2; if "replace SR-004", produce a deprecation plan; if "coexist", document the non-overlap boundary. | Decision recorded; SR-004 path handled. |
| 2.2 | Add `feat004` section to `settings.py`: `enabled`, `stage`, `benchmark_symbols`, `score_deltas`, `buy_downgrade_thresholds`, `sector_mapping_enabled`. | Config present; defaults = disabled/SHADOW. |
| 2.3 | Implement session-level benchmark OHLCV fetch (reuse the FYERS path already used for `NIFTY50-INDEX` in SR-003/SR-004). Fetch once, pass into the agent. | Benchmark df available per session; ABSTAINED on failure. |
| 2.4 | Wire `RecommendationAgent.run()` to forward `feat004_config`, `benchmark_ohlcv`, `sector_mapping`, `sector_ohlcv_cache` to `RecommendationService.build()`. | Kwargs no longer dropped. |
| 2.5 | Build `sector_ohlcv_cache` per session (one fetch per sector in the mapping) for `compute_sector_strength`. | Cache built once per session; ABSTAINED on failure. |
| 2.6 | Run the existing FEAT-004 unit suite (in `feat004_regime_overlay` tests); add integration tests for the wiring. | All green; disabled-feature byte-identity holds. |
| 2.7 | Add `feat004` field to `StockAnalysisResult` / `FinalRecommendation` schemas so the log propagates to the API. | API returns the nested payload. |

### Validation steps (FEAT-006 Stages 8–16)
- **Unit (Stage 8):** existing `feat004_regime_overlay` tests + new wiring tests.
- **Integration (Stage 9):** `feat004.enabled = false` → byte-identical to post-Phase-1 output.
- **Backtest (Stage 10):** baseline vs treatment (Stage B ACTIVE) against the **Phase-1 realistic composite**, per FEAT-004 §9 split.
- **Shadow (Stage 14):** ≥ 30 sessions, zero score effect; validate regime distribution (≥ 3 of FAV/NEU/CAU/DEF fire).
- **Evidence promotion (Stage 15 gate):** C → B via shadow correlations + independent review (FEAT-005 §9.2). **Activation blocked until promoted.**

### Exit criteria
- D2 resolved and documented.
- Overlay wired, benchmark fetch working, shadow validates.
- Level promoted C → B; System Owner approves activation.

---

## 8. Phase 3 — FEAT-007 (Sector Relative Strength)

### Goal
Converge the live SR-003 and the spec's ratio formula per D3, and wire the chosen formula into the FEAT-007 score modifier (STRONG/NEUTRAL/WEAK + STRONG cap + WEAK soft penalty + REJECT immutability + UNKNOWN no-op).

### Per-phase summary

| Attribute | Value |
| :--- | :--- |
| **Files expected to change** | `backend/app/services/sector_rs_service.py` (or a new `feat007` module if "replace"), `backend/app/agents/orchestrator_agent.py` (reconcile the challenger-downgrade path with the spec's score-modifier path), `backend/app/config/settings.py` (feat007 section), `backend/app/schemas/analysis.py` (`feat007` field) |
| **Classes expected to change** | `SectorRelativeStrengthService` (or successor), orchestrator, `Settings`, schemas |
| **APIs affected** | Sector evaluation API; the orchestrator's challenger-downgrade call site |
| **Database impact** | SR-003 columns already exist on `AnalysisHistory` (`mapped_sector`, `sector_rs_20`, etc.). Reuse or extend; likely no migration. |
| **Estimated effort** | **Small–Medium.** Sector logic exists and is live. Work is formula convergence (D3) + aligning the downgrade mechanism (orchestrator challenger vs spec's in-build modifier). |
| **Risks** | (i) D3 unresolved → two formulas coexist. (ii) SR-003 downgrades *after* the Strict Buy Gate as a "challenger"; FEAT-007's spec modifies the composite *before* the Gate. This is a structural placement difference that must be reconciled — it affects which score the Gate sees. (iii) Benchmark hardcoded to `NIFTY50-INDEX` in SR-003; spec prefers `NIFTY500`. |

### Engineering tasks

| # | Task | Done when |
| :--- | :--- | :--- |
| 3.1 | Resolve D3: adopt ratio (replace SR-003) or align SR-003 to ratio or document divergence. | Decision recorded. |
| 3.2 | Resolve the **placement conflict**: SR-003 acts post-Gate as a challenger; FEAT-007 acts pre-Gate on the composite. Decide one. (Recommendation: align to the spec — pre-Gate composite modifier — to match FEAT-004's pattern and keep both overlays symmetric.) | Decision recorded; call site moved or confirmed. |
| 3.3 | Implement the FEAT-007 score modifier per spec §9.3 (composite → FEAT-004 → FEAT-007 → Gate) with STRONG cap, WEAK penalty, REJECT immutability, UNKNOWN no-op. | Modifier behaves per §9.5 numeric examples. |
| 3.4 | Make the benchmark configurable (`NIFTY500` primary, `NIFTY50` fallback) rather than hardcoded. | Benchmark from config. |
| 3.5 | Add `feat007` section to `settings.py` (enabled, score deltas, downgrade threshold). | Config present; default disabled. |
| 3.6 | Unit tests per FEAT-007 §15.2 (14 tests) + cross-feature: `feat004 disabled → feat007 abstains`. | All green. |

### Validation steps
- **Unit (Stage 8):** FEAT-007 §15.2 suite + cross-feature abstention test.
- **Integration (Stage 9):** `feat007.enabled = false` → byte-identical to post-Phase-2.
- **Backtest (Stage 10):** baseline vs treatment against the full Phase-1+2 stack.
- **Shadow (Stage 14):** ≥ 30 sessions; validate STRONG/NEUTRAL/WEAK distribution.
- **Activation (Stage 15):** FEAT-007 is Level B → activation-eligible once shadow validates.

### Exit criteria
- D3 resolved and documented.
- Placement conflict resolved; modifier wired per spec ordering.
- Shadow validates; System Owner approves activation.

---

## 9. Cross-Feature Integration Tasks

These run at the end of Phase 3 but are designed throughout. Each is a test, not a feature.

| # | Test | Proves |
| :--- | :--- | :--- |
| X.1 | `feat008 LEGACY + feat004 disabled + feat007 disabled` → byte-identical to today | Full rollback safety |
| X.2 | `feat008 REALISTIC + feat004 ACTIVE + feat007 ACTIVE` → no exception propagates | Full-stack composition |
| X.3 | `feat004 disabled → feat007 abstains (UNKNOWN, zero delta)` | Clean upstream degradation |
| X.4 | `raw_technical_score` passed to Strict Buy Gate is unchanged under full stack | Gate isolation invariant |
| X.5 | Combined FEAT-004 + FEAT-007 penalty in CAU-regime + WEAK-sector does not exceed a documented bound | No runaway double-penalty |
| X.6 | SR-003/SR-004 (if retained per D2/D3) do not double-fire with FEAT-004/007 | Reconciliation held |

---

## 10. Feature Flags

| Flag | Default | Effect |
| :--- | :--- | :--- |
| `feat008.enabled` | `true` | Master switch for realism layer |
| `feat008.execution_model` | `LEGACY` | `LEGACY` = Pass-1 only (byte-identical to today); `REALISTIC` = Pass-2 primary |
| `feat008.composite_uses_realistic` | `false` | `false` = composite uses legacy (shadow); `true` = composite uses realistic (active) |
| `feat008.cost_scenario` | `BASE_COST` | Selects from existing `COST_SCENARIOS` |
| `feat004.enabled` | `false` | Master switch for regime overlay |
| `feat004.stage` | `SHADOW` | `SHADOW` = log only; `ACTIVE` = score effect on |
| `feat004.sector_mapping_enabled` | `true` | Gates `compute_sector_strength` (and therefore FEAT-007's input) |
| `feat007.enabled` | `false` | Master switch for sector RS overlay |

**Cascade rule (must be in ops runbook):** `feat004.enabled = false` or `feat004.sector_mapping_enabled = false` → FEAT-007 silently abstains. This is designed behavior, not a bug.

---

## 11. Configuration Management

All config lives in `backend/app/config/settings.py` (Pydantic `BaseSettings`, `.env`-backed). Add three sections (`feat004`, `feat007`, `feat008`) as nested config models. No new config framework.

**Config precedence:** `.env` overrides → settings defaults. All feature flags default to *disabled or LEGACY/SHADOW* so a fresh deploy never activates a feature unintentionally.

**Config review checkpoint:** before each Stage 15 activation, the System Owner reviews the effective config (dumped from the running settings) and signs off. No activation by config drift.

---

## 12. Database Migration Plan

| Phase | Migration needed? | Detail |
| :--- | :--- | :--- |
| Phase 1 (FEAT-008) | **Likely none.** The 10 realism columns already exist (`add_backtest_realism_metrics`). If `feat008_execution_model` / `feat008_score_used` must persist, a small additive migration on `backtest_history`. | Idempotent add only |
| Phase 2 (FEAT-004) | **Optional.** Shadow can run with in-flight dict only. If persistence is desired, add `market_regime_state`, `bm_roc20`, `feat004_score_adjustment` etc. to `AnalysisHistory`. | Additive, idempotent |
| Phase 3 (FEAT-007) | **Likely none.** SR-003 columns already exist. Reuse or extend. | — |

**Migration discipline:** every migration must be idempotent (check-before-add, as the existing realism migration does) and must have a tested downgrade. No destructive changes. No migration lands without a paired test.

---

## 13. Logging Plan

| Feature | Payload | Where |
| :--- | :--- | :--- |
| FEAT-008 | ~15 fields per stock (§12.2 of spec) | backtest result dict + session log |
| FEAT-004 | ~18 fields per stock incl. nested `benchmark_trend_inputs` | recommendation dict + session log |
| FEAT-007 | ~12 fields per stock | recommendation dict + session log |

**Capacity:** ~3× per-recommendation payload growth once all three are active. Verify log rotation/storage in Phase 0 (task 0.8).

**Schema convention:** every field written on every stock; absent values explicitly `null`, never omitted. Payload shape mirrors FEAT-004 §8 so monitoring tooling consumes all three uniformly.

---

## 14. Metrics Plan

Metrics are the Stage 16 (Production Monitoring) rollback triggers. Each feature defines its own; the combined set is monitored together.

| Feature | Metric | Rollback trigger |
| :--- | :--- | :--- |
| FEAT-008 | Label-distribution shift (BUY/WATCH/REJECT counts) post-activation | Unreviewed shift → revert `composite_uses_realistic` |
| FEAT-008 | Mean backtest P&L reduction (realistic vs legacy) | ≤ 0 → cost config wrong |
| FEAT-004 | False-positive reduction in CAU/DEF regimes | < 5% → re-tune deltas |
| FEAT-004 | Missed-winner rate | > 8% → rollback to SHADOW |
| FEAT-004 | Profit factor vs baseline | Drops > 10% → rollback |
| FEAT-007 | False-positive reduction in WEAK sectors | < 5% → re-tune |
| FEAT-007 | Missed-winner rate in STRONG sectors | > 8% → rollback |
| Cross | Combined penalty in CAU + WEAK | Exceeds documented bound → investigate |

---

## 15. Testing Strategy

### 15.1 Layers (per feature, per FEAT-006)

| Layer | Stage | Gate |
| :--- | :--- | :--- |
| Unit | 8 | All deterministic; fixed in/out |
| Integration | 9 | **Disabled-feature byte-identity** (non-negotiable) |
| Historical backtest | 10 | Baseline vs treatment; shared data split (FEAT-004 §9) |
| Walk-forward | 11 | Out-of-sample, ≥ 2 regimes |
| Paper trading | 12 | Simulated (FEAT-008's analogue = score-delta audit) |
| Shadow | 14 | ≥ 30 sessions, zero score effect |
| Activation | 15 | First-session metrics within bounds |
| Monitoring | 16 | Ongoing, against §14 triggers |

### 15.2 Shared regression test (the one that must never fail)

For each feature: with the feature disabled, the full scan output is byte-for-byte identical to the pre-feature output. Verified at Stage 9 of every phase. This is the guarantee that rollback is real.

### 15.3 Existing tests to preserve (do not rewrite)

| Suite | Location | Preserve |
| :--- | :--- | :--- |
| Backtest realism (11 tests) | `app/tests/test_backtest_realism.py` | Yes — extend, don't replace |
| FEAT-004 overlay unit tests | alongside `feat004_regime_overlay.py` | Yes |
| SR-003 / SR-004 tests | (locate in Phase 0) | Yes if their features are retained per D2/D3 |

### 15.4 Cross-feature integration tests

Per §9 (X.1–X.6). Added at end of Phase 3.

---

## 16. Rollback Strategy

| Feature | Primary rollback | Softer rollback | Restore guarantee |
| :--- | :--- | :--- | :--- |
| FEAT-008 | `execution_model = LEGACY` | `composite_uses_realistic = false` | Byte-identical (Stage 9 verified) |
| FEAT-004 | `feat004.enabled = false` | `feat004.stage = SHADOW` | Byte-identical |
| FEAT-007 | `feat007.enabled = false` | — | Byte-identical |

**Cascade:** rolling back FEAT-004 auto-degrades FEAT-007 to abstention. Rolling back FEAT-008 does not change FEAT-004/007 code, but invalidates their shadow correlations (computed against the restored legacy composite) → re-validation required.

---

## 17. Deployment Strategy

- **No parallel activations.** One feature shadow→active at a time.
- **Config-first deploy.** Code lands disabled; activation is a config flip after shadow validation.
- **Environment:** deploy to the existing backend environment; verify the frontend tolerates nested keys before any feature reaches shadow (Phase 0, task 0.8).
- **Sign-off gate:** each Stage 15 activation requires System Owner review of (i) effective config, (ii) shadow report, (iii) label-distribution shift, (iv) evidence level (FEAT-004 must be promoted C → B first).

---

## 18. Post-Deployment Validation

After Phase 3 exit, run a 30-session stability window with all three features active:

| Check | Target |
| :--- | :--- |
| No exception propagates to recommendation path | 0 events |
| Strict Buy Gate input (`raw_technical_score`) unchanged under full stack | Verified |
| Combined overlay behavior matches backtested expectation | No unexplained divergence |
| Log payload complete on every stock | No missing fields |
| Rollback drill: flip each flag to disabled, confirm byte-identity | Each drill passes |
| FEAT-004 + FEAT-007 combined penalty stays within documented bound | No runaway |

Any failure → rollback the offending feature per §16 and re-enter its lifecycle at the stage named in FEAT-006 §9.

---

## 19. Completion Checklist

- [ ] **Phase 0:** D1, D2, D3 recorded; sector mapping coverage ≥ target; cost values verified; FYERS instruments verified; frontend/log capacity verified.
- [ ] **Phase 1 (FEAT-008):** switch implemented; LEGACY byte-identity proven; D1 substrate resolved; realism tests green; shadow ≥ 30 sessions; `composite_uses_realistic` activated with System Owner sign-off.
- [ ] **Phase 2 (FEAT-004):** D2 resolved; overlay wired; benchmark fetch working; unit + integration green; shadow ≥ 30 sessions; evidence promoted C → B; activated.
- [ ] **Phase 3 (FEAT-007):** D3 resolved; placement conflict resolved; modifier wired per spec ordering; benchmark configurable; unit + cross-feature green; shadow ≥ 30 sessions; activated.
- [ ] **Cross-feature (§9):** X.1–X.6 all green.
- [ ] **Post-deploy (§18):** 30-session stability window clean; rollback drill passes for all three flags.

---

## 20. Final Notes & Honest Caveats

1. **This plan differs from a greenfield plan.** The audit proved the codebase already contains ~85% of FEAT-008, a complete-but-unwired FEAT-004, a live SR-003 that overlaps FEAT-007, and a live SR-004 that overlaps FEAT-004. The plan above is reconciliation-first. A greenfield plan would have duplicated working logic.

2. **The three reconciliation decisions (D1–D3) are the real critical path**, not the coding tasks. Until D1 is answered, FEAT-008's scope is unknown (it ranges from "branding + switch" to "migrate the composite to a new pass"). Until D2/D3 are answered, FEAT-004/007 risk creating a second parallel regime/sector logic alongside the live SR-003/SR-004.

3. **The FEAT-004 vs SR-004 overlap (R2) is the highest-impact unresolved question.** Two market-regime classifiers with different vocabularies both downgrading BUY→WATCH is a correctness hazard. D2 must not be deferred.

4. **The placement conflict in Phase 3 (SR-003 acts post-Gate as a challenger; FEAT-007's spec acts pre-Gate on the composite) is a structural decision**, not a tuning decision. It changes which score the Strict Buy Gate sees. Task 3.2 flags it; the System Owner should decide it alongside D3.

5. **This plan does not write code, redesign features, or create FEAT-009.** It converts the approved specifications into an engineering execution guide that respects the codebase as it actually is.

---

*End of IMPLEMENTATION_MASTER_PLAN v1.0*
