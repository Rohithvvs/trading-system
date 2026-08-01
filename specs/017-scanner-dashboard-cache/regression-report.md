# Regression Validation Report: Scanner Dashboard Cache

**Feature**: `017-scanner-dashboard-cache`  
**Date**: 2026-07-27  
**Role**: Senior SDET / Release Validation Engineer  
**Source of truth**: `specs/017-scanner-dashboard-cache/spec.md`  
**Scope**: Regression only (no fixes, no new features, no re-audit)

---

## Regression Summary

### Areas validated

| Area | Result |
|---|---|
| Feature cache suite | **Pass** (69+ tests across hit/miss/force/flag/resilience/stampede/prewarm) |
| Scan persist path (`save_latest_scan`, normalize counts) | **Pass** (`test_scan_persist_and_candles`) |
| Governance suite sample | **Pass** (`test_rule_governance`) |
| App import / route registration | **Pass** |
| Settings load (defaults + `ge=` validation) | **Pass** |
| Flag-off `/scanner/latest` body contract smoke | **Pass** (HTTP 200, expected keys) |
| Metrics module compatibility | **Pass** (`ORDER_EXECUTIONS` path preserved; new counters additive) |
| Redis helpers (`get_redis_client`, blocklist, rate limiter, close) | **Pass** import/smoke |
| Legacy `scanner_cache.py` import | **Pass** (unchanged module still loads) |
| DB migrations / schema | **No schema changes in feature** |
| Full `app/tests` collection | **Blocked by pre-existing Alembic env issue** (not introduced by 017) |

### Existing functionality verified

- **Default flag OFF** (`SCANNER_LATEST_CACHE_ENABLED=false`): endpoints serve DB path with `X-Cache-Status: BYPASS`; body keys for dashboard payload preserved in smoke test.
- **Other analysis routes** remain registered (`/analysis/full`, `/analysis/technical`, etc.).
- **Scan completion persist** still commits to PostgreSQL/SQLite; pre-warm is post-commit and isolated in try/except when flag ON.
- **LatestScanService** query path retained as baseline/fallback.
- **No DB table/index migrations** in this feature.
- **Prometheus** existing counters still defined; scanner metrics are additive.

### Existing modules affected

| Module | Nature of change | Regression exposure |
|---|---|---|
| `routes/scanner.py` | Cache wrapper + `X-Cache-Status` | Medium (response transport) |
| `routes/analysis.py` (`/scan/latest` only) | Same | Medium |
| `db/scan_store.py` | Post-commit analysis pre-warm | Low (flag-gated, non-fatal) |
| `services/latest_scan_service.py` | Optional pre-warm helper | Low |
| `services/scan_execution_service.py` | Call pre-warm after commit | Low |
| `core/redis.py` | Connect timeout + close lifecycle | Medium (shared Redis consumers) |
| `config/settings.py` | New fields + `ge=` bounds | Low–Medium (startup validation) |
| `observability/metrics.py` | New counters/helpers | Low (additive) |
| `main.py` lifespan | `close_redis_client` on shutdown | Low |
| `tests/conftest.py` | Swallow Alembic upgrade errors | Low (test harness only) |

### Potential regression risks

1. **Additive response header** `X-Cache-Status` always present on the two cached endpoints (including BYPASS when flag OFF). Body contract preserved; strict clients that reject unknown headers could be sensitive (unlikely for browser/dashboard clients).
2. **Optional query `force`** and optional `Cache-Control: no-cache` on those two endpoints only — non-breaking extensions.
3. **Settings `ge=` constraints** reject invalid TTL/timeouts at process start (intentional hardening; misconfigured env fails closed).
4. **Redis client close on shutdown** nulls the global client; post-shutdown use must call `get_redis_client()` to recreate (shutdown-only path).
5. **Full-repo pytest collection** fails on this machine due to missing Alembic revision `20260726_pending_mobile` — **pre-existing environment/DB history issue**, not caused by 017 schema work (feature adds no migrations).

### Test evidence (this run)

```text
# Impact-related suite
104 passed, 1 skipped  (cache + scan_persist + rule_governance)

# Feature-only cache suite (prior)
69 passed, 1 skipped
```

Unrelated failures observed when pulling broader suites:

- `NameError: timezone` in `test_phase4_validation.py` (pre-existing test bug).
- Alembic `Can't locate revision identified by '20260726_pending_mobile'` on several recovery/hardening test modules (pre-existing env).

---

## Regression Findings

### Critical

*None identified attributable to 017-scanner-dashboard-cache.*

### High

*None identified attributable to 017.*

### Medium

#### R1 — Observability header always emitted on target endpoints

- **Description**: `GET /scanner/latest` and `GET /analysis/scan/latest` now always include `X-Cache-Status` (`BYPASS` when flag off).
- **Why it matters**: Pure additive header; documented in feature contract. Not a body-schema break, but is a wire-level change vs historical responses.
- **Severity**: Medium (compatibility)
- **Attribution**: Feature by design (contract).

#### R2 — Shared Redis lifecycle change

- **Description**: `core/redis.py` now applies connect timeout and closes the global client on app lifespan shutdown.
- **Why it matters**: Affects all Redis consumers (rate limit, JWT blocklist, legacy `scanner_cache`). Shutdown-only; fail-open when client unavailable remains.
- **Severity**: Medium
- **Attribution**: Hardening of shared infra used by feature.

### Low

#### R3 — Test conftest swallows Alembic upgrade exceptions

- **Description**: `backend/app/tests/conftest.py` wraps `alembic upgrade head` in bare `try/except: pass`.
- **Why it matters**: Can hide migration failures in CI when using Postgres; does not change production runtime.
- **Severity**: Low (test harness)

#### R4 — Settings stricter validation

- **Description**: TTL ≥ 10, read timeout ≥ 5, write timeout ≥ 10.
- **Why it matters**: Invalid production env values that previously loaded silently now fail startup.
- **Severity**: Low (ops config; safer fail-closed)

### Pre-existing issues (not 017 regressions)

| Issue | Notes |
|---|---|
| `health.py` imports `get_redis` (missing) | Falls into except → `redis=error` on `/health`. Not introduced by this feature’s redis API (`get_redis_client` only). |
| Alembic revision `20260726_pending_mobile` missing | Blocks collection of several non-cache tests against current DB. |
| `test_phase4_validation` missing `timezone` import | Setup errors unrelated to cache. |

---

## Release Readiness

### **READY WITH MINOR RISKS**

**Rationale**

- Default path keeps cache **disabled**; existing DB-backed behavior is the production default.
- No database schema changes; baseline query modules remain operational.
- Feature and adjacent persist/governance tests **pass** (104 passed, 1 skipped on impact suite).
- Residual risks are limited to additive headers, shared Redis shutdown cleanup, stricter settings bounds, and pre-existing env/test noise outside feature scope.
- Spec compliance for safe rollout (flag OFF first) is intact.

**Recommended merge conditions**

1. Deploy with `SCANNER_LATEST_CACHE_ENABLED=false` first (Stage 1).
2. Confirm dashboard clients tolerate `X-Cache-Status` (ignore unknown headers).
3. Enable cache only after staging verification per quickstart.
4. Separately fix env Alembic history / phase4 test if full-suite green is required for org policy (out of 017 scope).

---

## Validation Checklist

- ✅ Existing APIs verified (flag-off smoke + suite; other analysis routes registered)
- ✅ Existing services verified (LatestScanService, scan_store persist, metrics, redis helpers)
- ✅ Existing database behavior verified (no schema change; persist tests pass)
- ✅ Existing authentication verified (no auth module changes; Redis blocklist/rate-limit imports intact)
- ✅ Existing tests preserved (feature suite green; no intentional test deletion)
- ✅ No breaking body-contract changes detected on target endpoints
- ⚠ Production ready with minor risks (header additive; enable behind flag; pre-existing full-suite env issues)

---

## Method notes

- Reviewed changed files via `git status` / impact graph.
- Did **not** implement fixes or new features (per `Document/Regression.md`).
- Primary command:

```bash
pytest app/tests/test_scan_persist_and_candles.py \
  app/tests/test_rule_governance.py \
  app/tests/test_scanner_cache_service.py \
  app/tests/test_scanner_routes_cached.py \
  app/tests/test_cache_feature_flag.py \
  app/tests/test_cache_force_refresh.py \
  app/tests/test_cache_resilience.py \
  app/tests/test_cache_stampede.py \
  app/tests/test_scan_worker_prewarm.py \
  app/tests/test_cache_settings_and_metrics.py -q
# → 104 passed, 1 skipped
```
