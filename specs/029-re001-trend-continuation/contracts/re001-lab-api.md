# Contract: RE-001 Lab Read/Write API Surface

**Feature**: `029-re001-trend-continuation`  
**Status**: Planning contract (logical endpoints — not implementation code)  
**Auth**: Existing session auth + feature permission key **`recommendation_lab`** for lab read surfaces

---

## Design rules

1. **Backward compatible**: existing scanner/analysis shortlist fields remain production-driven.
2. **Additive only**: new routes and/or optional response blocks.
3. **No production authority**: lab endpoints never rewrite production shortlists.
4. **Feature-gated**: lab reads require feature key `recommendation_lab` for Admin and Trader.
5. **Stages**: evaluation gated by `re001_enabled` + `re001_stage` ∈ {`LAB_SHADOW`,`PAPER_LINKED`}; `OFF` yields no new decisions.

---

## Logical capabilities

### C1 — Get engine registration / stage

**Purpose**: Ops visibility for RE-001 enabled/stage/version.

**Response (logical)**:
- engine_id, name, engine_version, stage, enabled

**Auth**: authenticated; stage mutation admin-appropriate if exposed.

---

### C2 — Get decisions for a scan run

**Purpose**: Compact Lab comparison view.

**Inputs**: `scan_run_id` — mapped to the platform’s existing completed-scan / latest-scan identity (same family used to restore “last scan” results)

**Response (logical)**: list of rows:
- symbol
- production_action / production_score (if available)
- re001 recommendation_state / confidence_score
- strategy_name / strategy_family
- is_mismatch
- recommendation_id

**Errors**:
- 401/403 without auth/permission
- 404 unknown scan
- empty list if RE-001 disabled or no shortlist

---

### C3 — Get decision for symbol (+ optional scan)

**Purpose**: Symbol detail RE-001 panel.

**Inputs**: symbol, optional scan_run_id / analysis_history_id

**Response (logical)**: full Decision Object + strategy trace + validation + comparison

**Errors**: 401/403; 404 if no decision

---

### C4 — Paper prefill from RE-001 decision

**Purpose**: SC-005 provenance path.

**Inputs**: recommendation_id (or symbol + scan with engine_id=RE-001)

**Behavior**:
- Prefill uses RE-001 `trade_guidance` when `complete=true`; otherwise falls back to production `trade_plans` for the same symbol/scan.
- Response includes `source_engine_id=RE-001`, `source_engine_version`, `source_recommendation_id`.
- Does not change fill semantics of subsequent order placement.
- Requires RE-001 stage not `OFF` and a persisted decision for provenance.

---

### C5 — Analytics RE-001 health (optional extension)

**Purpose**: FR-016

**Window**: rolling operational window (e.g. 7d — align with existing engine-health window)

**Metrics (logical)**:
- counts by recommendation_state
- evaluation success/error/timeout counts
- optional mismatch rate vs production

**Constraint**: production engine-health totals remain valid and not redefined.

---

## Optional enrichment of existing analysis payloads

When convenient for detail UI, analysis/full or screener analysis items MAY include optional:

```text
lab_engines.RE-001: { recommendation_id, recommendation_state, confidence_score, strategy_name, ... }
```

Clients that ignore unknown fields continue to work.  
`buy_candidate_symbols` / `watch_candidate_symbols` remain production-sourced in lab mode.

---

## Non-goals

- No public API for promoting RE-001 to production shortlist.
- No breaking changes to existing response models.
- No unauthenticated lab access.
