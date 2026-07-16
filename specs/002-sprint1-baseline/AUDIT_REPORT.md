# Production Readiness Audit Report

**Feature**: Sprint 1 – Baseline & Diagnostics (Phase 0)  
**Branch / Spec**: `002-sprint1-baseline`  
**Spec source of truth**: `specs/002-sprint1-baseline/spec.md`  
**Audit prompt**: `Document/Audit.md`  
**Audit date**: 2026-07-16  
**Auditor role**: Principal Software Architect / Reliability Engineer (read-only)

---

## Executive Summary

**Overall production readiness: FAIL**

The feature is largely scaffolded and task-checked in `tasks.md`, but several defects block production use of core paths:

- Experiment lifecycle does not reliably persist (no commit; sync methods incorrectly awaited).
- No Alembic migration for the `experiments` table.
- API key auth dependency does not reject unauthorized requests.
- Alert rules are not evaluated on a runtime schedule.
- The automated test suite cannot currently import the application (`Settings` Pydantic error).
- Quickstart validation (**T039**) remains incomplete.

**Final recommendation: REJECT IMPLEMENTATION**

Do not proceed to hardening until critical and high findings are remediated and re-verified.

---

## Scope Reviewed

| Artifact | Path |
|----------|------|
| Specification | `specs/002-sprint1-baseline/spec.md` |
| Plan | `specs/002-sprint1-baseline/plan.md` |
| Tasks | `specs/002-sprint1-baseline/tasks.md` |
| Data model | `specs/002-sprint1-baseline/data-model.md` |
| Contracts | `specs/002-sprint1-baseline/contracts/api.md`, `cli.md` |
| Quickstart / benchmark | `quickstart.md`, `benchmark.py` |
| Governance | `backend/app/governance/*`, `AGENTS.md` |
| Observability | `backend/app/observability/*`, `backend/app/routes/diagnostics.py` |
| Core stores | `backend/app/core/jsonl_store.py`, `audit_store.py`, `disk_utils.py` |
| Model | `backend/app/models/experiment.py` |
| Frontend | `frontend/src/pages/Diagnostics.tsx`, `components/Diagnostics/*` |
| Tests | `backend/app/tests/governance/*`, `observability/*`, `frontend/src/tests/Diagnostics.test.tsx` |

---

## Findings

### Critical

#### C1 — ExperimentService never commits transactions
- **Description**: Lifecycle methods only call `await self.db.flush()`. CLI opens `AsyncSessionLocal()` without an explicit commit. SQLAlchemy sessions do not auto-commit on close.
- **Why it matters**: Create/pause/resume/complete will not persist after the session ends. US1 is non-functional in production.
- **Severity**: Critical
- **Recommended action**: Commit after successful mutations (or use an explicit transaction context); rollback on error.

#### C2 — `await` used on synchronous ExperimentLog methods
- **Description**: `ExperimentService` uses `await self.log.log_event(...)` and `await self.log.log_metric(...)`, but `ExperimentLog.log_event` / `log_metric` are synchronous.
- **Why it matters**: Raises `TypeError` mid-lifecycle after audit write; create/complete paths crash.
- **Severity**: Critical
- **Recommended action**: Remove incorrect `await`, or make log methods async and keep I/O non-blocking as appropriate.

#### C3 — No Alembic migration for `experiments`
- **Description**: No migration under `backend/alembic/versions` creates the `experiments` table / enum.
- **Why it matters**: Deployed databases lack the table; experiment CRUD fails at runtime.
- **Severity**: Critical
- **Recommended action**: Add migration matching `data-model.md` (columns, enum, indexes).

#### C4 — Reserved SQLAlchemy attribute name `metadata` on Experiment model
- **Description**: Model maps `metadata: Mapped[...] = mapped_column(JSONB)`. Project convention elsewhere is `metadata_ = mapped_column("metadata", ...)`.
- **Why it matters**: Risk of Declarative `MetaData` shadowing / mapper issues; inconsistent with existing models.
- **Severity**: Critical
- **Recommended action**: Rename attribute to `metadata_` (or similar) with column name `"metadata"`.

#### C5 — `verify_api_key` does not enforce authentication
- **Description**: Dependency takes `authorization: str = ""` without `Header(...)`, returns `False` without raising `HTTPException(401)`. Returning `False` does not reject the request.
- **Why it matters**: NFR-005 is not met when `API_KEY` is set; dashboard APIs are not gated.
- **Severity**: Critical
- **Recommended action**: Inject Authorization header; raise 401 on missing/invalid key; align with existing security patterns.

#### C6 — Test suite cannot import the application
- **Description**: Loading conftest / `app.main` fails with Pydantic `Settings` decorator error on `_normalize_exec_model`.
- **Why it matters**: SC-008 and regression suite cannot run; production readiness unprovable.
- **Severity**: Critical
- **Recommended action**: Fix Settings field/decorator mismatch so governance and observability tests execute.

---

### High

#### H1 — Alert evaluation not scheduled in runtime
- **Description**: `AlertEngine.evaluate` exists and is unit-tested, but no scheduler/route continuously evaluates metric streams against rules.
- **Why it matters**: FR-008 / SC-005 / FR-013 will not produce live alerts or dashboard warnings.
- **Severity**: High
- **Recommended action**: Wire APScheduler (or metrics path) to evaluate system metrics on a short interval.

#### H2 — Frontend diagnostics omit API key
- **Description**: Panels fetch with `credentials: "include"` only; no Bearer / API key header.
- **Why it matters**: Dashboard fails once auth is correctly enforced.
- **Severity**: High
- **Recommended action**: Use shared API client / auth header consistent with the rest of the frontend.

#### H3 — CLI CSV audit export ignores date filters
- **Description**: JSON export uses filtered `audit.query(...)`; CSV path calls `export_csv()` with no `--since`/`--until`.
- **Why it matters**: FR-011 incorrect for CSV; partial audit exports wrong.
- **Severity**: High
- **Recommended action**: Apply the same filters for both formats.

#### H4 — CLI audit export buffers entire dataset
- **Description**: CLI builds full string via `json.dumps` / `export_csv` despite streaming helpers on `AuditStore`.
- **Why it matters**: Large export OOM risk (spec edge case / T033).
- **Severity**: High
- **Recommended action**: Stream to file/stdout using existing streaming helpers.

#### H5 — Single-active experiment race
- **Description**: Application checks `_get_active()` then inserts without row lock or partial unique index on `status = 'active'`.
- **Why it matters**: Concurrent starts can create multiple active experiments.
- **Severity**: High
- **Recommended action**: `SELECT … FOR UPDATE` and/or partial unique index; handle integrity errors.

#### H6 — Benchmark SC-001 references non-existent `AgentRouter`
- **Description**: `benchmark.py` imports `AgentRouter`, which is not implemented (`get_route` / `list_routes` exist instead).
- **Why it matters**: SC-001 performance verification fails as written.
- **Severity**: High
- **Recommended action**: Align benchmark with actual router API.

#### H7 — T039 quickstart validation incomplete
- **Description**: Tasks mark T039 unchecked; end-to-end quickstart not validated.
- **Why it matters**: Acceptance scenarios unproven.
- **Severity**: High
- **Recommended action**: Run `quickstart.md` scenarios; fix failures; mark T039 complete only after green.

#### H8 — Log retention rotation not scheduled
- **Description**: `archive_older_than` / `rotate_old_files` exist but are not invoked by a job.
- **Why it matters**: NFR-004 (90-day retention) not operationally enforced.
- **Severity**: High
- **Recommended action**: Schedule retention job or document explicit Phase 0 manual process.

---

### Medium

| ID | Description | Why it matters | Recommended action |
|----|-------------|----------------|--------------------|
| M1 | Disk-full handling is warn-only; `JsonlStore.append` does not enforce space check | Storage-full edge case weak | Use hard fail (`ensure_disk_space`) before append |
| M2 | Dashboard logs `total` is `len(entries)` after limit, not full match count | Incorrect pagination metadata | Use `count()` for `total` |
| M3 | `/metrics/prometheus` returns JSON, not Prometheus text | Scrapers cannot use endpoint | Emit exposition format or rename |
| M4 | Agent routing is static map only; no in-process command execution | FR-012 / AGENTS.md claim incomplete | Document Phase 0 scope or implement safe dispatch |
| M5 | Name uniqueness not case-insensitive | Diverges from data-model | Functional unique index or normalize names |
| M6 | Naive `utcnow` in experiment events vs aware UTC elsewhere | Filter/order skew | Standardize timezone-aware UTC |
| M7 | “Per-experiment” resources are whole-process metrics | FR-009 / SC-007 attribution weak | Document process proxy; optional windowing |
| M8 | Governance `/routes` unauthenticated | Command surface disclosure | Apply admin auth |
| M9 | Alert dedup state in-memory only | Restart / multi-worker duplicates | Accept Phase 0 or persist last-fire |
| M10 | Rate-limit store process-local | Weak under multi-worker | Accept Phase 0 or shared limiter |

---

### Low

| ID | Description | Recommended action |
|----|-------------|--------------------|
| L1 | Lifecycle log events not validated via `LogEventCreate` | Validate through schema |
| L2 | `MetricObservationCreate` validated then partially unused | Persist model dump |
| L3 | LogViewer lacks time-range UI (API supports it) | Optional time-range controls |
| L4 | Quickstart scenario 3 uses invalid `start --id` | Fix quickstart docs |
| L5 | No evidence of >80% coverage (SC-008) | Run coverage after import fix |
| L6 | Duplicate duration formatting service/CLI | Share utility |

---

## Risk Assessment

| Area | Level | Notes |
|------|-------|-------|
| Architecture Risk | MEDIUM | Layout matches plan; alert pipeline and agent dispatch incomplete |
| Production Risk | HIGH | Commit/async/migration defects break US1 |
| Security Risk | HIGH | Auth dependency non-enforcing |
| Performance Risk | MEDIUM | JSONL scans acceptable for Phase 0 scale if verified |
| Maintainability Risk | MEDIUM | Clear modules; broken import path blocks verification |

---

## Missing Requirements

| Requirement | Gap |
|-------------|-----|
| FR-002 / US1 lifecycle | Logic present; blocked by C1/C2/C3 |
| FR-003 experiment persistence | Migration + commit missing |
| FR-008 alert evaluation on streams | No runtime loop |
| FR-009 per-experiment resources | Process proxy only |
| FR-011 audit export JSON/CSV | CSV filter + streaming gaps |
| FR-012 agent activation workflow | Static route table only |
| FR-013 resource threshold warnings | Depends on H1 |
| NFR-001–NFR-004 performance/retention | Unverified / not scheduled |
| NFR-005 authentication | C5 |
| NFR-006 99.9% availability | Not evidenced |
| SC-001–SC-007 | Benchmark broken / suite import fail |
| SC-008 coverage | Cannot measure |

---

## Missing Tests

1. Integration: CLI start → committed DB row → list/complete  
2. Regression: lifecycle does not raise on log write (C2)  
3. Migration smoke: `experiments` table exists  
4. Auth: missing/wrong key → 401 on dashboard APIs  
5. Auth: frontend/API client sends credentials when required  
6. E2E: metric breach → scheduled evaluate → GET `/alerts`  
7. Concurrent create → only one active  
8. CSV export respects date filters  
9. Streaming export under large fixture  
10. Disk-full / low-space failure path  
11. Pagination `total` correctness  
12. Coverage report for SC-008  
13. Working SC-001 benchmark against real router  
14. Automated or documented quickstart (T039)

---

## Production Readiness Checklist

| Area | Status |
|------|--------|
| Specification compliance | ❌ Failed |
| Architecture preservation | ⚠ Needs Attention |
| Code quality | ⚠ Needs Attention |
| Production safety | ❌ Failed |
| Concurrency | ❌ Failed |
| Database | ❌ Failed |
| Performance | ⚠ Needs Attention |
| Security | ❌ Failed |
| Observability | ⚠ Needs Attention |
| Testing | ❌ Failed |
| Quickstart / e2e validation | ❌ Failed |

---

## Final Recommendation

**REJECT IMPLEMENTATION**

Not approved for hardening. Remediate all **Critical** and **High** findings, re-run unit/integration/quickstart validation, then re-audit.

See companion: `REMEDIATION_TASKS.md`.
