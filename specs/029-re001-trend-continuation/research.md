# Research: RE-001 Trend Continuation Integration

**Feature**: `029-re001-trend-continuation`  
**Date**: 2026-08-03  
**Purpose**: Resolve technical unknowns for MVP planning. No implementation code.

---

## R1 — Persistence system of record

**Decision**: First-class decisions table (`recommendation_engine_decisions` logical name) is the system of record for RE-001 Decision Objects and production-comparison metadata.

**Rationale**:
- Clarify session 2026-08-03 chose first-class table over JSON-only.
- REDS Decision Objects need durable, queryable history for EEF and analytics.
- Keeps `analysis_history.recommendation` as production-only authority.
- Supports multi-engine future via `engine_id`.

**Alternatives considered**:
- Namespaced JSON on `shadow_outputs` only — rejected as SoR (poor indexing, multi-engine friction).
- Experiment tables only — rejected; couples lab decisions too tightly to experiment lifecycle for day-to-day UI.
- Hybrid JSON + table — deferred; optional compact link later if join convenience needed.

---

## R2 — Isolation pattern for lab evaluation

**Decision**: Mirror existing shadow isolation envelope: run RE-001 after production recommendation is resolved; wrap in fail-open error handling with timeout; never mutate production recommendation fields.

**Rationale**:
- Shadow infrastructure already established patterns for non-production evaluation.
- Spec requires production path success independent of RE-001 (FR-012, SC-001).
- Orchestrator already owns per-symbol post-bulk sequencing.

**Alternatives considered**:
- Parallel process/microservice — rejected (over-architecture for brownfield monolith).
- In-process before production recommendation — rejected (violates production-first shortlist ownership and complicates comparison).
- Full async fire-and-forget without await on scan critical path — possible later optimization; MVP may await with timeout if simpler, as long as production result is already finalized and failures do not roll back production.

---

## R3 — Evaluation universe

**Decision**: Evaluate only production shortlist / full-analysis symbols per run.

**Rationale**:
- Clarify session locked shortlist-only.
- Inputs already loaded; latency bounded; aligns with SC-003.

**Alternatives considered**:
- All matched symbols / full NIFTY500 — rejected for MVP performance and scope risk.

---

## R4 — Market regime mapping (Bull / Sideways / Bear)

**Decision**: Map existing platform regime / market-permission / FEAT-004-style outputs into RE-001 orchestration buckets using an explicit versioned mapping table in configuration. If mapping inputs are missing or unusable → **REJECT** with reason `missing_market_context` (no default Sideways).

**Recommended initial mapping intent** (to be refined in tasks with exact enum names from live code):

| Platform signal family | RE-001 bucket |
| ---------------------- | ------------- |
| Favorable / bullish trend + entries allowed | Bull |
| Cautious / mixed / neutral | Sideways |
| Defensive / high-risk / new entries blocked / bearish | Bear |
| Unknown / missing / failed classification | **Unusable → REJECT** |

**Rationale**:
- RE-001 Doc 02 requires regime-adaptive strategy priority.
- Spec FR-025 forbids assumed defaults when context missing.
- Exact enum strings vary across FEAT-004 vs market_permission; mapping table isolates that churn.

**Alternatives considered**:
- Default Sideways on missing — rejected by clarify (capital risk).
- Hardcode one service’s enums inside engine — rejected (coupling).

---

## R5 — UI surface

**Decision**: Hybrid MVP — RE-001 section on symbol/analysis detail + compact Lab comparison view (tab/lightweight page). Full multi-engine Lab product deferred.

**Rationale**: Clarify session; balances SC-002/SC-004 with limited frontend scope.

**Alternatives considered**:
- Admin-only diagnostics — rejected (blocks trader paper workflow).
- Full Lab console — deferred beyond MVP.

---

## R6 — Access control

**Decision**: Admin + Trader may view lab surfaces when feature permission / UI flag enabled. Unauthenticated denied. Stage/flag administration remains admin-appropriate.

**Rationale**: Clarify session; matches research workstation multi-role usage.

**Alternatives considered**:
- Admin only — rejected for paper-trade user stories.
- Always-on for all authenticated — rejected (need kill-switch without code).

---

## R7 — Paper provenance

**Decision**: Extend paper prefill/order metadata with engine provenance (`engine_id`, `engine_version`, optional `recommendation_id`). Do not change fill, gap replay, or market engine.

**Rationale**: SC-005 attribution without paper logic redesign.

**Alternatives considered**:
- Separate paper ledger per engine — rejected (duplicate complexity).
- Infer provenance from timestamps only — rejected (unreliable).

---

## R8 — Strategy implementation depth for MVP

**Decision**: Implement RE-001 orchestration layers (primary families + supporting + validation) as deterministic rule sets over **existing** TA/regime/sector/breadth features. Full Strategy Library productization is incremental; strategy *names/families* must still appear on Decision Objects.

**Rationale**:
- Doc 02 is orchestration-first; Doc 03 thresholds unpublished.
- Spec allows engine-local descriptors conforming to SCM shape.
- Avoid inventing parallel indicator engine.

**Alternatives considered**:
- Wait for full Strategy Library platform — delays all value.
- Hardcode single strategy only — violates RE-001 multi-family architecture.

---

## R9 — API exposure style

**Decision**: Prefer dedicated lab read endpoints for comparison/list **and** optional non-breaking enrichment on analysis detail payloads where convenient. Production shortlist fields never switch to RE-001 in lab mode.

**Rationale**:
- Compact Lab view needs scan-level query.
- Detail panel benefits from symbol-scoped decision fetch.
- Backward compatibility via additive fields.

**Alternatives considered**:
- Only embed in screener SSE payload — couples UI to scan stream; weaker historical query.
- Only DB-side admin tools — fails SC-002.

---

## R10 — Analytics approach

**Decision**: Additive EngineID segmentation for RE-001 counts (BUY/WATCH/REJECT, success/fail, optional mismatch rate). Do not redefine production engine-health meaning.

**Rationale**: FR-016 + regression of existing analytics.

**Alternatives considered**:
- Replace engine-health with multi-engine only — breaks existing clients.
- Shadow_outputs scraping for analytics — weaker than first-class table.

---

## R11 — Timeout / failure semantics

**Decision**: Per-symbol (or per-run budget) timeout for RE-001; on timeout/exception: log, count diagnostic failure, **do not** write a false BUY; optional diagnostic record; production result already committed remains valid.

**Rationale**: SC-003 and fail-open isolation.

**Alternatives considered**:
- Fail entire scan on RE-001 error — rejected.
- Infinite await — rejected (scan latency risk).

---

## R12 — Technology stack (no new platform)

**Decision**: Stay on existing FastAPI + SQLAlchemy + PostgreSQL + React SPA. No new message bus, no new microservice, no new UI framework.

**Rationale**: Brownfield constraint; reuse existing deployment topology.

**Alternatives considered**:
- Separate RE service — rejected for MVP complexity.

---

## R13 — Analysis remediation locks (2026-08-03)

**Decision**:
- Stages: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` only (`ACTIVE` reserved).
- Feature key: `recommendation_lab` only.
- Paper trade guidance: RE-001 complete plan → else production `trade_plans`; provenance always RE-001 when lab-originated.
- Portfolio: requesting user snapshot when available; else fail-closed BUY with `portfolio_context_unavailable`.
- `scan_run_id` → existing completed-scan / latest-scan identity family.
- SC-006: bear BUY count ≤ 50% of bull BUY count on shared fixtures.
- SC-003: engineering gate = fail-open; 95% is ops soak with zero RE-001-caused production failures.

**Rationale**: Resolves analyze HIGH/MEDIUM findings before implement.

**Alternatives considered**: Dual feature keys; invent default portfolio; Sideways default on missing regime — all rejected.

---

## Open items deferred to implementation tasks (non-blocking)

1. Exact enum mapping table values from live `MarketRegimeResult` / FEAT-004 labels (mapper module).
2. Numeric default for `re001_timeout_ms` (suggest 2000–5000 ms per symbol; finalize in T004).
3. Whether registry is DB table or settings-only for MVP (settings-first per plan).

These do not reopen architecture; they are configuration/detail tasks.
