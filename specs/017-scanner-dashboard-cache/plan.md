# Implementation Plan: Scanner Dashboard Cache

**Branch**: `017-scanner-dashboard-cache` | **Date**: 2026-07-27 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md)  
**Input**: Approved Feature Specification (`/specs/017-scanner-dashboard-cache/spec.md`)

---

## Technical Context

- **Language/Version**: Python 3.11+
- **Primary Dependencies**: FastAPI, `redis.asyncio` (`redis-py` >= 4.2.0), `pydantic`
- **Storage**: PostgreSQL (Primary DB), Redis v6.0+ (In-Memory Cache)
- **Testing**: `pytest`, `pytest-asyncio`, `httpx`
- **Target Platform**: Linux Server / Docker Containerized Environment
- **Project Type**: Web Service / Trading Application Backend API
- **Performance Goals**: p95 endpoint response time < 10ms for cache hits; > 90% reduction in database read queries on scanner latest endpoints.
- **Constraints**: 100% backward compatibility; zero changes to database schemas or public API response JSON contracts; strict 50ms Redis timeout.

---

## Constitution Check

- **I. Library-First / Modular Design**: Cache logic implemented as an isolated, reusable service module (`app.services.scanner_cache_service`) decoupled from route handlers.
- **II. Test-First / Verification-Driven**: Unit and integration test scenarios must be defined and validated before rollout.
- **III. Resiliency & Graceful Degradation**: Outages in non-critical components (Redis) must never degrade core API availability (fall back to PostgreSQL).
- **IV. Observability**: Structured metrics (`X-Cache-Status` headers, hit/miss counters, latency histograms) required.

---

## Project Structure

### Documentation & Design Artifacts (this feature)

```text
specs/017-scanner-dashboard-cache/
├── spec.md                             # Approved Feature Specification
├── research.md                         # Technical Research & Architecture Decisions
├── data-model.md                       # Data Model & Configuration Spec
├── quickstart.md                       # Verification & Validation Guide
├── contracts/
│   └── scanner-cache-contract.md       # API & Cache Interface Contract
├── plan.md                             # Implementation Plan (This File)
└── checklists/
    └── requirements.md                 # Specification Quality Checklist
```

### Source Code Architecture Layout (backend root)

```text
backend/app/
├── core/
│   ├── config.py                       # Environment settings (TTL, Flag, Timeouts)
│   └── redis.py                        # Redis connection pool & client lifecycle
├── services/
│   ├── scanner_cache_service.py        # Redis cache read/write/invalidation logic
│   └── latest_scan_service.py          # Refactored service layer (Cache-Aside wrapper)
├── routes/
│   ├── scanner.py                      # GET /scanner/latest route handler
│   └── analysis.py                     # GET /analysis/scan/latest route handler
├── workers/
│   └── scanner_worker.py               # Scan completion worker with active pre-warming hook
└── tests/
    ├── test_scanner_cache_service.py   # Unit tests for cache service
    ├── test_scanner_routes_cached.py   # Route integration & fallback tests
    └── test_cache_stampede.py          # Concurrent request stampede tests
```

---

## 1. Executive Summary

### 1.1 Implementation Strategy
Introduce an in-memory Redis caching layer behind a feature flag (`SCANNER_LATEST_CACHE_ENABLED`) to serve high-frequency read requests for `GET /scanner/latest` and `GET /analysis/scan/latest`. The strategy employs a **Cache-Aside (Read-Through wrapper) pattern with Singleflight Lock Protection** on read requests, paired with **Event-Driven Active Pre-Warming (`SET`)** upon background scan completion.

### 1.2 Expected Outcomes
- Sub-10ms endpoint response latency for >90% of requests.
- >90% reduction in SQL SELECT queries executed against PostgreSQL for latest scan endpoints.
- 100% zero-downtime resiliency: if Redis fails, the system seamlessly falls back to direct PostgreSQL reads without raising HTTP 5xx errors.

---

## 2. Architecture Plan

### 2.1 High-Level Architecture
```
                                Client Request
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   FastAPI Router Layer    │
                        └─────────────┬─────────────┘
                                      │
                         Check Flag: ENABLED?
                         ├── (NO) ─────────────────────────────┐
                         │                                     │
                       (YES)                                   │
                         │                                     │
                         ▼                                     ▼
            ┌─────────────────────────┐          ┌──────────────────────────┐
            │  Scanner Cache Service  │          │  Latest Scan Service     │
            └────────────┬────────────┘          │  (PostgreSQL Reader)     │
                         │                       └─────────────┬────────────┘
               Lookup Redis Key                                │
               ├── (HIT) ──► Return Cached JSON                │
               │                                               │
            (MISS/ERR)                                         │
               │                                               │
               ▼                                               │
    ┌──────────────────────┐                                   │
    │  Singleflight Lock   ├───────────────────────────────────┘
    └──────────────────────┘ (Only 1 request queries DB; populates cache)
```

### 2.2 Component Interaction Matrix
- **Router Handler** (`app.routes.scanner`, `app.routes.analysis`): Inspects query/header directives (`force=true`), calls `ScannerCacheService`.
- **Cache Service** (`app.services.scanner_cache_service`): Interacts with Redis pool using strict timeouts (50ms).
- **Scan Worker** (`app.workers.scanner_worker`): Executes scan logic, commits to PostgreSQL, then triggers `ScannerCacheService.set_latest_scan()` to actively pre-warm cache.

---

## 3. Component Impact Analysis

| Component | Current Responsibility | Required Changes | Why Needed | Impact on Other Modules |
|---|---|---|---|---|
| `app.core.config` | Manages environment variables | Add `SCANNER_LATEST_CACHE_ENABLED`, `SCANNER_LATEST_CACHE_TTL_SECONDS`, timeouts | Centralized configuration | None (Additive) |
| `app.core.redis` | N/A (or basic Redis handle) | Initialize async Redis connection pool in FastAPI startup lifecycle | High-performance async connection reuse | None (Additive) |
| `app.services.scanner_cache_service` | Non-existent | Create dedicated cache service (get, set, invalidate, singleflight lock) | Encapsulates Redis operations & fallback logic | None (Additive) |
| `app.routes.scanner` | Handles `/scanner/latest` | Wrap service call with cache lookup & add `X-Cache-Status` response header | Serves cached payload directly | None (Contract preserved) |
| `app.routes.analysis` | Handles `/analysis/scan/latest` | Wrap service call with cache lookup & add `X-Cache-Status` response header | Serves cached payload directly | None (Contract preserved) |
| `app.workers.scanner_worker` | Executes scans & persists to DB | Add post-commit hook calling `set_latest_scan()` | Active cache pre-warming (Option B clarification) | None (Post-commit hook) |

---

## 4. Module Breakdown

1. **API Layer**: `backend/app/routes/scanner.py`, `backend/app/routes/analysis.py`
2. **Cache Service Layer**: `backend/app/services/scanner_cache_service.py`
3. **Database Layer**: `backend/app/services/latest_scan_service.py` (Unmodified baseline queries)
4. **Worker Layer**: `backend/app/workers/scanner_worker.py` (Active pre-warming trigger)
5. **Core Infrastructure**: `backend/app/core/config.py`, `backend/app/core/redis.py`
6. **Observability Module**: `backend/app/observability/metrics.py` (Hit/miss counters, latency metrics)

---

## 5. Implementation Strategy Step-by-Step

1. **Step 1: Configuration & Infrastructure Setup**: Define cache settings in `app.core.config.Settings` and set up global async Redis client in `app.core.redis.py`.
2. **Step 2: Core Cache Service (`ScannerCacheService`)**: Implement non-blocking `get()`, `set()`, and `invalidate()` methods wrapped in try-except blocks with 50ms read timeouts. Include `asyncio.Lock` for singleflight stampede prevention.
3. **Step 3: Route Integration**: Update `GET /scanner/latest` and `GET /analysis/scan/latest` to check feature flag `SCANNER_LATEST_CACHE_ENABLED`. If `true` and `force` parameter is absent, execute `ScannerCacheService.get()`. Return `Response(content=json_bytes, media_type="application/json")`.
4. **Step 4: Active Pre-warming Worker Hook**: Attach post-commit event hook in scan worker to pre-serialize and `SET` updated payloads into Redis upon scan completion.
5. **Step 5: Testing & Fallback Verification**: Write unit tests, Redis outage simulation tests, and concurrent stampede tests.

---

## 6. Dependency Analysis

- **Internal Dependencies**: `ScannerCacheService` depends on `app.core.redis` for connection pool and `app.core.config` for settings. Routes depend on `ScannerCacheService`.
- **External Dependencies**: Redis Server (v6.0+) accessible over TCP network. Python package `redis` >= 4.2.0.
- **Configuration Dependencies**: Environment variables (`SCANNER_LATEST_CACHE_ENABLED`, `REDIS_URL`, `SCANNER_LATEST_CACHE_TTL_SECONDS`).
- **Runtime Dependencies**: FastAPI event loop running `asyncio`.

---

## 7. Data Flow Plan

```
[HTTP GET Request]
        │
        ▼
[FastAPI Router Handler]
        │
        ├── SCANNER_LATEST_CACHE_ENABLED == false ──► [Query PostgreSQL DB] ──► [Return DB JSON]
        │
        ▼ (ENABLED == true)
[Check Query Param: ?force=true OR Header: Cache-Control: no-cache]
        │
        ├── YES (Force Refresh) ──────────────────────► [Query PostgreSQL DB] ──► [Write Redis] ──► [Return DB JSON]
        │
        ▼ (NO)
[Redis GET scanner:latest:v1 (Timeout: 50ms)]
        │
        ├── HIT ───────────────────────────────────────────────────────────────► [Return Redis JSON (<10ms)]
        │
     MISS / REDIS ERROR
        │
        ▼
[Acquire Singleflight Lock]
        │
        ▼
[Query PostgreSQL DB] ──► [Serialize JSON] ──► [Write Redis (SET EX 300)] ──► [Return JSON]
```

---

## 8. Feature Flag Strategy

- **Flag Name**: `SCANNER_LATEST_CACHE_ENABLED` (Default: `false`)
- **Rollout Sequence**: Deploy code with flag `false` (baseline) -> Enable flag in Staging -> Enable flag in Production.
- **Rollback Procedure**: If any anomaly is detected, update environment variable `SCANNER_LATEST_CACHE_ENABLED=false` or dynamic config toggle. System immediately reverts to direct PostgreSQL reads in zero seconds with zero downtime.

---

## 9. Cache Lifecycle Plan

- **Creation & Refill**: Triggered on Cache Miss during API request OR via Active Pre-warming on scan completion.
- **Lookup**: Executed on API GET request when feature flag is `true`.
- **Refresh**: Triggered automatically when TTL expires OR manually when `?force=true` parameter is sent.
- **Invalidation & Overwrite**: Executed immediately by scan worker via `SET key json EX 300` upon scan completion.
- **TTL Expiration**: Redis automatically evicts key after 300 seconds (configurable).

---

## 10. Failure Recovery Plan

| Failure Event | Recovery Mechanism | Impact |
|---|---|---|
| **Redis Connection Refused** | Exception caught in `ScannerCacheService` -> Log warning -> Query PostgreSQL. | Zero API failure. Response latency matches baseline DB read. |
| **Redis Read Timeout (>50ms)** | Timeout error caught -> Fallback to PostgreSQL read. | Zero API failure. Client receives response without hanging. |
| **Corrupted Redis JSON** | JSON decode validation check fails -> Key deleted (`DEL`) -> Query PostgreSQL. | Zero API failure. Client receives fresh DB data. |
| **Concurrent Miss Stampede** | `asyncio.Lock` / Singleflight ensures 1 DB query is executed. | Database protected from connection pool exhaustion. |

---

## 11. Performance Plan

- **Database Query Reduction**: Expected SELECT query volume reduction on scan tables >90%.
- **Response Time Improvement**: p95 endpoint latency reduced from >150ms to <10ms for cached hits.
- **Bandwidth & CPU Savings**: Pre-serialized JSON pass-through eliminates FastAPI JSON serialization CPU overhead per request.

---

## 12. Risk Assessment

| Risk | Severity | Mitigation Strategy |
|---|---|---|
| **Stale Cache Data** | Medium | Active pre-warming (`SET`) on scan completion + 300s TTL + `?force=true` bypass. |
| **Cache Stampede on Expiry** | High | Enforce in-process singleflight mutex lock on cache refill. |
| **Redis Outage Degrading API** | High | Strict 50ms read timeout and try-catch fallback wrapper executing direct PostgreSQL query. |

---

## 13. Validation Plan

Before opening PR for task execution:
1. Validate JSON schema parity between cached response and direct DB response using automated diff test.
2. Validate zero SQL queries executed during hot cache hit test (`pytest-django` / `sqlalchemy` query counter).
3. Validate graceful fallback during simulated Redis disconnection test.

---

## 14. Monitoring Plan

Expose the following metrics via Prometheus / Application Logs:
- `scanner_cache_hits_total{endpoint="/scanner/latest"}`
- `scanner_cache_misses_total{endpoint="/scanner/latest"}`
- `scanner_cache_hit_ratio` (Target > 0.90)
- `scanner_cache_redis_errors_total` (Alert if > 10 in 5 mins)
- `http_request_duration_seconds{status="cached|db"}`

---

## 15. Rollout Plan

1. **Stage 1 (Deployment)**: Deploy code behind `SCANNER_LATEST_CACHE_ENABLED=false`. Verify baseline behavior.
2. **Stage 2 (Staging Validation)**: Turn flag `ON` in staging. Run automated integration & load test suite.
3. **Stage 3 (Production Canary)**: Enable flag `ON` in production. Monitor Grafana dashboard & PostgreSQL CPU usage.
4. **Stage 4 (Rollback Window)**: If error rate spikes > 0.1%, flip flag `OFF`.

---

## 16. Assumptions

- Redis 6.0+ instance is accessible from API container over low-latency network (<2ms).
- Existing PostgreSQL scan query logic is deterministic and suitable for serialization into standard JSON payloads.

---

## 17. Constraints

- Zero changes to existing public API endpoint URLs, response schemas, or database tables.
- All new cache behavior MUST strictly execute behind `SCANNER_LATEST_CACHE_ENABLED`.

---

## 18. Deliverables

Before advancing to Phase 2 (`/speckit-tasks`):
- Approved Spec (`specs/017-scanner-dashboard-cache/spec.md`)
- Technical Research (`specs/017-scanner-dashboard-cache/research.md`)
- Data Model Spec (`specs/017-scanner-dashboard-cache/data-model.md`)
- Contract Spec (`specs/017-scanner-dashboard-cache/contracts/scanner-cache-contract.md`)
- Quickstart Guide (`specs/017-scanner-dashboard-cache/quickstart.md`)
- Approved Implementation Plan (`specs/017-scanner-dashboard-cache/plan.md`)
