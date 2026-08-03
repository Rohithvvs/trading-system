# Quickstart Validation Guide: RE-001 Integration

**Feature**: `029-re001-trend-continuation`  
**Date**: 2026-08-03  
**Purpose**: Runnable validation scenarios for implementers after coding. No implementation code here.

**Related**: [spec.md](./spec.md) · [plan.md](./plan.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/)

---

## Prerequisites

1. Application boots with database migrations applied (including decisions table when implemented).
2. RE-001 defaults **OFF** (`re001_enabled=false` / `re001_stage=OFF`).
3. Ability to run backend test suite and perform a shortlist-producing scan (or fixture-based scan).
4. Authenticated Admin and Trader test users; feature key **`recommendation_lab`** configurable.
5. Baseline regression suites green **before** enabling RE-001.

## Ops: stages and env (canonical)

| Setting | Values | Notes |
| ------- | ------ | ----- |
| `RE001_ENABLED` / `re001_enabled` | true/false | Master switch |
| `RE001_STAGE` / `re001_stage` | `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` | `ACTIVE` reserved |
| Feature permission | `recommendation_lab` | Admin + Trader when active |

`LAB_SHADOW` and `PAPER_LINKED` both evaluate+persist when enabled; `PAPER_LINKED` marks intentional paper-validation mode.

---

## Scenario A — Production invariance (SC-001, FR-002)

**Setup**
1. Capture production shortlist + BUY/WATCH labels with RE-001 **OFF** (control).
2. Enable RE-001 `LAB_SHADOW` with same market snapshot / fixtures.
3. Re-run analysis/scan.

**Expected**
- Production labels and shortlist membership **identical** to control.
- RE-001 Decision Objects exist for shortlisted symbols when evaluation succeeds or rules-reject.
- Scan does not fail solely because RE-001 errored on a symbol.

**Fail if**
- Any production action/score/shortlist membership changes solely due to RE-001 enablement.

---

## Scenario B — Missing market context (FR-025)

**Setup**
1. Force missing/unusable regime inputs for one shortlisted symbol (fixture).
2. Enable RE-001 lab mode.
3. Evaluate.

**Expected**
- Decision Object persisted with `recommendation_state = REJECT`.
- Reason code includes `missing_market_context` (or equivalent).
- No BUY.
- Production path for that symbol still succeeds.

---

## Scenario C — Shortlist-only evaluation (FR-017)

**Setup**
1. Produce a scan with matched symbols beyond shortlist top-N.
2. Enable RE-001.
3. Inspect decisions table / lab API.

**Expected**
- Decisions only for shortlist / full-analysis symbols.
- Zero RE-001 decisions for non-shortlisted matched symbols.

---

## Scenario D — Flag OFF zero artefacts (SC-007)

**Setup**
1. With RE-001 previously enabled, set OFF.
2. Run a new scan.

**Expected**
- No **new** RE-001 Decision Objects for that run.
- Lab UI empty/disabled for new data.

---

## Scenario E — Lab UI hybrid (SC-002, SC-004, FR-014)

**Setup**
1. Enable RE-001 + lab feature permission for Trader.
2. Complete a scan with at least one RE-001 BUY and one REJECT.
3. Open symbol detail and compact Lab comparison.

**Expected**
- Detail shows state, strategy, evidence, production comparison.
- Lab comparison lists shortlist production vs RE-001 within interactive review (< 2 minutes).
- Surfaces labeled Lab/Experimental.

**Permission check**
- Without feature permission: lab surfaces denied/hidden.
- Unauthenticated: denied.

---

## Scenario F — Paper provenance (SC-005, FR-015)

**Setup**
1. Select RE-001 BUY decision.
2. Prefill / create paper ticket from that decision.

**Expected**
- Trade levels: RE-001 `trade_guidance` when complete; else production trade_plans for same symbol/scan.
- Provenance retains `RE-001`, version, recommendation_id.
- Paper order lifecycle still works (fill path unchanged).

---

## Scenario G — Analytics dimension (FR-016)

**Setup**
1. Accumulate several RE-001 decisions across states.
2. Query RE-001 health metrics for rolling window.

**Expected**
- Counts by BUY/WATCH/REJECT available for RE-001.
- Production engine-health aggregates still make sense (regression).

---

## Scenario H — Isolation under failure (FR-012, SC-003)

**Setup**
1. Inject RE-001 timeout or exception for one symbol.
2. Complete scan.

**Expected**
- Production result present and scan completes.
- Failure logged/countable; no false BUY from failed evaluation.
- Engineering gate for SC-003 satisfied (no production failure attributable to RE-001).

## Scenario I — Portfolio context unavailable (FR-026)

**Setup**
1. Evaluate RE-001 without user portfolio/risk snapshot (scheduler-style or stripped context).
2. Use a setup that would otherwise be BUY-eligible.

**Expected**
- RecommendationState is WATCH or REJECT (not BUY).
- Reason code includes `portfolio_context_unavailable`.

## Scenario J — Scheduler / daily-scan path (FR-017)

**Setup**
1. Enable RE-001 `LAB_SHADOW`.
2. Trigger the existing daily-scan / scheduler entrypoint that runs the analysis pipeline (or its test double).

**Expected**
- RE-001 decisions are written for shortlisted symbols without a separate manual batch.
- Production shortlist authority unchanged.

## Scenario K — SC-006 regime ratio

**Setup**
1. Shared fixture set under bull vs bear mapped regimes.
2. Run RE-001 with Doc 02 priorities (US4 complete).

**Expected**
- Bear BUY count ≤ 50% of bull BUY count on that fixture set.

---

## Suggested automated test map

| Scenario | Suggested layer |
| -------- | --------------- |
| A | Integration + regression |
| B | Unit + integration |
| C | Integration |
| D | Integration |
| E | Frontend component + API permission tests |
| F | Integration (paper routes) |
| G | API/integration analytics |
| H | Unit/integration orchestrator isolation |

---

## Definition of validation complete

All scenarios A–H pass on a branch with RE-001 integrated, with baseline production regressions still green, before enabling `LAB_SHADOW` in any shared environment.
