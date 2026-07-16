# Remediation Tasks — 002-sprint1-baseline

**Source audit**: `specs/002-sprint1-baseline/AUDIT_REPORT.md`  
**Date**: 2026-07-16  
**Goal**: Clear **REJECT IMPLEMENTATION** by fixing Critical + High findings, then re-verify before hardening.

**Rules**: Prefer minimal, targeted fixes. Do not redesign architecture. Keep Phase 0 file-based storage and single-admin model.

---

## Priority legend

| Priority | Meaning |
|----------|---------|
| P0 | Must fix before any other work is trustworthy |
| P1 | Required for production readiness / hardening gate |
| P2 | Should fix before hardening if time allows |
| P3 | Nice-to-have / polish |

---

## Wave 0 — Unblock the codebase (P0)

### R-001 [P0] [C6] Fix Settings import so the app and tests load
- **Problem**: Pydantic `Settings` decorator error on `_normalize_exec_model` blocks `app.main` and conftest.
- **Work**:
  - Inspect `backend/app/config/settings.py` around the failing decorator.
  - Align field name with decorator (or set `check_fields=False` only if intentional inheritance).
  - Confirm `python -c "from app.main import app"` and a single pytest collection succeed.
- **Done when**: `pytest app/tests/governance/ --collect-only` and `pytest app/tests/observability/ --collect-only` succeed without import errors.
- **Evidence**: paste successful collect/import output.

### R-002 [P0] [C2] Fix async/await misuse on ExperimentLog
- **Files**: `backend/app/governance/experiment.py`, `backend/app/governance/experiment_log.py`
- **Work**:
  - Either remove `await` on `log_event` / `log_metric`, or make those methods async consistently.
  - Prefer non-breaking choice: sync call without await unless I/O must be offloaded.
- **Done when**: Creating an experiment does not raise `TypeError` on log write.
- **Test**: unit test covering create → log write path.

### R-003 [P0] [C1] Commit experiment lifecycle transactions
- **Files**: `backend/app/governance/experiment.py`, `backend/app/governance/experiment_cli.py`
- **Work**:
  - After successful create/pause/resume/complete/fail (and optionally metric if needed), `await self.db.commit()` **or** use an explicit transaction boundary the CLI always commits.
  - Ensure rollback on exception.
  - Do not leave success path as flush-only.
- **Done when**: CLI `start` leaves a durable row visible in a new session/`list`.
- **Test**: integration test: create in one session, read in another.

### R-004 [P0] [C4] Rename Experiment `metadata` attribute
- **Files**: `backend/app/models/experiment.py`, any callers using `.metadata`
- **Work**:
  - Follow project pattern: `metadata_: Mapped[...] = mapped_column("metadata", JSONB, ...)`.
  - Update service/CLI/tests that set `metadata=...`.
- **Done when**: Model maps cleanly; create with metadata works.
- **Test**: create with metadata dict; read back.

### R-005 [P0] [C3] Add Alembic migration for `experiments`
- **Files**: new migration under `backend/alembic/versions/`, model as source of truth
- **Work**:
  - Create table `experiments` with columns from `data-model.md`.
  - Create enum `experiment_status` (`active`, `paused`, `completed`, `failed`).
  - Indexes on `name`, `status` as appropriate.
  - Verify `alembic upgrade head` on clean DB.
- **Done when**: Table exists post-migration; app can insert experiments.
- **Test**: migration upgrade/downgrade smoke or integration create after upgrade.

---

## Wave 1 — Security & runtime correctness (P0/P1)

### R-006 [P0] [C5] Enforce API key authentication properly
- **Files**: `backend/app/core/security.py`, `backend/app/routes/diagnostics.py`
- **Work**:
  - Inject Authorization via FastAPI `Header` (or existing project pattern).
  - Raise `HTTPException(401)` when key required and missing/invalid.
  - When `API_KEY` unset, document Phase 0 open mode (current allow-all) if intentional.
- **Done when**: With `API_KEY=secret`, unauthenticated dashboard calls return 401; valid Bearer succeeds.
- **Test**: 401 without key; 200 with correct key.

### R-007 [P1] [H2] Frontend diagnostics auth
- **Files**: `frontend/src/components/Diagnostics/*`, shared API client if present
- **Work**:
  - Send the same auth headers used by the rest of the app (Bearer API key / session token).
  - Keep credentials behavior consistent with CORS and cookie auth if used.
- **Done when**: Diagnostics panels load against an auth-enabled backend.
- **Test**: frontend test or manual quickstart with API_KEY set.

### R-008 [P1] [H1] Wire continuous alert evaluation
- **Files**: alert engine, scheduler integration (existing APScheduler), optionally dashboard metrics path
- **Work**:
  - Periodically sample system metrics (CPU, memory, error rate, etc.).
  - Call `AlertEngine.evaluate` / `evaluate_batch`.
  - Persist alerts; surface on GET `/api/v1/dashboard/alerts`.
  - Target: evaluation within NFR-002 (10s of breach).
- **Done when**: Threshold breach produces an alert without manual evaluate calls.
- **Test**: unit + integration: force metric over threshold → alert appears.

### R-009 [P1] [H5] Enforce single-active at DB/concurrency layer
- **Files**: migration, `ExperimentService.create`
- **Work**:
  - Prefer partial unique index: only one row with `status = 'active'` (PostgreSQL).
  - Optionally `SELECT … FOR UPDATE` on active lookup inside a transaction.
  - Map integrity errors to `SingleActiveConstraintError`.
- **Done when**: Concurrent create attempts cannot leave two active experiments.
- **Test**: concurrent create test or DB constraint test.

---

## Wave 2 — Export, retention, verification (P1)

### R-010 [P1] [H3] Fix CLI CSV audit export filters
- **Files**: `backend/app/governance/experiment_cli.py`, `audit.py` / `audit_store.py` if needed
- **Work**: Apply `--since` / `--until` to CSV the same as JSON.
- **Done when**: Filtered CSV only includes events in range.
- **Test**: seed events across dates; assert CSV filter.

### R-011 [P1] [H4] Stream large audit exports
- **Files**: `experiment_cli.py`, use `export_json_to_file` / `export_csv_to_file` (or stdout streaming)
- **Work**: Avoid loading multi-MB export fully into one string when writing to file.
- **Done when**: Export path uses streaming helpers for file output.
- **Test**: large fixture export completes without buffering entire string in CLI if feasible.

### R-012 [P1] [H6] Fix benchmark SC-001
- **Files**: `specs/002-sprint1-baseline/benchmark.py`
- **Work**: Replace `AgentRouter` with `get_route` / `list_routes` (or real dispatch once implemented).
- **Done when**: `python specs/002-sprint1-baseline/benchmark.py` runs SC-001 without ImportError.
- **Evidence**: benchmark output for SC-001–SC-007.

### R-013 [P1] [H8] Schedule or document log retention
- **Files**: scheduler config or ops docs; `jsonl_store` rotation
- **Work**:
  - Prefer: daily job calling `rotate_old_files(90)` for log aggregator / experiment logs / alerts.
  - Or document manual Phase 0 retention runbook if job deferred.
- **Done when**: Retention either automated or explicitly owned in ops docs for Phase 0.
- **Test**: unit already on rotate if present; add if missing.

### R-014 [P1] [H7] Complete T039 quickstart validation
- **Files**: `specs/002-sprint1-baseline/quickstart.md`, `tasks.md`
- **Work**:
  - Run all quickstart scenarios after Waves 0–1.
  - Fix L4 quickstart invalid `start --id` while editing.
  - Check off T039 only when all scenarios pass.
- **Done when**: Quickstart scenarios 1–7 pass; T039 marked complete in `tasks.md`.
- **Evidence**: command outputs or short validation note in audit follow-up.

---

## Wave 3 — Spec gaps & quality (P2)

### R-015 [P2] [M1] Hard-fail on low disk space for appends
- Call `ensure_disk_space` (or equivalent) in `JsonlStore.append` / audit append paths.
- Test: mock low free space → OSError / clean failure.

### R-016 [P2] [M2] Fix dashboard logs `total` count
- Use aggregator `count()` for total; keep page in `entries`.
- Test: 20 events, limit 5 → `total == 20`, `len(entries) == 5`.

### R-017 [P2] [M3] Prometheus format or rename endpoint
- Either emit text exposition format or rename to avoid claiming Prometheus compatibility.

### R-018 [P2] [M4] Clarify or implement agent dispatch
- Document Phase 0 as route-lookup only **or** implement safe in-process dispatch per AGENTS.md.
- Update FR-012 acceptance notes if documenting scope reduction.

### R-019 [P2] [M5] Case-insensitive experiment name uniqueness
- Functional unique index / normalize to lower case on write.

### R-020 [P2] [M6] Timezone-aware timestamps everywhere
- Replace naive `datetime.utcnow()` in experiment log events with `datetime.now(timezone.utc)`.

### R-021 [P2] [M7/M8] Document process-level resource attribution; auth on `/governance/routes`
- Docs for FR-009 Phase 0 proxy semantics.
- Apply auth dependency to governance router if admin-only.

### R-022 [P2] Missing tests pack
Add automated tests listed in AUDIT_REPORT “Missing Tests” § items 1–14 as applicable after P0/P1.

### R-023 [P2] [L5] [SC-008] Coverage report
- Run coverage on governance + observability modules.
- Record result; target >80% or document shortfall with waiver.

---

## Wave 4 — Polish (P3)

| ID | Task |
|----|------|
| R-024 | Validate lifecycle logs via `LogEventCreate` (L1) |
| R-025 | Use full `MetricObservationCreate` dump when logging metrics (L2) |
| R-026 | Optional LogViewer time-range UI (L3) |
| R-027 | Deduplicate duration formatting (L6) |
| R-028 | Alert dedup persistence / multi-worker note (M9) |
| R-029 | Rate-limit multi-worker note (M10) |

---

## Suggested execution order

```text
R-001 (import)
  → R-002 (await)
  → R-004 (metadata_)
  → R-005 (migration)
  → R-003 (commit)
  → R-006 (auth enforce)
  → R-007 (frontend auth)
  → R-008 (alert loop)
  → R-009 (single-active DB)
  → R-010, R-011 (export)
  → R-012 (benchmark)
  → R-013 (retention)
  → R-014 (quickstart / T039)
  → Wave 3 tests + coverage
  → Re-audit → HARDENING only if Critical/High cleared
```

---

## Definition of Done (feature re-approval gate)

All of the following must be true:

- [ ] No open **Critical** findings (C1–C6)
- [ ] No open **High** findings (H1–H8)
- [ ] `pytest app/tests/governance/ app/tests/observability/ -v` green
- [ ] Quickstart scenarios pass (T039)
- [ ] `benchmark.py` runs; SC-001–SC-007 results recorded
- [ ] Coverage measured for governance + observability (SC-008)
- [ ] Fresh audit status is at least **PASS WITH MINOR ISSUES**
- [ ] Recommendation upgrades from **REJECT** to **APPROVED FOR HARDENING**

---

## Out of scope (do not do during remediation)

- Architectural redesign or new microservices
- Database-backed audit/log storage (Phase 1 per spec assumptions)
- Email/webhook alert delivery (Phase 1)
- Multi-role RBAC beyond single admin (Phase 0)
- Implementing unrelated product features outside 002-sprint1-baseline

---

## Tracking

| Wave | Task IDs | Status |
|------|----------|--------|
| 0 Unblock | R-001 … R-005 | **done** (2026-07-16) |
| 1 Security & runtime | R-006 … R-009 | **done** (auth, alerts, single-active index) |
| 2 Export & verification | R-010 … R-014 | **partial** (export/benchmark/retention done; T039 quickstart manual remaining) |
| 3 Spec gaps | R-015 … R-023 | **done** (disk hard-fail, logs total, timezone, FEAT-008 settings, tracker, schema) |
| 4 Polish | R-024 … R-029 | optional |
| Regression fixes | R-H1/H2, R-M1/M3, R-L1/L3 | **done** — gov/obs **209 passed**; FEAT-008 filter **120 passed** |

Update this table as work completes. After Wave 2, re-run audit prompt from `Document/Audit.md` against the same spec.
