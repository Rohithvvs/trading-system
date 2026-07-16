# ADR-001 — Backtest Execution Model

**Status:** Proposed — awaiting System Owner decision
**Date:** 2026-07-11
**Decides:** The relationship between the existing two-pass backtest engine and the FEAT-008 specification
**Supersedes:** None
**Blocks:** IMPLEMENTATION_MASTER_PLAN Phase 1

---

## 1. Context

The FEAT-008 specification ("Realistic Trade Execution Model") mandates a `LEGACY`/`REALISTIC` execution-model switch that replaces optimistic same-candle-close fills with causal next-bar-open execution plus slippage, brokerage, and statutory charges. The specification was written against the *architectural description* in FEAT-001 §8 Gaps #11–#14, which states the backtest "assumes same-candle close execution" with "no slippage" and "no fees."

A codebase audit (2026-07-11) has now established that this description is **stale**. The engine already implements the majority of what FEAT-008 specifies, under different internal naming and with no selectable switch. This ADR decides how to reconcile the existing implementation with the specification.

The decision is consequential because the BacktestAgent feeds **25 % (standard regime) / 20 % (catalyst regime)** of the composite score (FEAT-001 §4). Any change to which backtest metric feeds the composite is a global shift affecting every recommendation.

---

## 2. Existing Implementation

The engine in `backend/app/services/backtest_service.py` runs **two passes every time**, hardwired, with no caller-selectable switch:

### Pass 1 — "Gross / legacy" baseline (`backtest_service.py:211–299`)
- **Entry fill:** `close[T]` (line 240) — same-candle close. **Non-causal.**
- **Exit fill:** `close[T]` (line 244) — same-candle close. **Non-causal.**
- **Costs:** none. **Position sizing:** 100 % equity deployment.
- **Purpose:** retained as a "gross" baseline for comparison.
- **Reported via:** `gross_total_return`, `gross_cagr`, `gross_max_drawdown`, `gross_win_rate`, `gross_profit_factor`, `gross_sharpe_ratio` on `BacktestResult`.

### Pass 2 — "Net / realistic" challenger (`backtest_service.py:302–498`)
- **Entry fill:** `open[T+1]` via a `pending_buy` flag executed at the *start* of the next iteration (line 337). **Causal.**
- **Exit fill:** `open[T+1]` via a `pending_exit` flag (line 370). **Causal.**
- **Slippage:** symmetric multiplier on the open price — buy `×(1+rate)`, sell `×(1−rate)` (lines 341, 374), accumulated into `total_slippage`.
- **Costs:** full Indian stack via `calculate_transaction_costs` (lines 58–127): brokerage (with optional flat cap), STT (intraday vs delivery), exchange transaction charges, SEBI, stamp duty (buy-only), GST (18 % on brokerage+etc+sebi), DP charge (₹13.5, sell-side delivery).
- **Position sizing:** `PercentEquityPositionSizer` (fractional deployment).
- **Residual non-causal edge case:** a position still open at end-of-data is force-closed at `final_row["close"]` with a `TEMPORARY_ASSUMPTION` warning log (lines 458–498).

### Which pass feeds the composite (the load-bearing fact)

`orchestrator_agent.py:566`:
```python
best_backtest = max(backtests, key=lambda item: item.total_return)
```
`orchestrator_agent.py:705`:
```python
backtest_score=backtest.total_return,
```

The composite's backtest weight is fed by `total_return` — the **Pass-2 realistic (net) metric**, *not* `gross_total_return` (Pass 1). The gross baseline is persisted to the database (`orchestrator_agent.py:738–747`) but does **not** feed the recommendation.

**Conclusion: the FEAT-008 "substrate shift" has already happened.** The composite already runs on realistic, cost-aware, causal metrics. Gaps #11–#14 are substantially closed in production today.

### What does not exist
- No `execution_model` parameter, enum, or runtime switch anywhere in `backend/app/`.
- No way for a caller to select Pass 1 only, Pass 2 only, or both.
- The tokens `feat008`, `realistic`, `legacy` (in the backtest sense) appear nowhere as identifiers.

### What already exists (preserved assets)
- 11 realism unit tests in `app/tests/test_backtest_realism.py` (next-bar execution, costs, slippage, sizing, retro-fee logic, drawdown consistency).
- Alembic migration `add_backtest_realism_metrics` adding 10 nullable columns to `backtest_history` (applied).
- `COST_SCENARIOS`: `LOW_COST`, `BASE_COST`, `STRESS_COST` (each with full bps config).
- `PercentEquityPositionSizer`.

---

## 3. Proposed Implementation

Four candidate implementations are evaluated in §11. The specification's literal proposal (the FEAT-008 §13 config: `execution_model ∈ {LEGACY, REALISTIC}` + `composite_uses_realistic` flag) is one of them. This section describes the *specification's* proposed shape for reference; alternatives follow in §11.

- Add `execution_model: Literal["LEGACY","REALISTIC"]` to `BacktestService.run()` (default `LEGACY`).
- Add a `composite_uses_realistic` flag selecting whether `total_return` (Pass 2) or `gross_total_return` (Pass 1) feeds the composite.
- Brand the existing realism layer as FEAT-008; preserve all existing tests.

---

## 4. Technical Differences (Spec vs. Existing Code)

| Aspect | FEAT-008 specification | Existing code | Gap |
| :--- | :--- | :--- | :--- |
| Causal next-bar entry | Required (`open[T+1]`) | **Present** (Pass 2, pending-order state machine) | None |
| Causal next-bar exit | Required (`open[T+1]`) | **Present** (Pass 2) | None |
| Conservative stop-before-target intrabar ordering | Required (§9.3) | **Not verified** — must confirm the pending-exit logic handles intrabar stop/target ordering conservatively | Possible gap |
| Slippage model | Flat `slippage_bps` per side | **Present** — 3 tiers (0.02 % / 0.05 % / 0.15 %) via `COST_SCENARIOS` | None (different parametrization, equivalent effect) |
| Brokerage | Flat `brokerage_bps` | **Present** — % with optional flat ₹ cap | None |
| Statutory charges | Aggregated `statutory_bps` | **Present, more granular** — STT, stamp, SEBI, exchange, GST, DP modelled individually with intraday/delivery branching | None (existing is richer) |
| `LEGACY`/`REALISTIC` switch | Required | **Absent** — both passes hardwired | Gap |
| `composite_uses_realistic` flag | Required | **Implicitly always true** — composite reads `total_return` (Pass 2) | Gap (no switch, no shadow mode) |
| End-of-data open position | Not specified | Force-closed at `close[T]` (`TEMPORARY_ASSUMPTION`) | Residual non-causal edge case |
| FEAT-008 naming | Required | Absent | Cosmetic gap |

**The honest summary:** the realism logic is ~85 % present. The missing 15 % is the *selectability and shadow-mode infrastructure*, not the realism math. Critically, the composite already uses the realistic metric — so FEAT-008's "shadow then activate" lifecycle cannot be exercised naively: there is no legacy composite to shadow against, because the legacy metric (`gross_total_return`) is persisted but never used for scoring.

---

## 5. Advantages of the Existing Implementation

- Realism math is built, tested, and **already live** in the scoring path.
- Cost model is richer than the spec (per-component Indian charges, intraday/delivery branching).
- DB persistence already exists (10 columns, migrated).
- 11-test suite already validates next-bar execution, costs, slippage.

## 6. Disadvantages of the Existing Implementation

- No selectability: cannot run legacy-only or realistic-only; cannot shadow.
- No FEAT-008 naming → traceability gap; the feature is invisible in the codebase.
- The end-of-data `TEMPORARY_ASSUMPTION` close-at-`close[T]` is a residual non-causal edge case.
- The spec's "conservative stop-before-target ordering" is unverified in the pending-exit logic.

---

## 7. Recommendation

**Option B — Brand, switch, and verify** (see §11). Adopt the existing two-pass engine as the FEAT-008 implementation; add the `LEGACY`/`REALISTIC` switch; default `execution_model = REALISTIC` (not LEGACY) because the composite *already* uses the realistic metric — defaulting to LEGACY would be a silent behaviour change; brand and document it; verify the conservative-ordering and end-of-data edge cases; skip the spec's shadow-against-legacy phase (or implement it as a *log-only* gross-vs-net delta, since both metrics are already computed).

Rationale: the realism work is done and live. The honest engineering task is to make it selectable, named, and auditable — not to rebuild it. Defaulting the switch to LEGACY (as the spec's §13 suggests) would *change* current production behaviour (composite would flip from realistic to legacy), which is the opposite of brownfield safety.

---

## 8. Migration Strategy

1. Add `execution_model` param to `BacktestService.run()` and `BacktestAgent.run()` (default `REALISTIC`, preserving today's behaviour).
2. Add `composite_uses_realistic` flag, defaulting `true` (preserving today's behaviour).
3. Add FEAT-008 config section to `settings.py`.
4. Verify the conservative intrabar stop/target ordering; if absent, add it behind `conservative_exit_ordering = true`.
5. Decide and document the end-of-data `TEMPORARY_ASSUMPTION` edge case (fix or accept).
6. Extend the realism test suite with FEAT-008 §16.2 cases.
7. No DB migration (columns exist).

Because today's behaviour is `REALISTIC + composite_uses_realistic = true`, the migration is **behaviour-preserving by default**. The flags exist to *enable* shadow/rollback, not to change current behaviour.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| Defaulting the switch to LEGACY silently flips the composite to gross metrics | High if Option A/spec-literal is chosen | High (global score shift) | Default to REALISTIC; add a byte-identity test asserting `total_return` still feeds the composite |
| Conservative stop/target ordering is not actually implemented | Medium | Medium (asymmetric exit bias) | Verify; add behind flag |
| End-of-data `TEMPORARY_ASSUMPTION` inflates a few trades | Low | Low | Audit the warning log volume; fix if material |
| Re-building realism logic that already exists (Option B-spec-literal misread) | Medium | High (wasted effort, regressions) | This ADR |

---

## 10. Rollback Strategy

- The existing engine has run for some time; "rollback" to a pre-FEAT-008 state is not meaningful.
- Within the new switch: `execution_model = REALISTIC` + `composite_uses_realistic = true` reproduces today's behaviour exactly.
- If a regression is introduced by the switch plumbing, revert the plumbing commit; the underlying engine is unchanged.

---

## 11. Final Decision Options

### Option A — Keep existing implementation as-is (no switch, no branding)

The realism layer is live and working; treat Gaps #11–#14 as already closed and FEAT-008 as "already delivered." Add only documentation.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Neutral — no change |
| Brownfield safety | High — nothing changes |
| Determinism | High — unchanged |
| Explainability | Low — no FEAT-008 naming, no observability of gross-vs-net in scoring |
| Implementation complexity | Trivial |
| Regression risk | None |
| Technical debt | **High** — feature is invisible; no selectability; future shadow/rollback impossible |
| Long-term maintainability | Low |

### Option B — Brand, switch, and verify (RECOMMENDED)

Adopt the existing engine as FEAT-008. Add `execution_model` (default `REALISTIC`) and `composite_uses_realistic` (default `true`). Add naming, config, and the missing conservative-ordering/edge-case verification. Keep both passes running.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Neutral-to-positive — no behaviour change, but gains auditability |
| Brownfield safety | High — defaults preserve today's behaviour |
| Determinism | High |
| Explainability | High — gross-vs-net delta observable; FEAT-008 named in code |
| Implementation complexity | Low — small plumbing delta on existing engine |
| Regression risk | Low — byte-identity test guards the composite input |
| Technical debt | Low — closes the traceability/selectability gap |
| Long-term maintainability | High |

### Option C — Replace with the spec's literal LEGACY-default switch

Implement FEAT-008 §13 verbatim: default `execution_model = LEGACY`, `composite_uses_realistic = false`, then shadow-then-activate. This requires *flipping the composite back to legacy* first, shadowing the realistic metric, then re-activating it.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Neutral |
| Brownfield safety | **Low** — defaults *change* production behaviour (composite flips realistic→legacy on deploy) |
| Determinism | High |
| Explainability | High — full shadow/active lifecycle |
| Implementation complexity | Medium — plumbing + a shadow cycle against a substrate that was never used for scoring |
| Regression risk | **High** — the flip to legacy is a global score shift with no prior shadow baseline |
| Technical debt | Low |
| Long-term maintainability | Medium — the shadow-against-legacy exercise is partly theatre since realistic is already proven in production |

### Option D — Merge: dual-report always, selectable composite source

Always run both passes (as today), but make the *composite source* selectable and add a shadow mode that logs both while the composite reads one. This is Option B with a richer shadow facility.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Positive — enables true A/B between gross and net |
| Brownfield safety | High — defaults preserve behaviour |
| Determinism | High |
| Explainability | Highest — both metrics always visible |
| Implementation complexity | Medium |
| Regression risk | Low |
| Technical debt | Low |
| Long-term maintainability | High |

**Recommended: Option B** (with Option D's shadow facility as a follow-on if the owner wants gross-vs-net A/B observability). Option B is the only option that is both brownfield-safe (defaults preserve today's behaviour) and closes the traceability gap without risky score shifts. Option C is explicitly discouraged because its defaults would silently change production scoring.

---

*End of ADR-001 — proposed, not final.*
