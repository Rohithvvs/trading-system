# Production Readiness Audit: Scanner Dashboard Cache

**Feature**: `017-scanner-dashboard-cache`  
**Audit Date**: 2026-07-27  
**Auditor Role**: Principal Software Architect / Reliability / Production Code Auditor  
**Source of Truth**: `specs/017-scanner-dashboard-cache/spec.md`  
**Test Run**: `57 passed, 1 skipped, 1 xfailed` (cache-related suite)

---

## Executive Summary

Overall production readiness: **PASS WITH MAJOR ISSUES**

The feature delivers the core cache-aside path for both target endpoints, feature-flag bypass, force-refresh, Redis timeout/error soft-fallback (HTTP 200), empty-result short TTL, and a solid unit/integration test surface. However, several **specification-critical behaviors are incomplete or broken in production paths**:

1. **Active pre-warming is effectively dead** (`json.dumps` used without `import json` in `scan_store.py`; swallowed by try/except).
2. **Even if fixed, pre-warm for `scanner:latest:v1` writes the wrong payload shape** (scan_store JSONB vs `LatestScanService` dashboard schema).
3. **Singleflight exists but is not wired into route handlers** → stampede protection is not live on HTTP traffic.
4. **Prometheus metrics are defined but never incremented** → hit/miss/error/ratio observability is non-functional.
5. **Contract header `X-Cache-Status: FALLBACK` is never emitted**; corrupted-cache eviction path is missing.

These are not pure style issues; they undermine FR-005, FR-009, FR-010, SC-004, and operational rollout monitoring.

---

## Findings

### Critical

#### C1 — Active pre-warming silently fails (missing `import json`)

- **Description**: `backend/app/db/scan_store.py` `save_latest_scan()` post-commit pre-warm block calls `json.dumps(...)` but the module does not import `json`. The `NameError` is caught by the surrounding `try/except`, logged as a warning, and pre-warm is skipped.
- **Why it matters**: FR-005 / User Story 2 require immediate `SET` of `scanner:latest:v1` and `analysis:scan:latest:v1` after scan completion so the first post-scan dashboard request is a HIT. Production never pre-warms; first request always misses (or serves stale TTL data).
- **Severity**: Critical
- **Evidence**: Module imports are only `logging`, `time`, `typing`, `orjson`, `sqlalchemy`; tests document this as xfail (`test_prewarm_block_references_json_module`).
- **Recommended action**: Import `json` (or use `orjson.dumps` consistently) so pre-warm actually runs; add a regression test that fails if pre-warm is skipped due to NameError.

#### C2 — Pre-warm payload for `scanner:latest:v1` does not match `/scanner/latest` response schema

- **Description**: On pre-warm success path, `scanner:latest:v1` is filled with `jsonb_payload` from `_normalize_scan_payload` / `scan_results` (ScreenerResponse-like structure). `GET /scanner/latest` (miss path) builds responses via `LatestScanService.get_latest_completed_scan()` from `scan_snapshots` + `scan_snapshot_records` with fields such as `scan_id`, `buy_candidates[]` (symbol/score/rsi/…), `buy_count`, etc.
- **Why it matters**: After a scan, a cache HIT could return a structurally different body than the DB path — violating SC-003 (100% schema parity) and the “API contract 100% unchanged” guarantee. Dashboard clients may break or show wrong fields.
- **Severity**: Critical
- **Evidence**: `scan_store.save_latest_scan` SETs `scanner:latest:v1` to normalized scan_store payload; `routes/scanner.py` miss path serializes `LatestScanService` result.
- **Recommended action**: Pre-warm `scanner:latest:v1` with the exact serialized output of the same builder used by the route (`LatestScanService` shape), or stop pre-warming that key and only pre-warm `analysis:scan:latest:v1` if shapes cannot be unified. Add parity assertion: post-prewarm HIT body == forced DB body.

---

### High

#### H1 — Singleflight not integrated into HTTP handlers (FR-010 / SC-004 unmet in production)

- **Description**: `ScannerCacheService.execute_singleflight()` implements in-process lock + re-check, and unit/stampede tests cover it. Route handlers (`scanner.py`, `analysis.py`) never call it; they do open GET → on None, always query DB → SET.
- **Why it matters**: Concurrent misses (TTL expiry, cold start, multi-tab dashboards) each hit PostgreSQL independently. Spec requires max one DB fetch under stampede; production path does not enforce this.
- **Severity**: High
- **Recommended action**: Route miss/refill path must go through `execute_singleflight` (or equivalent) so concurrent requests share one DB fetch; add route-level concurrent test (not only service-level).

#### H2 — Observability metrics never instrumented (spec §16)

- **Description**: `metrics.py` defines `scanner_cache_hits_total`, `scanner_cache_misses_total`, `scanner_cache_redis_errors_total`, `scanner_cache_hit_ratio`. No production code path calls `.labels(...).inc()` / `.set()`. Missing entirely: `scanner_cache_force_refreshes_total` and cache-aware latency histogram labels.
- **Why it matters**: Rollout Stage 4 depends on hit ratio, Redis errors, and latency. Operators cannot detect silent fallback storms or confirm >90% hit ratio (SC-002 monitoring).
- **Severity**: High
- **Recommended action**: Increment counters on HIT/MISS/BYPASS/FALLBACK/force and Redis op errors; maintain hit-ratio gauge; add force-refresh counter.

#### H3 — Redis failure not distinguished as `X-Cache-Status: FALLBACK`

- **Description**: Contract allows `HIT | MISS | BYPASS | FALLBACK`. On Redis connection/timeout, service returns `None`; routes label status as `MISS` (or `BYPASS` if disabled). Tests explicitly allow either FALLBACK or MISS.
- **Why it matters**: Ops cannot distinguish cold miss vs Redis outage from headers alone; FR-009 expects logged **metric** + fallback semantics; contract documents FALLBACK for this case.
- **Severity**: High
- **Recommended action**: Propagate error vs miss from cache service (or raise typed exceptions that routes map to FALLBACK without 5xx); set header + error metric.

#### H4 — Corrupted cache JSON not validated, not evicted (Edge Case / Failure Matrix)

- **Description**: HIT path returns Redis string as `Response(content=cached_payload)` with no `json.loads` validation and no `DEL` on corruption.
- **Why it matters**: Spec requires: log error → delete corrupted key → query DB & refill. Clients can receive invalid JSON until TTL expires.
- **Severity**: High
- **Recommended action**: On HIT, validate JSON; on failure, invalidate key, fall back to DB, refill.

#### H5 — Feature-flag “dynamic zero-restart rollback” not actually dynamic

- **Description**: `SCANNER_LATEST_CACHE_ENABLED` is read from process `settings` singleton at import/load. Changing the env var alone does not refresh in-process settings without restart/reload.
- **Why it matters**: Spec §18.2 claims instantaneous revert “without requiring code redeployment or container restart.” Current design needs process restart (or undocumented settings mutation).
- **Severity**: High (operational safety claim)
- **Recommended action**: Document restart requirement honestly, or add runtime config reload / admin toggle that mutates live `settings.scanner_latest_cache_enabled`.

---

### Medium

#### M1 — In-process singleflight only (multi-worker stampede)

- **Description**: Locks are `asyncio.Lock` on a process-local dict. Spec lock key names (`lock:scanner:latest:v1`) imply Redis-level locks; multi-worker/multi-instance deployments still stampede across processes even after H1 is fixed.
- **Why it matters**: Production typically runs >1 Uvicorn worker; SC-004 “exactly one DB query” fails across workers.
- **Severity**: Medium
- **Recommended action**: Document single-process scope, or implement Redis/distributed singleflight if multi-worker is production default.

#### M2 — Redis client lifecycle incomplete vs plan

- **Description**: Plan calls for async pool + FastAPI lifespan hooks. Implementation uses module-level `redis.from_url` with no connect timeout pool kwargs, no app lifespan init/close, and optional lazy recreate in `get_redis_client()`.
- **Why it matters**: Connection leaks/hangs on shutdown; no explicit health bound for connect phase separate from op timeouts.
- **Severity**: Medium
- **Recommended action**: Wire init/close in lifespan; set socket/connect timeouts aligned with read/write budgets.

#### M3 — Settings validation gaps vs data-model

- **Description**: Data model requires TTL ≥ 10, read timeout ≥ 5, write timeout ≥ 10. Settings fields accept any int (including 0/negative) without validators.
- **Why it matters**: Misconfiguration can disable caching semantics or wait_for edge behavior.
- **Severity**: Medium
- **Recommended action**: Add pydantic `ge=` constraints matching data-model.md.

#### M4 — Dead exception types

- **Description**: `RedisCacheTimeoutException` / `RedisCacheConnectionException` are defined but never raised; service swallows all errors to `None`.
- **Why it matters**: Callers cannot distinguish miss vs error without parsing logs; blocks FALLBACK header and metrics (H3).
- **Severity**: Medium
- **Recommended action**: Raise or return a typed result object used by routes.

#### M5 — Documentation task incomplete

- **Description**: T024 claims update to `backend/README.md`; file is absent / not updated with cache ops notes.
- **Why it matters**: Operators lack in-repo enablement guidance outside specs/quickstart.
- **Severity**: Medium
- **Recommended action**: Document env vars, headers, rollback, and metrics in the active backend docs location.

#### M6 — Force-refresh header status always `MISS`

- **Description**: Force path correctly bypasses read and rewrites cache, but status is always `MISS` when enabled (never a distinct value). Quickstart allows MISS/BYPASS; acceptable but weak for ops counting force usage without metric H2.
- **Severity**: Medium (ops clarity)
- **Recommended action**: Prefer force counter metric; optional dedicated status only if contract is extended.

---

### Low

#### L1 — Unused imports / minor route duplication

- **Description**: Cache control parsing and status selection duplicated across `scanner.py` and `analysis.py`; force branch ternary is redundant (`"MISS" if not force else "MISS"`).
- **Why it matters**: Maintainability drift risk between endpoints.
- **Severity**: Low
- **Recommended action**: Shared helper for directive + status mapping.

#### L2 — Spec metric name inconsistency (documentation only)

- **Description**: FR-009 text uses `scanner_cache_redis_error_total`; §16 and code use `scanner_cache_redis_errors_total`.
- **Severity**: Low
- **Recommended action**: Align FR-009 wording to plural form used in implementation.

#### L3 — Exception module unused by service layer

- **Description**: Custom exceptions unused; low impact beyond M4.
- **Severity**: Low

---

## Risk Assessment

| Area | Risk | Notes |
|---|---|---|
| Architecture Risk | **MEDIUM** | Cache service isolation is good; dual data sources (scan_results vs scan_snapshots) create pre-warm schema risk. |
| Production Risk | **HIGH** | Pre-warm broken; stampede unprotected on routes; metrics dark; possible wrong HIT payload after pre-warm fix without C2 fix. |
| Security Risk | **LOW** | Caches same public read payloads; no secrets in keys; force/bypass not auth-gated (pre-existing open read endpoints). |
| Performance Risk | **MEDIUM–HIGH** | Hits work when populated via miss path; stampede and multi-worker can erase DB-load reduction under expiry spikes. |
| Maintainability Risk | **MEDIUM** | Duplicated route logic; dead APIs (exceptions, singleflight unused by routes); tests paper over some defects (xfail, FALLBACK or MISS). |

---

## Missing Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-005 | Active pre-warm SET both keys on scan completion | **Missing in practice** (C1 NameError); analysis shape OK if fixed; scanner key shape wrong (C2) |
| FR-009 | Structured warning **metric** `scanner_cache_redis_errors_total` on Redis failure | **Missing** (logs only; counter never inc) |
| FR-010 | Singleflight/mutex during miss refill | **Missing on HTTP path** (helper exists unused) |
| Edge: corrupted JSON | Validate, DEL, DB fallback | **Missing** |
| Contract | `X-Cache-Status: FALLBACK` | **Missing** |
| §16 metrics | hits/misses/errors/ratio/force_refresh/latency labels | **Partially defined, not wired** |
| §18.2 | Flag toggle without container restart | **Not achieved** with env-only settings |
| SC-001 | p95 &lt; 10ms | **Not evidenced** by automated load test in suite |
| SC-002 | &gt;90% DB reduction over 24h | **Ops metric; not automatable here** — no runtime counters |
| SC-004 | 500 concurrent → ≤1 DB query | **Service-level only; routes unprotected** |
| T024 | backend README update | **Missing** |

Implemented / largely compliant:

- FR-001 feature flag gate on both endpoints  
- FR-002 Redis lookup when enabled  
- FR-003 HIT returns JSON without DB (when key correct)  
- FR-004 miss → DB → SET with TTL  
- FR-006 / FR-007 force + Cache-Control no-cache bypass + refill  
- FR-008 Redis errors do not yield 5xx (fallback to DB)  
- Empty result short TTL (10s)  
- Key names `scanner:latest:v1`, `analysis:scan:latest:v1`  
- Default flag `false`, TTL 300, timeouts 50/100 ms  
- Settings present; `redis` dependency present  

---

## Missing Tests

| Gap | Notes |
|---|---|
| Pre-warm production path without `inject_json` workaround | Current suite xfails missing import instead of failing build |
| Post-prewarm `/scanner/latest` body equals `LatestScanService` schema | Would catch C2 |
| Route-level stampede (N concurrent HTTP → 1 DB call) | Only service-level stampede tests exist |
| Corrupted Redis payload → DEL + DB fallback | Not covered |
| Metrics `.inc()` on hit/miss/error/force | Only “metric object defined” tests |
| `X-Cache-Status: FALLBACK` exact value on Redis outage | Tests accept MISS |
| Runtime flag flip without process restart | Not covered (and not implemented) |
| p95 latency / 1000 RPS throughput | Spec §17.3 load tests absent |
| Multi-worker stampede | Not covered |

Existing coverage that is good: unit hit/miss/timeout/write fail; force query+header; flag BYPASS; resilience HTTP 200; empty TTL; payload parity for miss→hit via route fill path.

---

## Production Readiness Checklist

| Area | Status |
|---|---|
| Specification compliance | ❌ Failed (FR-005/009/010, FALLBACK, corrupt handling) |
| Architecture preservation | ⚠ Needs Attention (additive service OK; dual store pre-warm mismatch) |
| Code quality | ⚠ Needs Attention (dead singleflight on routes; unused exceptions; duplication) |
| Production safety / fallback | ⚠ Needs Attention (DB fallback works; pre-warm broken; no FALLBACK signal) |
| Concurrency / stampede | ❌ Failed on request path |
| Database | ✅ Passed (no schema change; existing queries retained) |
| Performance goals | ⚠ Needs Attention (hit path present; stampede + missing pre-warm limit gains) |
| Security | ✅ Passed for scope (no new secrets; payload parity intent) |
| Observability | ❌ Failed (metrics dark) |
| Testing | ⚠ Needs Attention (57 pass but xfail + gaps hide production defects) |
| Feature flag rollback story | ⚠ Needs Attention (works with restart; not true dynamic) |
| Rollout readiness | ❌ Failed until Critical + High items addressed |

---

## Final Recommendation

**REQUIRES CHANGES BEFORE HARDENING**

Do not enable `SCANNER_LATEST_CACHE_ENABLED=true` in production until at least:

1. **C1** Pre-warm actually executes (`json` / `orjson` fix).  
2. **C2** Pre-warm payload for `scanner:latest:v1` matches dashboard route schema (or omit that key from pre-warm).  
3. **H1** Wire singleflight into both route miss paths.  
4. **H2** Instrument Prometheus counters/gauge on real paths.  
5. **H3–H4** FALLBACK status + corrupt key eviction.

After those fixes, re-run the cache suite (expect zero xfail on pre-warm), add route stampede + corrupt-payload tests, then proceed to staging canary with flag OFF → ON per §18.

---

## Audit Method Notes

- Reviewed: `spec.md`, `plan.md`, `tasks.md`, `contracts/scanner-cache-contract.md`, `data-model.md`, implementation under `backend/app/{services,routes,db,core,config,observability}`, and cache test modules.  
- Did not rewrite or patch code (audit-only).  
- Test command:  
  `pytest app/tests/test_scanner_cache_service.py app/tests/test_scanner_routes_cached.py app/tests/test_cache_force_refresh.py app/tests/test_cache_feature_flag.py app/tests/test_cache_resilience.py app/tests/test_cache_stampede.py app/tests/test_scan_worker_prewarm.py app/tests/test_cache_settings_and_metrics.py -q`  
  → **57 passed, 1 skipped, 1 xfailed**.
