# Implementation Plan: RE-001 Trend Continuation Recommendation Engine Integration

**Branch**: `029-re001-trend-continuation` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/029-re001-trend-continuation/spec.md` (RE-001 Docs 01–02 + REDS v1.0 + clarify session 2026-08-03)

**Note**: This is the master implementation plan for brownfield integration. It explains *how* integration will be executed. It does **not** contain implementation code, SQL, API bodies, or task lists (`tasks.md` is produced by `/speckit-tasks`).

---

## 1. Executive Summary

### Goal

Integrate **RE-001 (Trend Continuation Recommendation Engine)** as an **additional** engine inside the Recommendation Lab of the existing production Trading Application, without replacing or redesigning the current composite recommendation engine, scanner, technical analysis, paper fills, analytics formulas, or scheduler jobs.

### Approach

1. **Keep production path authoritative** for shortlists and retail BUY/WATCH/REJECT.
2. **Register RE-001** as a lab engine with canonical flags/stages (`OFF` | `LAB_SHADOW` | `PAPER_LINKED`; `ACTIVE` reserved/out of scope).
3. **Run RE-001 only on production shortlist / full-analysis symbols**, after production recommendations resolve.
4. **Isolate failures** so RE-001 never fails production scans.
5. **Persist** REDS Recommendation Decision Objects in a **first-class decisions table**.
6. **Surface** results via hybrid UI (symbol detail + compact Lab comparison).
7. **Wire** paper provenance and analytics segmentation without changing paper fill or production analytics meaning.
8. **Validate** with production-invariance regression and RE-001 behavior tests before any promotion path (promotion remains out of scope).

### Expected outcome

Operators can compare RE-001 continuation decisions to production, paper-trade with provenance, and accumulate experiment evidence—while production advisory behavior remains unchanged when RE-001 is off or in lab mode.

---

## Summary (SpecKit)

| Item | Content |
| ---- | ------- |
| Primary requirement | Lab-isolated RE-001 engine producing BUY/WATCH/REJECT Decision Objects |
| Technical approach | Post-production isolated evaluate → persist → optional API/UI/analytics; production engine untouched |
| Migration style | Additive, flag-gated, fail-open, shortlist-only |
| Clarifications locked | First-class table; hybrid UI; Admin+Trader; shortlist-only; missing regime → REJECT; stages `OFF|LAB_SHADOW|PAPER_LINKED`; feature key `recommendation_lab`; paper plan fallback; portfolio fail-closed |

---

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/React 18 (frontend)  
**Primary Dependencies**: FastAPI, SQLAlchemy (async + sync), Pydantic Settings, PostgreSQL, APScheduler, existing FYERS/market-data stack, Vite React SPA  
**Storage**: PostgreSQL — new first-class `recommendation_engine_decisions` (logical name); production `analysis_history` retained as production SoR  
**Testing**: pytest (backend unit/integration/regression), Vitest/Playwright patterns as existing for frontend  
**Target Platform**: Existing two-tier monolith (FastAPI + React SPA), singleton-worker scheduler pod  
**Project Type**: web application (backend + frontend)  
**Performance Goals**: RE-001 must not reduce production path success rate; evaluate shortlist only; per-symbol isolation timeout; SC-003 ≥95% RE-001 attempts without impacting production success  
**Constraints**: Brownfield; no production shortlist rewrite; no live orders; advisory-only; REDS Decision Object shape; deterministic labels (no LLM-owned state); Admin+Trader via `recommendation_lab`; stages `OFF|LAB_SHADOW|PAPER_LINKED`  
**Scale/Scope**: Shortlist-sized evaluation set per scan (typical top-N full analysis), multi-user paper accounts, multi-engine future (RE-00x) via registry pattern  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project constitution template is placeholder; **operational gates** derived from SHARED_CONTEXT_PACK / REDS / feature spec:

| Gate | Status | Notes |
| ---- | ------ | ----- |
| Brownfield safety / bounded delta | **PASS** | Additive engine + table + thin hooks; no redesign |
| Production recommendation authority preserved | **PASS** | Lab mode never owns shortlist |
| Deterministic recommendation states | **PASS** | Labels not LLM-owned |
| Reuse shared services (no parallel stacks) | **PASS** | SCS mapped to existing modules |
| Isolation / fail-open for production | **PASS** | Shadow-pattern envelope |
| Backward-compatible APIs | **PASS** | Optional fields / new lab routes only |
| No live trading | **PASS** | Advisory + paper only |
| Clarifications complete for MVP | **PASS** | Session 2026-08-03 |

**Post-Phase-1 re-check**: PASS — design artifacts remain additive contracts only; no gate violations requiring Complexity Tracking.

---

## Project Structure

### Documentation (this feature)

```text
specs/029-re001-trend-continuation/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 validation guide
├── contracts/           # Phase 1 interface contracts
│   ├── re001-decision-object.md
│   ├── re001-lab-api.md
│   └── re001-ui-contract.md
├── spec.md              # Feature specification (complete)
├── checklists/
│   └── requirements.md
└── tasks.md             # NOT created by /speckit-plan
```

### Source Code (repository root — existing layout; planned touchpoints only)

```text
backend/app/
├── agents/
│   └── orchestrator_agent.py          # EXTEND: isolated RE-001 hook after production
├── config/
│   └── settings.py                    # EXTEND: re001_* flags/stage
├── models/                            # EXTEND: engine decision model module
├── schemas/                           # EXTEND: Decision Object + lab DTOs
├── services/
│   ├── recommendation_service.py      # KEEP production path
│   ├── paper_trading_service.py       # EXTEND: provenance only
│   ├── shadow_executor*.py            # REUSE isolation patterns
│   └── re001/                         # NEW package (engine + orchestration helpers)
├── routes/                            # EXTEND: lab read APIs / optional analytics dim
└── ...

frontend/src/
├── components/
│   ├── StockDetailPanel.tsx           # EXTEND: RE-001 section
│   └── ...                            # NEW compact Lab comparison view component/page
├── layout/navConfig.tsx               # EXTEND: feature-gated Lab entry
├── api.ts                             # EXTEND: lab fetch helpers
└── utils/featureCatalogDefaults.ts    # EXTEND: lab feature key

alembic/ or backend/alembic/           # EXTEND: additive migration for decisions table
```

**Structure Decision**: Stay within the existing backend/frontend monolith. Introduce a bounded `re001` service package and additive persistence/API/UI surfaces. Do not create a new microservice or redesign agent topology.

---

## Complexity Tracking

> No constitution/gate violations requiring justification. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## 2. Architecture Review

### Current system (as-is)

```text
Scanner / Full Analysis
        → Market Data + TA bulk
        → News / Fund / Backtest (parallel)
        → Sector RS / Market permission (challenger/overlays)
        → RecommendationAgent + RecommendationService (PRODUCTION)
        → Final gate / shortlist classification
        → Persist AnalysisHistory
        → Rank / API / Dashboard
        → (existing) shadow hooks for experimental features
```

### Target system (to-be, lab mode)

```text
... production path unchanged through shortlist classification ...
        → [if re001_enabled && stage != OFF]
              Build immutable LabExecutionContext (shortlist symbol only)
              → RE-001 engine evaluate (isolated, timed)
              → Recommendation Decision Object
              → Persist recommendation_engine_decisions (+ comparison meta)
        → Return production response (+ optional lab payload)
        → UI: production dashboard unchanged; detail/Lab compare when permitted
        → Paper: optional provenance from RE-001 decision
        → Analytics: optional EngineID dimension for RE-001 counts
```

### Design principles

1. **Production-first**: shortlist and retail UX remain production-sourced.
2. **Engine purity**: RE-001 only decides/explains; does not own market data, TA math, paper fills, or scheduler.
3. **REDS compliance**: standard pipeline order and Decision Object fields.
4. **Fail-open**: production success independent of RE-001.
5. **Additive schema**: no rewrite of `analysis_history.recommendation` meaning.

---

## 3. Current System Analysis

| Capability | Existing home | Role today |
| ---------- | ------------- | ---------- |
| Market data | `market_data_service`, FYERS, candle store | OHLCV authority |
| Scanner | `screener_service`, `scan_execution_service`, orchestrator stages | Universe → shortlist |
| Technical analysis | `technical_analysis_service` | Indicators + scores |
| News / sentiment | news agent/service, LLM assist | Sentiment inputs |
| Fundamentals | fundamental agent | Context scores |
| Backtest | `backtest_service` / agent | Historical validation inputs |
| Production recommendation | `recommendation_service` + agent | Composite BUY/WATCH/REJECT + trade plans |
| Overlays / challenger | FEAT-004/007, SR-003/004, market permission | Score/challenger paths |
| Shadow / experiment | `shadow_executor*`, governance experiment services | Isolated experimental runs |
| Paper trading | `paper_trading_service`, market engine | Simulated execution |
| Analytics | analytics routes/services, daily analytics | Engine health, shadow status |
| Dashboard | Scanner App, StockDetailPanel, Paper Desk | Operator UX |
| Scheduler | APScheduler jobs, daily-scan | Triggers existing pipeline |
| Config / flags | `settings.py`, feature permissions | Runtime control |
| Logging / audit | logger, db_logger, audit services | Observability |

---

## 4. RE-001 Integration Strategy

### Strategy statement

**Parallel lab engine with shared inputs, separate outputs, and zero production authority until a future explicit promotion feature.**

### Locked product decisions (from clarify)

| Decision | Value |
| -------- | ----- |
| Persistence | First-class decisions table |
| UI | Hybrid: symbol detail + compact Lab comparison |
| Visibility | Admin + Trader with feature permission |
| Evaluation set | Production shortlist / full-analysis only |
| Missing market regime | REJECT + reason code; no default regime |

### Integration posture by concern

| Concern | Strategy |
| ------- | -------- |
| Scanner shortlist | **Do not change** ownership or stage-stopping |
| Production scores/gates | **Do not change** |
| RE-001 placement | After production recommendation resolved per shortlist symbol |
| Shared inputs | Reuse already-fetched candles/TA/regime/sector/breadth/portfolio snapshot |
| Persistence | New decisions table; optional link to analysis/scan id |
| API | Optional lab block on analysis responses and/or dedicated lab read endpoints |
| UI | Feature-gated; clearly labeled lab/experimental |
| Paper | Provenance metadata only |
| Analytics | Segment counts by EngineID without redefining production aggregates |
| Scheduler | No new trading cron; piggyback existing scan path |

### Safest migration approach

1. Ship **OFF by default**.
2. Enable **LAB_SHADOW** in non-prod / controlled env.
3. Prove **production invariance** (SC-001).
4. Enable UI + paper provenance.
5. Only then expand analytics dashboards.
6. Never auto-promote to production shortlist in this feature.

---

## 5. Component Classification

Legend: **KEEP** (unchanged behavior) · **REUSE** (consume as-is) · **MODIFY** (behavior change of existing logic) · **EXTEND** (thin additive hook/config/UI) · **NEW** · **REMOVE**

| Module | Classification | Reason |
| ------ | -------------- | ------ |
| **Scanner** (`screener_service`, stage logic, shortlist caps, stage-stop) | **KEEP** | Spec forbids scanner redesign; RE-001 consumes shortlist only |
| **Scan execution / locks** | **KEEP** / **REUSE** | Existing locks protect concurrency; RE-001 must respect them |
| **Recommendation pipeline (production)** | **KEEP** | Composite engine remains production authority |
| **Orchestrator post-bulk path** | **EXTEND** | Isolated RE-001 invoke after production decision; no production label rewrite |
| **Technical Analysis calculations** | **KEEP** / **REUSE** | No indicator/score formula changes; RE-001 consumes results |
| **News Analysis** | **KEEP** / **REUSE** | Context only; not RE-001 primary strategy |
| **Fundamental Analysis** | **KEEP** / **REUSE** | Context only |
| **Backtesting** | **KEEP** / **REUSE** | Existing BT for production inputs; later validation may reuse offline |
| **AI Agents (LLM reasoning)** | **KEEP** | May assist explanation only; must not own RE-001 state |
| **Paper Trading fill/lifecycle** | **KEEP** | No change to fills, gap replay, market engine |
| **Paper prefill / order metadata** | **EXTEND** | Engine provenance fields only |
| **Analytics calculations (production)** | **KEEP** | Existing production aggregates stay correct |
| **Analytics surfaces** | **EXTEND** | Optional RE-001 counts / mismatch rate |
| **Dashboard retail scanner cards** | **KEEP** | Production-sourced |
| **Stock detail / nav / lab view** | **EXTEND** / **NEW** (compact Lab view) | Hybrid UI |
| **Database production tables** | **KEEP** | `analysis_history.recommendation` meaning unchanged |
| **Database lab decisions** | **NEW** | First-class decisions table |
| **Scheduler job definitions** | **KEEP** | No new mandatory cron; existing jobs trigger pipeline that may include RE-001 |
| **Configuration / feature flags** | **EXTEND** | `re001_*` settings + feature permission key |
| **Logging / audit** | **REUSE** / **EXTEND** | Structured lab events; no new logging platform |
| **Experiment / shadow framework** | **REUSE** / **EXTEND** | Isolation patterns; optional experiment linkage |
| **Market data pipeline** | **KEEP** / **REUSE** | No second fetch path for RE-001 core path |
| **Portfolio / risk settings** | **REUSE** | Validation inputs for portfolio-before-trade |
| **Sector RS / breadth / regime** | **REUSE** | Market context mapping inputs |
| **Existing shadow_outputs keys** | **KEEP** | Not RE-001 SoR; do not break other features |

**REMOVE**: Nothing in MVP.

**MODIFY** (true behavior change of existing domain logic): **None planned.** All production domain behaviors are KEEP; integration is EXTEND/NEW only.

---

## 6. Reuse Strategy

| Existing capability | Why reuse |
| ------------------- | --------- |
| Market Data Service / candle store / FYERS path | Canonical OHLCV; avoids dual data truth |
| Technical Analysis Service | Provides structure, MAs, Supertrend, RSI, MACD, volume for continuation confirmation |
| Scanner shortlist | Bounds work set; ensures shared analysis inputs already loaded |
| News / Event services | Optional supporting context only |
| Fundamental results | Optional context; not primary philosophy |
| Backtest Service | Existing results in context; future offline validation of continuation rules |
| Market permission / FEAT-004 regime signals | Map to Bull/Sideways/Bear for orchestration |
| Market breadth / sector RS | Supporting strategies + bull-stock RS intent |
| Paper Trading Service | Paper lifecycle already correct; only provenance needed |
| Portfolio / risk settings | Portfolio-before-trade validation |
| RecommendationService (production) | Continues as production engine; not reimplemented |
| Shadow isolation patterns | Proven fail-open envelope for experimental work |
| Analytics engine-health patterns | Extend dimensionally rather than new observability stack |
| Settings / feature permissions | Operational control model already exists |
| Logging / audit | Compliance and diagnostics |
| Scheduler + scan locks | Safe concurrent execution |
| Caching | Avoid redundant market-data load for lab path |

**REDS Shared Core Services mapping (logical → existing)**

| REDS SCS | Existing reuse target |
| -------- | --------------------- |
| SCS-01 Market Regime | market permission / FEAT-004 regime classification |
| SCS-02 Market Breadth | `market_breadth` |
| SCS-03 Sector Analysis | sector services |
| SCS-04 Relative Strength | `sector_rs_service` / related |
| SCS-05 Liquidity | TA/screener liquidity checks |
| SCS-06 Technical Indicators | `technical_analysis_service` |
| SCS-07 News & Event | news + event calendar |
| SCS-08 Risk | gate/risk settings patterns (read-only for RE-001 validation) |
| SCS-09 Portfolio | paper/portfolio state snapshot |
| SCS-10 Confidence | engine-local confidence scoring using shared inputs |
| SCS-11 Explainability | structured evidence + optional LLM assist for text only |
| SCS-12 Audit | audit/logging + decisions table trail |

---

## 7. New Component Strategy

Only **new** components required for RE-001 (logical):

### 7.1 Engine Registry (config or light module)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Identify production engine vs RE-001 (version, stage, enabled) |
| Responsibilities | Resolve whether RE-001 runs; expose metadata for Decision Objects |
| Inputs | Settings / feature flags |
| Outputs | Engine registration view |
| Dependencies | `settings` |

### 7.2 RE-001 Engine Module

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Trend-continuation strategy orchestration and decisioning |
| Responsibilities | Eligibility (incl. Bull Stock Filter intent), strategy activation/priority/conflict resolution, supporting evidence, validation, confidence, Decision Object population, explainability fields |
| Inputs | Lab execution context (candles, TA, regime/breadth/sector, portfolio/risk snapshot, quality flags) |
| Outputs | Recommendation Decision Object (REDS fields) or REJECT-with-reason |
| Dependencies | Shared services (read-only); no private market-data stack |

### 7.3 Lab Execution Context Builder

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Immutable snapshot of inputs + production recommendation for comparison |
| Responsibilities | Assemble context after production decision; freeze inputs |
| Inputs | Orchestrator per-symbol analysis artefacts |
| Outputs | LabExecutionContext |
| Dependencies | Existing schemas/results |

### 7.4 Decision Persistence Service

| Aspect | Definition |
| ------ | ---------- |
| Purpose | System of record for RE-001 Decision Objects + comparison metadata |
| Responsibilities | Validate Decision Object completeness; write to first-class table; query by scan/symbol/engine |
| Inputs | Decision Object, production action/score, run identifiers |
| Outputs | Persisted Engine Decision Records |
| Dependencies | DB session patterns; model layer |

### 7.5 Lab Query / API Adapter

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Read path for UI and analytics |
| Responsibilities | Fetch decisions and comparison rows; enforce auth/feature permission |
| Inputs | scan_id/symbol/window filters |
| Outputs | Lab DTOs for detail + compact comparison |
| Dependencies | Persistence service; auth/feature guards |

### 7.6 Compact Recommendation Lab UI

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Scan-level production vs RE-001 comparison |
| Responsibilities | Table/list of states; link to symbol detail |
| Inputs | Lab comparison API |
| Outputs | Operator-visible comparison |
| Dependencies | Feature permission; nav entry |

### 7.7 Symbol Detail RE-001 Panel

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Explainability for one symbol |
| Responsibilities | Show state, primary strategy, support, validation, evidence, vs production |
| Inputs | Decision Object DTO |
| Outputs | UI section |
| Dependencies | Feature permission |

**Not new**: Scanner engine, TA engine, paper fill engine, production recommendation math, scheduler framework.

---

## 8. Dependency Analysis

### Internal dependencies (order)

```text
Settings / feature flags
        → Engine registry
        → Lab context builder (needs production result)
        → RE-001 engine
        → Decision persistence
        → Lab API / optional response enrichment
        → Frontend detail + Lab view
        → Paper provenance (optional path)
        → Analytics segmentation (optional path)
```

### Shared services dependencies

- Must be available and healthy for quality decisions: market data history, TA results, regime signals.
- Missing **regime/context** → RE-001 REJECT (FR-025); production unaffected.

### Database dependencies

- Additive decisions table migration before enabling persistence flag.
- Optional FK/link to analysis_history id / scan run id.
- No change required to production recommendation column semantics.

### API dependencies

- Existing analysis/scanner APIs remain primary.
- Lab read contracts for comparison/detail.
- Feature permission enforcement on lab surfaces.

### Scheduler dependencies

- Existing scan jobs call pipeline; RE-001 rides that path when enabled.
- No dependency on new scheduled promotion jobs.

### Paper trading dependencies

- Prefill/order create path must accept optional engine provenance.
- Fill engine independent of RE-001.

### Analytics dependencies

- Decisions table queryable by `engine_id`, state, time window.
- Production engine-health queries must remain valid when RE-001 data exists.

### Recommendation dependencies

- Production recommendation must complete first for comparison metadata (not required for RE-001 pure logic, but required for lab compare).
- RE-001 does not call production score mutators.

---

## 9. Migration Strategy

### Migration sequence

| Step | Action | Exit criteria |
| ---- | ------ | ------------- |
| M0 | Land plan + contracts; baseline regression suite green | Planning accepted |
| M1 | Settings/flags OFF default; registry metadata | Boot with flags off |
| M2 | Decisions table additive migration | Empty table; app starts |
| M3 | RE-001 engine pure evaluate (unit-tested) behind flag | Deterministic unit outcomes |
| M4 | Orchestrator isolated hook; persist when enabled | Lab decisions on shortlist only; production invariant |
| M5 | Lab read APIs | Detail/compare data available |
| M6 | Frontend hybrid UI (feature-gated) | SC-002/SC-004 |
| M7 | Paper provenance | SC-005 |
| M8 | Analytics RE-001 dimension | FR-016 |
| M9 | Hardening: timeouts, metrics, docs | SC-003/007; regression green |

### Rollback strategy

1. Set `re001_enabled=false` / stage `OFF` — immediate behavioral rollback.
2. Feature permission off — hides UI without schema rollback.
3. Migration remains additive; table can stay empty (no destructive down required for safety).
4. Remove optional API fields usage on clients (ignore unknown fields already).

### Regression strategy

- Always run production recommendation classification tests.
- Scanner smoke (shortlist, stage-stop).
- Paper lifecycle smoke.
- Analytics production aggregates smoke.
- RE-001 on vs off production invariance test (SC-001) as gate for any enablement.

### Validation checkpoints

| Checkpoint | When |
| ---------- | ---- |
| CP1 Production invariant | After M4 |
| CP2 Decision Object completeness | After M3–M4 |
| CP3 Missing regime REJECT | After M3–M4 |
| CP4 UI reviewability | After M6 |
| CP5 Paper provenance | After M7 |
| CP6 Flag OFF zero artefacts | After M4–M8 |

### Deployment considerations

- Default **OFF** in production.
- Deploy migration before enabling flag.
- Singleton scan lock already serializes heavy work; keep RE-001 inside that protected path.
- Monitor scan duration and error rates when first enabling LAB_SHADOW.
- Label UI as Lab/Experimental to prevent operator confusion.

---

## 10. Risk Assessment

| Severity | Risk | Impact | Mitigation |
| -------- | ---- | ------ | ---------- |
| **Critical** | RE-001 writes production recommendation / shortlist | Wrong live advisory | Separate table/fields; invariance tests; code review gate |
| **Critical** | RE-001 exception aborts scan | Production outage of advisory pipeline | Isolated try/except + timeout; fail-open |
| **High** | Operator confuses lab BUY with production BUY | Bad paper/manual action | Clear labeling; production cards unchanged; provenance badges |
| **High** | Incomplete Decision Objects | Broken EEF/compare | Validate before persist; reject incomplete |
| **High** | Wrong regime mapping → overtrading | Capital risk in lab paper | Explicit mapping table; bear-regime verification (SC-006); missing → REJECT |
| **Medium** | Scan latency increase | Operator friction | Shortlist-only; timeout budget; async isolation patterns |
| **Medium** | Multi-user portfolio validation ambiguity | Inconsistent REJECT/WATCH | **Resolved**: requesting user paper/risk snapshot; if unavailable → fail-closed BUY with `portfolio_context_unavailable` (FR-026) |
| **Medium** | Doc 03–05 thresholds absent | Strategy parameter drift | Conservative defaults; versioned config; no architecture churn |
| **Low** | Extra nav clutter | UX noise | Feature-gate Lab entry; default UI flag off |
| **Low** | Future multi-engine registry growth | Refactor pressure | Keep Decision Object + engine_id generic from day one |

---

## 11. Validation Strategy

| Layer | What is validated |
| ----- | ----------------- |
| Business | RE-001 philosophy (continuation only); regime participation; REJECT on missing context |
| Technical | Isolation; flags; persistence completeness; shortlist-only evaluation set |
| Recommendation | Decision Object fields; single primary strategy; states ∈ {BUY,WATCH,REJECT} |
| Integration | Production invariance; paper provenance; lab UI permission; analytics dimension |
| Regression | Scanner, production recommendation, paper, analytics baseline |
| Operational | Enable/disable without redeploy; logs countable |

---

## 12. Testing Strategy

### Unit testing

- RE-001 eligibility / Bull Stock Filter intent.
- Strategy activation priority by Bull/Sideways/Bear.
- Conflict resolution → single primary.
- Missing regime → REJECT + reason code.
- Supporting strategies cannot create BUY alone.
- Decision Object field completeness validator.
- Settings stage transitions.

### Integration testing

- Orchestrator: production result unchanged with RE-001 on.
- Persist decision row linked to symbol/run.
- Lab query by scan/symbol.
- Feature permission deny/allow for Trader/Admin.
- Paper prefill retains engine_id/version.

### Regression testing

- Existing recommendation threshold/gate tests.
- Scanner stage-stop and shortlist tests.
- Shadow_outputs keys for other features still intact.
- Paper fill/gap-replay tests unchanged.
- Analytics production engine-health totals stable.

### Paper trading validation

- Prefill from RE-001 BUY with provenance.
- Normal order lifecycle still succeeds.
- Attribution of tickets to RE-001 post-trade.

### Recommendation validation

- Controlled fixtures for bull vs bear participation (SC-006 qualitative gate).
- Production vs RE-001 both stored when diverge.

### Analytics validation

- Counts by state for EngineID=RE-001 over window.
- Production aggregates not polluted incorrectly.

### Performance validation

- Shortlist-only evaluation confirmed (no full-universe RE-001).
- Timeout path: production success preserved.
- Optional duration metrics for lab diagnostics.

---

## 13. Implementation Roadmap

### Phase 1 — Engine Registration

| Item | Content |
| ---- | ------- |
| **Objective** | Register RE-001 identity, version, stage, flags; default OFF |
| **Business value** | Safe operational control; REDS engine identity |
| **Dependencies** | Spec clarifications; settings patterns |
| **Risks** | Accidental enable in prod → default OFF + deploy checklist |
| **Validation** | Boot with flags off; registry metadata readable |
| **Deliverables** | Settings block; engine registry module; feature permission key plan |

### Phase 2 — Recommendation Pipeline Integration

| Item | Content |
| ---- | ------- |
| **Objective** | Isolated RE-001 evaluate on shortlist after production; persist Decision Objects |
| **Business value** | Lab decisions exist without production risk |
| **Dependencies** | Phase 1; decisions table; shared inputs from orchestrator |
| **Risks** | Critical isolation failure; latency |
| **Validation** | SC-001, FR-012, FR-017, FR-025, CP1–CP3 |
| **Deliverables** | Context builder; RE-001 engine; persistence; orchestrator hook |

### Phase 3 — Paper Trading Integration

| Item | Content |
| ---- | ------- |
| **Objective** | Provenance from RE-001 decisions into paper prefill/orders |
| **Business value** | Experiment path with attribution (SC-005) |
| **Dependencies** | Phase 2 Decision Objects |
| **Risks** | Accidental change to fill logic → scope control |
| **Validation** | Provenance present; fill tests still green |
| **Deliverables** | Prefill/order metadata extension only |

### Phase 4 — Analytics Integration

| Item | Content |
| ---- | ------- |
| **Objective** | RE-001 health counts and optional mismatch vs production |
| **Business value** | Operational visibility for lab quality |
| **Dependencies** | Decisions table populated |
| **Risks** | Breaking production aggregates → additive queries only |
| **Validation** | FR-016; production aggregate regression |
| **Deliverables** | Analytics extension for EngineID=RE-001 |

### Phase 5 — Dashboard Integration

| Item | Content |
| ---- | ------- |
| **Objective** | Hybrid UI: symbol detail RE-001 section + compact Lab comparison |
| **Business value** | Human review without DB access (SC-002/SC-004) |
| **Dependencies** | Lab APIs; feature permission |
| **Risks** | Operator confusion → labeling |
| **Validation** | Permission tests; review under 2 minutes |
| **Deliverables** | Detail panel; Lab view; nav entry |

### Phase 6 — Validation

| Item | Content |
| ---- | ------- |
| **Objective** | End-to-end proof of isolation, quality, ops readiness |
| **Business value** | Confidence to leave LAB_SHADOW on in controlled envs |
| **Dependencies** | Phases 1–5 |
| **Risks** | Incomplete regression → enforce checklist |
| **Validation** | All SC-001–SC-008; DoD |
| **Deliverables** | Test evidence, runbook notes, readiness sign-off |

**Phase order rationale**: Registration → pipeline/persist (core value + safety) → paper → analytics → UI can partially parallelize after APIs exist, but **pipeline+persist before UI**; **validation continuous**, final gate in Phase 6.

---

## 14. Assumptions

1. Clarify session decisions remain binding for MVP.
2. RE-001 Docs 03–05 remain unpublished; strategy parameter defaults are conservative and versioned in config.
3. Existing regime/permission outputs can be mapped to Bull/Sideways/Bear via a documented mapping table (planning research).
4. Shortlist size remains the performance envelope.
5. Multi-engine future will reuse Decision Object + engine_id without redesign.
6. Promotion to production shortlist is a **separate future feature**.
7. LLM text assist may remain optional and never sets RecommendationState.
8. Portfolio validation uses the authenticated requesting user’s paper/risk snapshot when present; if none (including scheduler runs), fail-closed for BUY (WATCH/REJECT) with `portfolio_context_unavailable` without inventing portfolio state (FR-026).
9. Paper trade guidance: RE-001 complete trade guidance preferred; else production `trade_plans` for same symbol/scan; provenance always RE-001 when lab-originated (FR-015).
10. Feature permission key is exactly `recommendation_lab`.
11. `scan_run_id` maps to existing completed-scan / latest-scan identity family (FR-027).

---

## 15. Constraints

- Do **not** redesign the existing recommendation engine.
- Do **not** change scanner behavior, TA calculations, AI agent decision ownership, paper fill logic, analytics production formulas, or scheduler job semantics.
- Do **not** change existing production business rules/thresholds.
- Long-only, swing, NIFTY500 intent, advisory-only.
- Backward-compatible APIs.
- Additive DB only.
- Default OFF.
- RE-001 evaluation set = shortlist/full-analysis only.

---

## 16. Out of Scope

- Auto-promotion of RE-001 to production shortlist authority.
- Live broker execution.
- RE-002…RE-007 engines.
- Mean reversion / event / gap / news-primary / earnings / short / pure intraday engines.
- Full multi-engine Lab product console / strategy library marketplace UI.
- Rewriting market data, scanner vectorization, paper market engine.
- Publishing RE-001 Documents 03–05 (external).
- New shared REDS architecture layers (REDS locked).
- Generating `tasks.md` (use `/speckit-tasks`), implementation code, SQL scripts, API implementation code.

---

## 17. Definition of Done (Planning → Implementation handoff)

Planning is complete when:

1. This plan is accepted as master integration roadmap.
2. `research.md` resolves technical unknowns for MVP.
3. `data-model.md` and `contracts/*` define Decision Object + lab interfaces.
4. `quickstart.md` defines validation scenarios for implementers.
5. Component classification and phase roadmap are unambiguous for `/speckit-tasks`.

Implementation (later) is complete when feature **spec** Definition of Done and SC-001–SC-008 are met (see `spec.md` §18).

---

## Phase 0 / Phase 1 Artifact Index

| Artifact | Path | Role |
| -------- | ---- | ---- |
| Research | [research.md](./research.md) | Decisions & alternatives |
| Data model | [data-model.md](./data-model.md) | Entities & validation rules |
| Contracts | [contracts/](./contracts/) | Decision Object, Lab API, UI |
| Quickstart | [quickstart.md](./quickstart.md) | Validation scenarios |

---

## Files Expected to Change (planning inventory only)

| Area | Touch type |
| ---- | ---------- |
| `backend/app/config/settings.py` | EXTEND flags |
| `backend/app/agents/orchestrator_agent.py` | EXTEND isolated hook |
| `backend/app/services/re001/*` | NEW engine package |
| `backend/app/models/*` (decisions) | NEW |
| `backend/app/schemas/*` | EXTEND DTOs |
| `backend/app/routes/*` | EXTEND lab reads / analytics dim |
| `backend/app/services/paper_trading_service.py` + paper routes | EXTEND provenance |
| Alembic tree | Additive migration |
| Frontend detail / lab / nav / api / feature catalog | EXTEND/NEW UI surfaces |
| Tests unit/integration/regression | NEW + KEEP existing |

**Explicit non-touch (behavior)**: screener scoring formulas, TA calculation formulas, production recommendation score matrix, paper fill engine, scheduler cron definitions (beyond natural pipeline piggyback), AI agent ownership of labels.
