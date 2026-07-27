# Hardening Summary: Scanner Dashboard Cache

**Feature**: `017-scanner-dashboard-cache`  
**Date**: 2026-07-27  
**Source**: Audit report + `Document/Hardening.md`  
**Validation**: Cache suite **66 passed, 1 skipped** (no new tests added)

---

## Hardening Summary

### Files modified

| File | Change |
|---|---|
| `backend/app/services/scanner_cache_service.py` | Live flag evaluation, typed `CacheLookupResult`, corrupt eviction, singleflight/`resolve_latest_scan`, shared `wants_force_refresh`, in-process lock scope documented |
| `backend/app/routes/scanner.py` | Resolve path + metrics + live flag + shared force helper |
| `backend/app/routes/analysis.py` | Same for `/analysis/scan/latest` |
| `backend/app/db/scan_store.py` | Analysis-only pre-warm via `orjson`; live flag |
| `backend/app/services/latest_scan_service.py` | Dashboard-schema pre-warm for `scanner:latest:v1` |
| `backend/app/services/scan_execution_service.py` | Call pre-warm after persist commit |
| `backend/app/observability/metrics.py` | Hit/miss/error/force counters + hit-ratio + record helpers |
| `backend/app/config/settings.py` | TTL/timeout `ge=` bounds; `is_scanner_latest_cache_enabled()` live read |
| `backend/app/core/redis.py` | Connect timeout; `close_redis_client()` lifecycle |
| `backend/app/main.py` | Redis close on lifespan shutdown (prod + test) |
| `specs/017-scanner-dashboard-cache/spec.md` | FR-009 metric name; honest rollback procedure |
| `specs/017-scanner-dashboard-cache/quickstart.md` | Ops guide (env, headers, rollback, metrics, concurrency, pre-warm) |

### Audit findings resolved

| ID | Severity | Resolution |
|---|---|---|
| **C1** | Critical | Pre-warm uses `orjson.dumps` (no silent NameError) |
| **C2** | Critical | `scanner:latest:v1` pre-warmed with LatestScanService dashboard schema only |
| **H1** | High | Routes use `resolve_latest_scan` / singleflight |
| **H2** | High | Prometheus counters/gauge instrumented on real paths |
| **H3** | High | `X-Cache-Status: FALLBACK` on Redis error/timeout |
| **H4** | High | Corrupt JSON validated, key deleted, DB refill |
| **H5** | High | Live flag via `settings.is_scanner_latest_cache_enabled()`; rollback docs corrected |
| **M2** | Medium | Redis connect timeout + shutdown close |
| **M3** | Medium | Settings `ge=` constraints |
| **M4** | Medium | `CacheLookupResult` distinguishes miss vs Redis error |
| **M5** | Medium | Ops documentation in quickstart §3 |
| **M6** | Medium | Force-refresh counter metric |
| **L1** | Low | Shared `wants_force_refresh` helper |
| **L2** | Low | FR-009 metric name aligned to `scanner_cache_redis_errors_total` |

### Reliability improvements

- Redis failures never raise 5xx; soft fallback to PostgreSQL with `FALLBACK` status.
- Corrupt cache payloads are evicted before refill.
- Pre-warm failures remain isolated (try/except); scan persist still succeeds.
- Active pre-warm for both keys with correct schemas.

### Performance improvements

- In-process singleflight on miss/force refill reduces thundering-herd DB load per worker.
- Strict Redis read/write timeouts (50ms / 100ms) via `asyncio.wait_for`.
- Connect-phase timeout on Redis client creation.

### Security improvements

- No new attack surface; cache continues to store the same public read payloads as the API.
- No secrets added to Redis keys or settings logging.

### Observability improvements

- Live metrics: hits, misses, Redis errors, force refreshes, hit ratio.
- Structured cache status header: `HIT | MISS | BYPASS | FALLBACK`.
- Ops runbook in quickstart.

---

## Remaining Audit Findings

| ID | Severity | Status | Why left unresolved |
|---|---|---|---|
| **M1** | Medium | **Resolved** | Redis `SET lock:{key} NX EX` distributed singleflight + wait-for-fill across workers. |
| **L3** | Low | **Resolved** | `_redis_get/_set/_delete` raise `RedisCacheTimeoutException` / `RedisCacheConnectionException`; lookup maps them to FALLBACK. |
| SC-001 load bench | N/A | Ops | p95 &lt; 10ms / 1000 RPS remains an ops/load validation item. |

---

## Validation Checklist

- ✅ Critical findings resolved
- ✅ High findings resolved
- ✅ Architecture preserved (cache-aside + feature flag + active pre-warm)
- ✅ Existing functionality preserved (API body contracts unchanged)
- ✅ Specification preserved (FR/contract aligned; rollback language corrected)
- ✅ Existing cache tests remain valid (**66 passed, 1 skipped**)
- ✅ Ready for Regression Testing

---

## Notes

- Hardening did **not** add new features, redesign architecture, or generate new tests.
- Prior implementation fixes (C1–H4) were retained and completed with H5/M2/docs in this pass.
