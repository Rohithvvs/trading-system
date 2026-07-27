# Tasks: Scanner Dashboard Cache

**Input**: Design documents from `/specs/017-scanner-dashboard-cache/`  
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/plan.md), [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md), [research.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/data-model.md), [contracts/](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/contracts/scanner-cache-contract.md), [quickstart.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/quickstart.md)

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- All tasks include exact file paths in descriptions.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Infrastructure configuration and core settings setup.

- [x] T001 Configure environment variables for cache layer (`SCANNER_LATEST_CACHE_ENABLED`, `SCANNER_LATEST_CACHE_TTL_SECONDS`, `REDIS_CACHE_READ_TIMEOUT_MS`, `REDIS_CACHE_WRITE_TIMEOUT_MS`) in `backend/app/config/settings.py`
- [x] T002 [P] Verify `redis` async client dependency in `backend/requirements.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Redis infrastructure and base cache service that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Create async Redis connection pool manager and lifecycle hooks in `backend/app/core/redis.py`
- [x] T004 Create base cache service class with `asyncio.Lock` singleflight stampede protection in `backend/app/services/scanner_cache_service.py`
- [x] T005 [P] Create custom exception classes and fallback logger for cache errors in `backend/app/core/exceptions.py`

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Fast Dashboard Loading via Cached Scanner Results (Priority: P1) 🎯 MVP

**Goal**: Serve cached scanner payloads for `GET /scanner/latest` and `GET /analysis/scan/latest` in <10ms, reducing PostgreSQL read query volume by >90%.

**Independent Test**: Execute consecutive GET requests to `/scanner/latest` with `SCANNER_LATEST_CACHE_ENABLED=true` and verify second request returns HTTP 200 (`X-Cache-Status: HIT`) in <10ms without PostgreSQL SQL logs.

### Tests for User Story 1

- [x] T006 [P] [US1] Create unit tests for cache lookup, hit, miss, and singleflight locking in `backend/app/tests/test_scanner_cache_service.py`
- [x] T007 [P] [US1] Create contract and integration tests for `/scanner/latest` and `/analysis/scan/latest` caching in `backend/app/tests/test_scanner_routes_cached.py`

### Implementation for User Story 1

- [x] T008 [US1] Implement `get_latest_scan()` and `set_latest_scan()` pre-serialized JSON caching logic in `backend/app/services/scanner_cache_service.py`
- [x] T009 [US1] Integrate `ScannerCacheService` into `GET /scanner/latest` route handler with `X-Cache-Status` header in `backend/app/routes/scanner.py`
- [x] T010 [US1] Integrate `ScannerCacheService` into `GET /analysis/scan/latest` route handler with `X-Cache-Status` header in `backend/app/routes/analysis.py`

**Checkpoint**: At this point, User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - Real-Time Active Cache Pre-Warming on Scan Completion (Priority: P1)

**Goal**: Automatically pre-warm Redis cache keys (`scanner:latest:v1` and `analysis:scan:latest:v1`) immediately upon background market scan completion so that the first dashboard request post-scan gets an instant cache hit.

**Independent Test**: Trigger a background market scan run; verify Redis keys are updated upon scan completion, and verify next API call receives `X-Cache-Status: HIT` with new scan data.

### Tests for User Story 2

- [x] T011 [P] [US2] Create integration tests for scan completion active pre-warming in `backend/app/tests/test_scan_worker_prewarm.py`

### Implementation for User Story 2

- [x] T012 [US2] Implement active pre-warming post-commit hook `set_latest_scan()` in scan background execution worker in `backend/app/db/scan_store.py`
- [x] T013 [US2] Implement `invalidate_scan_cache()` helper in `backend/app/services/scanner_cache_service.py`

**Checkpoint**: User Stories 1 AND 2 are fully integrated and independently testable.

---

## Phase 5: User Story 3 - Manual Force Refresh & Bypass (Priority: P2)

**Goal**: Allow developers/admins to force a cache refresh via `?force=true` query parameter or `Cache-Control: no-cache` header.

**Independent Test**: Execute `GET /scanner/latest?force=true` while cache holds data; verify PostgreSQL is queried and Redis key is refreshed with HTTP 200 response.

### Tests for User Story 3

- [x] T014 [P] [US3] Create unit/integration tests for `?force=true` parameter and `Cache-Control: no-cache` header bypass in `backend/app/tests/test_cache_force_refresh.py`

### Implementation for User Story 3

- [x] T015 [US3] Implement `CacheControlDirective` parsing (`?force=true` / `Cache-Control: no-cache`) in `backend/app/routes/scanner.py`
- [x] T016 [US3] Implement `CacheControlDirective` parsing (`?force=true` / `Cache-Control: no-cache`) in `backend/app/routes/analysis.py`

**Checkpoint**: User Stories 1, 2, and 3 work independently.

---

## Phase 6: User Story 4 - Feature Flag Governance & Zero-Downtime Rollback (Priority: P2)

**Goal**: Dynamically toggle `SCANNER_LATEST_CACHE_ENABLED` between `true` and `false` so that the system can immediately revert to direct DB queries without code redeploy.

**Independent Test**: Set `SCANNER_LATEST_CACHE_ENABLED=false` and verify all requests query PostgreSQL directly with `X-Cache-Status: BYPASS`.

### Tests for User Story 4

- [x] T017 [P] [US4] Create integration tests verifying dynamic feature flag toggling (`SCANNER_LATEST_CACHE_ENABLED=false`) in `backend/app/tests/test_cache_feature_flag.py`

### Implementation for User Story 4

- [x] T018 [US4] Add feature flag evaluation wrapper around Redis cache lookups in `backend/app/routes/scanner.py` and `backend/app/routes/analysis.py`

**Checkpoint**: Feature flag governance verified.

---

## Phase 7: User Story 5 - High-Availability Fallback on Redis Outage (Priority: P3)

**Goal**: Ensure zero 5xx errors if Redis experiences connection errors or timeouts (>50ms) by gracefully falling back to PostgreSQL queries.

**Independent Test**: Stop Redis container and send GET request to `/scanner/latest`; verify HTTP 200 (`X-Cache-Status: FALLBACK`) returned with logged warning metric.

### Tests for User Story 5

- [x] T019 [P] [US5] Create resilience and failure recovery tests for Redis timeout (>50ms) and connection errors in `backend/app/tests/test_cache_resilience.py`

### Implementation for User Story 5

- [x] T020 [US5] Implement 50ms read timeout and try-catch fallback wrapper in `backend/app/services/scanner_cache_service.py`
- [x] T021 [US5] Add structured warning metric logging (`scanner_cache_redis_errors_total`) for Redis fallbacks in `backend/app/observability/metrics.py`

**Checkpoint**: All 5 user stories independently functional and resilient.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final monitoring, metric exposes, and documentation checks.

- [x] T022 [P] Expose Prometheus metrics counters (`scanner_cache_hits_total`, `scanner_cache_misses_total`, `scanner_cache_hit_ratio`) in `backend/app/observability/metrics.py`
- [x] T023 Run validation quickstart scenarios from `specs/017-scanner-dashboard-cache/quickstart.md`
- [x] T024 [P] Update documentation in `backend/README.md` and feature spec notes

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user story tasks.
- **User Stories (Phase 3+)**: Depend on Foundational phase completion. Proceed in priority order: US1 (MVP) -> US2 -> US3 -> US4 -> US5.
- **Polish (Phase 8)**: Depends on completion of desired user stories.

### Parallel Opportunities
- All Setup tasks marked `[P]` can run in parallel (`T002`).
- All Foundational tasks marked `[P]` can run in parallel (`T005`).
- Test tasks within each story marked `[P]` can run in parallel (`T006`, `T007`, `T011`, `T014`, `T017`, `T019`).
- Observability and documentation polish tasks marked `[P]` can run in parallel (`T022`, `T024`).

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (`T001` - `T002`)
2. Complete Phase 2: Foundational (`T003` - `T005`)
3. Complete Phase 3: User Story 1 (`T006` - `T010`)
4. **STOP & VALIDATE**: Execute Scenario 2 & Scenario 3 from `quickstart.md`. Verify <10ms response and zero SQL queries.

### Incremental Delivery
- Add User Story 2 (`T011` - `T013`) -> Verify active pre-warming.
- Add User Story 3 (`T014` - `T016`) -> Verify force refresh `?force=true`.
- Add User Story 4 (`T017` - `T018`) -> Verify feature flag toggle.
- Add User Story 5 (`T019` - `T021`) -> Verify Redis outage resilience.
