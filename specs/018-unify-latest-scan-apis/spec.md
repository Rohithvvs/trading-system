# Feature Specification: Unify Latest-Scan APIs

**Feature Branch**: `018-unify-latest-scan-apis`  
**Created**: 2026-07-27  
**Status**: Approved / Implementation-Ready  
**Input**: User description: "Sprint 2 – Specification Generation (SDD): Unify Latest-Scan APIs"

---

## 1. Executive Summary

### 1.1 Feature Overview
Sprint 2 introduces a single, canonical backend service layer—`LatestScanService.get_latest_scan()`—responsible for fetching, resolving, and preparing the latest completed scanner results for client consumption. Currently, the system exposes two public endpoints:
- `GET /scanner/latest` (serving dashboard-facing snapshot candidates)
- `GET /analysis/scan/latest` (serving deep-analysis scan payloads)

Each endpoint presently executes its own distinct data access, formatting, and logging pipelines, resulting in code duplication, divergent queries, and elevated risk of inconsistent behavior during operational updates. Sprint 2 refactors both endpoints to delegate all underlying scan retrieval and business logic to `LatestScanService` while preserving 100% backward compatibility for all API clients.

### 1.2 Business Purpose
- **Lower Operational & Maintenance Costs**: Maintenance engineers update business rules (such as snapshot selection criteria or stale scan filters) in a single unified codebase location rather than across multiple route handlers.
- **Risk Reduction**: Eliminates subtle discrepancies between dashboard views and analysis views, ensuring traders and downstream automated strategies inspect identical market scan snapshots.
- **Velocity for Future Features**: Establishes a clean, single source of truth that simplifies adding new query parameters, multi-tenant boundaries, or caching policies in subsequent sprints.

### 1.3 Technical Purpose
- **Refactor to Single Responsibility**: Consolidate disparate data query layers (`ScanSnapshot`/`ScanSnapshotRecord` ORM queries vs `db.scan_store.load_latest_scan` raw JSONB queries) into a cohesive domain service.
- **Maintain Full Backward Compatibility**: Ensure zero structural changes to public HTTP contracts, response schemas, status codes, headers, or authentication/authorization mechanics.
- **Controlled Feature Flag Rollout**: Guard the unified service delegation behind a feature flag (`SCANNER_UNIFIED_LATEST_ENABLED`) allowing instant zero-downtime rollback to legacy code paths if anomaly occurs.

### 1.4 Expected Outcome
Both `GET /scanner/latest` and `GET /analysis/scan/latest` execute through `LatestScanService.get_latest_scan()` when `SCANNER_UNIFIED_LATEST_ENABLED` is `ON`. Response schemas, latency profiles, and cache semantics remain identical to Sprint 1 baselines.

---

## 2. Problem Statement

### 2.1 Current Duplicated Architecture
The trading application currently exposes two distinct API endpoints that provide "the latest scan result" to clients:

```
Legacy Architecture (Sprint 1 Baseline):

Client Request ─────────────────► GET /scanner/latest
                                       │
                                       ▼
                          [routes/scanner.py]
                                       │
                                       ▼
                   LatestScanService.get_latest_completed_scan()
                                       │
                                       ▼
                     PostgreSQL (scan_snapshots ORM)


Client Request ─────────────────► GET /analysis/scan/latest
                                       │
                                       ▼
                          [routes/analysis.py]
                                       │
                                       ▼
                         scan_store.load_latest_scan()
                                       │
                                       ▼
                     PostgreSQL (market_data.scan_results)
```

### 2.2 Why Duplication Exists
- **Historical Evolution**: `GET /analysis/scan/latest` was created during early research phases to dump full raw scan payloads directly from `market_data.scan_results` JSONB storage. `GET /scanner/latest` was created later during dashboard development to serve categorized candidate lists (`buy_candidates`, `watch_candidates`, `rejected_candidates`) via structured ORM tables (`scan_snapshots` and `scan_snapshot_records`).
- **Parallel Feature Development**: As new features were added (diagnostics logging, metric tracking, cache invalidation), both routes received independent, un-synchronized modifications.

### 2.3 Risks Created by Duplicate Implementations
1. **Inconsistent Data State**: If a scan persistence run succeeds in `scan_snapshots` but fails or lags in `market_data.scan_results` (or vice versa), `GET /scanner/latest` and `GET /analysis/scan/latest` return disparate timestamps, creating confusion between dashboard users and analytical engine components.
2. **Divergent Cache Mechanisms**: Sprint 1 added Redis caching (`scanner:latest:v1` and `analysis:scan:latest:v1`). Maintaining separate fetch-and-serialize logic in two route files increases the probability of cache invalidation desynchronization.
3. **Elevated Testing Complexity**: Every new query filter or observability field requires duplicate test suites and mock setups for both endpoint modules.

### 2.4 Long-Term Maintenance Problems
Any bug fix, performance optimization, or schema enhancement applied to scan retrieval must be implemented twice. Omitting one endpoint during a critical hotfix leads to silent production bugs where dashboard metrics drift from strategy signal evaluation logic.

---

## 3. Goals

- **G-1: Remove Duplicated Business Logic**: Consolidate scan querying, fallback detection, sorting, and payload preparation into a single canonical service (`LatestScanService`).
- **G-2: Establish Single Source of Truth**: Ensure both public endpoints derive their data from the exact same underlying snapshot resolution logic and persistence source.
- **G-3: Simplify Future Maintenance**: Provide a single entry point (`LatestScanService.get_latest_scan()`) for modifying scan fetching, filtering, or transformation rules.
- **G-4: Preserve Existing APIs & Contracts**: Ensure 100% backward compatibility for response schemas, HTTP status codes, headers, and query parameters.
- **G-5: Enable Safe Rollout & Rollback**: Implement a robust feature flag (`SCANNER_UNIFIED_LATEST_ENABLED`) with zero-downtime dynamic toggle capabilities.
- **G-6: Maintain High Performance**: Guarantee no regression in response latency (p95 < 10ms for cached hits; p95 < 150ms for DB hits).

---

## 4. Scope

### 4.1 In-Scope Endpoints
- `GET /scanner/latest`
- `GET /analysis/scan/latest`

### 4.2 Affected Modules
- **API Layer**: `backend/app/routes/scanner.py`, `backend/app/routes/analysis.py`
- **Service Layer**: `backend/app/services/latest_scan_service.py`
- **Repository / Data Layer**: `backend/app/db/scan_store.py`, `backend/app/models/market_data.py`
- **Dependency Injection**: FastAPI `Depends(get_db)` session management in route handlers and service instantiation.
- **Feature Flags**: `backend/app/config/settings.py` (adding `SCANNER_UNIFIED_LATEST_ENABLED`).
- **Logging**: Unified diagnostic logging via `log_dashboard_request` and `scan.db` loggers.
- **Metrics**: Unified Prometheus metric counters for cache and database invocations.

### 4.3 Out-of-Scope Items
- **Public API Contract Changes**: No modification to route URLs, response structures, field names, or data types.
- **Database Schema Alterations**: No migrations or schema changes to `scan_snapshots`, `scan_snapshot_records`, or `market_data.scan_results`.
- **Sprint 1 Cache Invalidation Strategy**: Cache keys (`scanner:latest:v1` and `analysis:scan:latest:v1`) and Redis TTLs remain managed by `scanner_cache_service`.
- **Authentication/Authorization Model**: No changes to security protocols or permissions.
- **Write Path / Ingestion Pipelines**: How scans are written and persisted by `ScreenerService` or `OrchestratorAgent` remains unchanged.

---

## 5. Functional Requirements

### 5.1 Shared Service Creation (`FR-001` to `FR-005`)
- **FR-001**: System MUST provide a single canonical service method `LatestScanService.get_latest_scan(target_format: str)` (or equivalent format-specific fetch methods `get_latest_dashboard_scan()` and `get_latest_analysis_scan()`) encapsulated in `LatestScanService`.
- **FR-002**: `LatestScanService` MUST handle querying the authoritative database repository for the most recent completed scan snapshot (`status == 'COMPLETED'`), falling back to the newest snapshot if no `COMPLETED` row exists.
- **FR-003**: `LatestScanService` MUST perform candidate categorization and score-based sorting for dashboard payloads (`buy_candidates`, `watch_candidates`, `rejected_candidates` sorted descending by score).
- **FR-004**: `LatestScanService` MUST provide standardized handling for empty/missing scan states, returning explicit structured empty representations for both dashboard and analysis formats.
- **FR-005**: `LatestScanService` MUST be completely reusable across API route handlers, background tasks, and CLI commands without duplicating database query code.

### 5.2 Endpoint Delegation & Feature Flag Behavior (`FR-006` to `FR-010`)
- **FR-006**: System MUST evaluate feature flag `SCANNER_UNIFIED_LATEST_ENABLED` upon every request to `GET /scanner/latest` and `GET /analysis/scan/latest`.
- **FR-007**: When `SCANNER_UNIFIED_LATEST_ENABLED == False`, `GET /scanner/latest` and `GET /analysis/scan/latest` MUST execute their legacy code paths independently (preserving Sprint 1 baseline execution).
- **FR-008**: When `SCANNER_UNIFIED_LATEST_ENABLED == True`, both `GET /scanner/latest` and `GET /analysis/scan/latest` MUST delegate scan retrieval to `LatestScanService`.
- **FR-009**: Endpoint delegation MUST preserve full compatibility with Sprint 1 Redis caching (`scanner_cache_service`), passing cache key generation and `X-Cache-Status` header generation through the unified service layer.
- **FR-010**: Support for `force=true` query parameter and `Cache-Control: no-cache` headers MUST be fully preserved under both unified and legacy execution paths.

### 5.3 Response Adaptation & Backward Compatibility (`FR-011` to `FR-014`)
- **FR-011**: `GET /scanner/latest` response payload MUST strictly conform to the existing JSON schema:
  ```json
  {
    "scan_id": "string",
    "scan_timestamp": "ISO-8601 string",
    "last_scan_completed_at": "ISO-8601 string",
    "total_scanned": 0,
    "valid_symbols": 0,
    "buy_count": 0,
    "watch_count": 0,
    "rejected_count": 0,
    "buy_candidates": [],
    "watch_candidates": [],
    "rejected_candidates": []
  }
  ```
  When no scans exist, it MUST return HTTP 200 with message `"No completed scans found"` and empty arrays.
- **FR-012**: `GET /analysis/scan/latest` response payload MUST strictly conform to the existing JSON schema:
  ```json
  {
    "available": true,
    "timestamp": "ISO-8601 string",
    "total_symbols": 0,
    "buy_signals": 0,
    "watch_signals": 0,
    "no_signals": 0,
    "items": []
  }
  ```
  When no scans exist, it MUST return HTTP 200 with payload `{"available": false}`.
- **FR-013**: Response headers MUST remain identical, including `Content-Type: application/json` and `X-Cache-Status` (`HIT`, `MISS`, `BYPASS`, `FALLBACK`).
- **FR-014**: HTTP Status Codes MUST remain identical across all scenarios (200 OK for valid/empty responses, 500 for unhandled backend failures).

### 5.4 Logging and Metrics (`FR-015` to `FR-017`)
- **FR-015**: Unified execution MUST output structured diagnostic logs via `log_dashboard_request` including `endpoint`, `scan_id`, `returned_records`, and `query_duration_ms`.
- **FR-016**: Metrics collection MUST accurately record cache hits, misses, force refreshes, and database execution durations tagged by endpoint name.
- **FR-017**: Error events in `LatestScanService` MUST be logged at `ERROR` level with stack traces without leaking raw database exceptions to API clients.

---

## 6. Architecture

### 6.1 Current Architecture vs. Future Unified Architecture

```
Current Duplicated Architecture:

   ┌──────────────────────────┐          ┌──────────────────────────┐
   │    GET /scanner/latest   │          │ GET /analysis/scan/latest│
   └────────────┬─────────────┘          └────────────┬─────────────┘
                │                                     │
                ▼                                     ▼
   ┌──────────────────────────┐          ┌──────────────────────────┐
   │   [routes/scanner.py]    │          │   [routes/analysis.py]   │
   └────────────┬─────────────┘          └────────────┬─────────────┘
                │                                     │
                ▼                                     ▼
   ┌──────────────────────────┐          ┌──────────────────────────┐
   │ LatestScanService        │          │ scan_store               │
   │ .get_latest_completed... │          │ .load_latest_scan()      │
   └────────────┬─────────────┘          └────────────┬─────────────┘
                │                                     │
                ▼                                     ▼
   ┌──────────────────────────┐          ┌──────────────────────────┐
   │ PostgreSQL               │          │ PostgreSQL               │
   │ (scan_snapshots)         │          │ (scan_results)           │
   └──────────────────────────┘          └──────────────────────────┘


Future Unified Architecture (Sprint 2):

   ┌──────────────────────────┐          ┌──────────────────────────┐
   │    GET /scanner/latest   │          │ GET /analysis/scan/latest│
   └────────────┬─────────────┘          └────────────┬─────────────┘
                │                                     │
                └──────────────────┬──────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────┐
                  │ Feature Flag Router             │
                  │ (SCANNER_UNIFIED_LATEST_ENABLED)│
                  └────────────────┬────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────┐
                  │ LatestScanService (Canonical)   │
                  │ .get_latest_scan()              │
                  └────────────────┬────────────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
        ┌──────────────────────────┐┌──────────────────────────┐
        │ Redis Cache (Sprint 1)   ││ Repository Layer         │
        │ (Cache-Aside / Singleflight)│ (Canonical Snapshot DB) │
        └──────────────────────────┘└────────────┬─────────────┘
                                                 │
                                                 ▼
                                    ┌──────────────────────────┐
                                    │ PostgreSQL Database      │
                                    └──────────────────────────┘
```

### 6.2 Architectural Justification
1. **Decoupling Route Handlers from Data Access**: Route handlers in `routes/scanner.py` and `routes/analysis.py` become thin HTTP adapters focused purely on request parameter extraction, feature flag evaluation, and HTTP response building.
2. **Single Business Domain Model**: `LatestScanService` acts as the single domain service for scan retrieval. Any change to how "latest scan" is defined (e.g., handling pending scans, multi-timeframe filtering) automatically applies to all entry points.
3. **Encapsulated Cache Strategy**: Redis cache reads and writes are managed through a unified service pattern, eliminating redundant cache lookup boilerplate in route files.

---

## 7. Component Design

### 7.1 API Controllers (`app.routes.scanner` & `app.routes.analysis`)
- **Responsibility**: Parse HTTP request, extract `force` query flag and `Cache-Control` headers, evaluate `SCANNER_UNIFIED_LATEST_ENABLED` feature flag.
- **Routing Decision**:
  - If feature flag `OFF`: Call legacy helper (`service.get_latest_completed_scan()` or `scan_store.load_latest_scan()`).
  - If feature flag `ON`: Call `LatestScanService.get_latest_scan(format_type)`.
- **Response Formatting**: Wrap payload string/dict into FastAPI `Response(content=payload, media_type="application/json", headers={"X-Cache-Status": cache_status})`.

### 7.2 Canonical Service (`LatestScanService`)
- **Module**: `backend/app/services/latest_scan_service.py`
- **Class Methods**:
  - `get_latest_scan(format_type: str, force: bool = False, cache_enabled: bool = True) -> tuple[str, str]`: Master entry point returning `(serialized_json_payload, cache_status)`.
  - `_fetch_and_adapt_scan(format_type: str) -> dict | None`: Internal helper to query repository and build appropriate format dictionary (`dashboard` or `analysis`).
  - `_format_dashboard_payload(snapshot, records) -> dict`: Constructs candidate lists sorted by score.
  - `_format_analysis_payload(snapshot, records) -> dict`: Constructs analysis payload with `available`, `items`, and summary counts.
- **Dependencies**: Injected SQLAlchemy `AsyncSession` (`db`), `scanner_cache_service`, and `settings`.

### 7.3 Repository & Data Access
- **Authoritative Data Source**: `ScanSnapshot` and `ScanSnapshotRecord` ORM tables (or `scan_store` abstraction).
- **Query Strategy**: Select newest snapshot where `status == 'COMPLETED'`, ordered by `scan_timestamp DESC`. Fall back to newest row regardless of status if no completed scan exists. Join or query child records for detailed items.

### 7.4 Cache Integration
- **Cache Service**: Uses Sprint 1 `scanner_cache_service`.
- **Cache Keys**:
  - `scanner:latest:v1` for dashboard endpoint requests.
  - `analysis:scan:latest:v1` for analysis endpoint requests.
- **Singleflight Lock**: Prevents database stampedes during concurrent cache misses.

### 7.5 Observability & Metrics
- **Diagnostics**: `log_dashboard_request(scan_id, endpoint, returned_records, query_duration_ms)`.
- **Metrics**: Invokes `record_scanner_cache_hit()`, `record_scanner_cache_miss()`, and `record_scanner_cache_force_refresh()`.

---

## 8. Data Flow

Complete request lifecycle for unified scan retrieval:

```
[ Client Request ]
       │  GET /scanner/latest OR GET /analysis/scan/latest
       ▼
[ FastAPI Router ]
       │  1. Extract `force` query parameter and `Cache-Control` header.
       │  2. Evaluate feature flag `SCANNER_UNIFIED_LATEST_ENABLED`.
       ▼
[ Feature Flag Check ]
       ├────────► (OFF) ──► Execute Legacy Pipeline (Return legacy response)
       │
       ▼ (ON)
[ LatestScanService.get_latest_scan(format_type) ]
       │
       │  3. Determine Cache Key (`scanner:latest:v1` or `analysis:scan:latest:v1`).
       │  4. Inspect `SCANNER_LATEST_CACHE_ENABLED` & `force` flag.
       ▼
[ Redis Cache Lookup ]
       ├────────► (Cache HIT) ──► Return cached JSON string + `X-Cache-Status: HIT`
       │
       ▼ (Cache MISS / Bypass / Force)
[ Singleflight Lock ]
       │  5. Acquire lock for key to prevent concurrent DB stampede.
       ▼
[ Repository Database Query ]
       │  6. Execute SQL: SELECT * FROM scan_snapshots WHERE status='COMPLETED' ORDER BY scan_timestamp DESC LIMIT 1.
       │  7. Execute SQL: SELECT * FROM scan_snapshot_records WHERE scan_id = :scan_id.
       ▼
[ Payload Adaptation ]
       │  8. Transform ORM rows into requested JSON dict (Dashboard vs Analysis format).
       │  9. Serialize payload to JSON bytes/string.
       ▼
[ Cache Store & Diagnostics ]
       │ 10. Write JSON payload to Redis cache with configured TTL.
       │ 11. Emit diagnostic log `log_dashboard_request()`.
       │ 12. Record Prometheus metrics (`cache_miss`).
       ▼
[ HTTP Response Construction ]
       │ 13. Return FastAPI `Response(content=payload, media_type="application/json", headers={"X-Cache-Status": cache_status})`.
       ▼
[ Client Response Received ]
```

---

## 9. Feature Flag Strategy

### 9.1 Configuration Identifier
- **Environment Variable**: `SCANNER_UNIFIED_LATEST_ENABLED`
- **Settings Property**: `settings.SCANNER_UNIFIED_LATEST_ENABLED` (boolean, default: `false` during initial deployment, toggled to `true` during canary rollout).

### 9.2 Execution Pathways

| Flag Value | `GET /scanner/latest` Pathway | `GET /analysis/scan/latest` Pathway |
| :--- | :--- | :--- |
| `false` (OFF) | Calls legacy `LatestScanService.get_latest_completed_scan()` in `routes/scanner.py`. | Calls legacy `scan_store.load_latest_scan()` in `routes/analysis.py`. |
| `true` (ON) | Calls `LatestScanService.get_latest_scan("dashboard")`. | Calls `LatestScanService.get_latest_scan("analysis")`. |

### 9.3 Dynamic Runtime Evaluation
- The setting MUST be evaluated per-request without requiring application server restarts.
- Configuration updates are managed via environment variables or runtime settings refresh mechanisms.

### 9.4 Rollback Strategy
If any runtime anomaly, data discrepancy, or latency spike occurs during rollout:
1. Set `SCANNER_UNIFIED_LATEST_ENABLED=false` in environment configuration.
2. Trigger settings reload or application restart.
3. System instantly reverts 100% of traffic to legacy execution paths.

---

## 10. Compatibility Requirements

### 10.1 JSON Response Guarantee
The unified service MUST produce byte-for-byte compatible JSON output structures matching Sprint 1 contract definitions:
- **`GET /scanner/latest`**: Preserves keys `scan_id`, `scan_timestamp`, `last_scan_completed_at`, `total_scanned`, `valid_symbols`, `buy_count`, `watch_count`, `rejected_count`, `buy_candidates`, `watch_candidates`, `rejected_candidates`.
- **`GET /analysis/scan/latest`**: Preserves keys `available`, `timestamp`, `total_symbols`, `buy_signals`, `watch_signals`, `no_signals`, `items`.

### 10.2 HTTP Status Codes
- `200 OK`: For all successful reads, including empty scan states.
- `500 Internal Server Error`: For unrecoverable database or service crashes.

### 10.3 Response Headers
- `Content-Type: application/json`
- `X-Cache-Status`: `HIT`, `MISS`, `BYPASS`, or `FALLBACK`.

### 10.4 Authentication and Authorization
- Identical security rules: Public read access or standard bearer token validation as configured on legacy routes. No security middleware changes.

---

## 11. Failure Handling

### 11.1 Service / Backend Failure
If an unhandled exception occurs inside `LatestScanService`:
- Exception is caught and logged at `ERROR` level with stack trace context.
- System raises an HTTP 500 exception or returns standard error JSON without exposing internal tracebacks to client.

### 11.2 Repository / Database Failure
If PostgreSQL is unreachable or times out:
- If Redis cache contains a valid snapshot, system serves the cached payload with `X-Cache-Status: HIT` or `FALLBACK`.
- If cache is empty, error is logged and a graceful degraded error response (HTTP 500) is returned.

### 11.3 Cache Failure (Redis Outage)
If Redis connection fails or times out:
- `scanner_cache_service` catches connection errors silently.
- System transparently falls back to direct database execution (`X-Cache-Status: FALLBACK` or `BYPASS`).
- API requests complete successfully without failing client calls.

### 11.4 Invalid / Corrupted Data
If database contains malformed scan records or null timestamps:
- Default values are applied (e.g. `score=0.0`, missing signals marked `null`).
- Warning is emitted to system logs (`scan.db`).

---

## 12. Non-Functional Requirements

### 12.1 Performance
- **Cached Response Latency**: p95 < 10ms for requests served from Redis cache.
- **Database Fetch Latency**: p95 < 150ms for cold database reads.
- **Overhead of Delegation**: Additional overhead introduced by unified routing abstraction MUST be < 0.5ms.

### 12.2 Reliability
- **Zero Interruption**: 100% request success rate during feature flag toggles (OFF -> ON -> OFF).
- **Data Parity**: 100% identical data returned under unified vs legacy paths.

### 12.3 Maintainability
- Code duplication reduced by 100% across scan retrieval endpoints.
- Cyclomatic complexity of route handlers reduced.

### 12.4 Observability
- All requests tracked via Prometheus counters and structured JSON logs.

---

## 13. Migration Strategy

### 13.1 Phased Implementation Approach
1. **Phase 1: Code Implementation**: Implement `LatestScanService.get_latest_scan()` adapters and add `SCANNER_UNIFIED_LATEST_ENABLED` flag (default `false`).
2. **Phase 2: Dual-Path Automated Testing**: Execute automated suite verifying identical JSON payloads from legacy vs unified paths across 100+ sample scan runs.
3. **Phase 3: Staging Deployment**: Deploy to staging environment with `SCANNER_UNIFIED_LATEST_ENABLED=true` and run continuous load/regression tests.
4. **Phase 4: Production Canary Rollout**: Enable feature flag for 10% -> 50% -> 100% of production instances.
5. **Phase 5: Legacy Code Deprecation**: After 14 days of zero production errors, remove legacy fallback paths.

---

## 14. Acceptance Criteria

- **AC-001**: `GET /scanner/latest` returns identical JSON schema and data values under both `SCANNER_UNIFIED_LATEST_ENABLED=false` and `SCANNER_UNIFIED_LATEST_ENABLED=true`.
- **AC-002**: `GET /analysis/scan/latest` returns identical JSON schema and data values under both `SCANNER_UNIFIED_LATEST_ENABLED=false` and `SCANNER_UNIFIED_LATEST_ENABLED=true`.
- **AC-003**: `LatestScanService.get_latest_scan()` serves as the single source of business logic for scan resolution when feature flag is `ON`.
- **AC-004**: Setting `SCANNER_UNIFIED_LATEST_ENABLED=false` instantly restores legacy execution paths with zero application restart requirement.
- **AC-005**: All existing API client applications operate without any modifications, error spikes, or breaking changes.
- **AC-006**: Redis cache hits, misses, force refreshes (`force=true`), and `X-Cache-Status` headers function identically under the unified service.
- **AC-007**: Response latency p95 remains < 10ms for cached hits and < 150ms for database reads.
- **AC-008**: 100% of unit tests, integration tests, and API compatibility tests pass clean in CI.

---

## 15. Risks & Mitigation

| Risk Category | Identified Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Compatibility** | Minor payload key order or null field mismatch between legacy and unified endpoints. | Medium | Run automated dual-path contract comparison tests verifying exact JSON diff parity before enabling flag. |
| **Performance** | Performance overhead introduced by dynamic format adaptation logic. | Low | Benchmark adapter functions to ensure memory allocations and CPU duration remain under 0.5ms per call. |
| **Operational** | Cache invalidation key collision or desynchronization between endpoints. | Medium | Reuse Sprint 1 isolated Redis cache keys (`scanner:latest:v1` and `analysis:scan:latest:v1`). |
| **Rollout** | Database lock contention if both endpoints hit DB simultaneously on cache miss. | High | Singleflight lock in `scanner_cache_service` coalesces concurrent requests into a single database read. |

---

## 16. Metrics

| Metric Name | Type | Description | Target |
| :--- | :--- | :--- | :--- |
| `http_requests_total{endpoint="/scanner/latest"}` | Counter | Total requests to `/scanner/latest` | Track traffic volume |
| `http_requests_total{endpoint="/analysis/scan/latest"}` | Counter | Total requests to `/analysis/scan/latest` | Track traffic volume |
| `latest_scan_service_invocations_total{format="..."}` | Counter | Invocations of canonical service | Match endpoint request volume |
| `http_request_duration_seconds{endpoint="..."}` | Histogram | Endpoint response latency | p95 < 10ms (cached), p95 < 150ms (DB) |
| `scanner_cache_status_total{endpoint="...", status="..."}` | Counter | Cache status counts (`HIT`, `MISS`, `BYPASS`) | > 90% Cache Hit ratio |

---

## 17. Testing Requirements

### 17.1 Unit Tests
- `test_latest_scan_service_unified.py`: Test `LatestScanService.get_latest_scan()` for dashboard format, analysis format, empty DB state, and invalid DB state.

### 17.2 Integration & API Compatibility Tests
- `test_unified_latest_scan_parity.py`: Execute GET requests to both endpoints with feature flag `OFF` vs `ON`. Compare JSON structures, HTTP headers, status codes, and candidate sort orders for exact equality.

### 17.3 Feature Flag & Rollback Tests
- `test_feature_flag_toggle.py`: Dynamically toggle `SCANNER_UNIFIED_LATEST_ENABLED` during active requests to verify instant pathway switching and rollback capability.

---

## 18. Rollout Plan

```
  [ Dev Phase ] ──► [ Test / CI Phase ] ──► [ Staging Phase ] ──► [ Prod Canary (10%) ] ──► [ Full Production (100%) ]
   Implement logic    Run parity suite      Enable flag ON        Monitor 24 hours         Deprecate legacy paths
```

1. **Development**: Complete code refactoring in feature branch `018-unify-latest-scan-apis`.
2. **Testing**: Run 100% automated regression and parity test suites in CI.
3. **Staging**: Deploy to staging environment with `SCANNER_UNIFIED_LATEST_ENABLED=true`.
4. **Production Canary**: Enable flag on 10% instance pool. Monitor error rates, cache hit ratios, and latency metrics for 24 hours.
5. **Full Production Enablement**: Enable flag across 100% of production instances.

---

## 19. User Scenarios & Testing *(mandatory)*

### User Story 1 - Unified Dashboard Scan Access (Priority: P1)

As a trading dashboard user, I want the dashboard to load the latest market scan snapshot reliably via `GET /scanner/latest` so that I can immediately review buy, watch, and rejected candidates.

**Why this priority**: Core user journey for trading signal visibility; highest traffic endpoint.

**Independent Test**: Can be tested by invoking `GET /scanner/latest` when `SCANNER_UNIFIED_LATEST_ENABLED=true` and verifying identical structure to legacy responses.

**Acceptance Scenarios**:
1. **Given** `SCANNER_UNIFIED_LATEST_ENABLED=true` and a completed scan snapshot exists in the database, **When** `GET /scanner/latest` is requested, **Then** return HTTP 200 OK with `buy_candidates`, `watch_candidates`, and `rejected_candidates` sorted descending by score.
2. **Given** `SCANNER_UNIFIED_LATEST_ENABLED=true` and no scan snapshots exist, **When** `GET /scanner/latest` is requested, **Then** return HTTP 200 OK with message `"No completed scans found"` and empty candidate lists.

---

### User Story 2 - Unified Analysis Scan Access (Priority: P1)

As an analytical research engine or system client, I want to fetch deep scan payloads via `GET /analysis/scan/latest` from the unified service so that research data stays perfectly synchronized with dashboard signals.

**Why this priority**: Essential for automated strategy evaluation and deep technical analysis features.

**Independent Test**: Can be tested by calling `GET /analysis/scan/latest` when flag is `true` and validating payload fields (`available`, `items`, summary counts).

**Acceptance Scenarios**:
1. **Given** `SCANNER_UNIFIED_LATEST_ENABLED=true` and a completed scan exists, **When** `GET /analysis/scan/latest` is requested, **Then** return HTTP 200 OK with `available: true` and full candidate item details.
2. **Given** `SCANNER_UNIFIED_LATEST_ENABLED=true` and no scans exist, **When** `GET /analysis/scan/latest` is requested, **Then** return HTTP 200 OK with `available: false`.

---

### User Story 3 - Dynamic Zero-Downtime Rollback (Priority: P2)

As an DevOps administrator, I want to toggle `SCANNER_UNIFIED_LATEST_ENABLED=false` at runtime so that the system immediately reverts to legacy endpoints if an anomaly is detected.

**Why this priority**: Risk mitigation for production stability during deployment.

**Independent Test**: Can be tested by toggling setting from `true` to `false` during live traffic and observing fallback to legacy code paths.

**Acceptance Scenarios**:
1. **Given** `SCANNER_UNIFIED_LATEST_ENABLED=false`, **When** requests hit `GET /scanner/latest` or `GET /analysis/scan/latest`, **Then** execute legacy route handlers with zero errors.

---

### Edge Cases
- **Database record truncation**: If scan snapshot record list contains null scores, default score to `0.0`.
- **Concurrent DB Miss Stampede**: Multiple concurrent cache miss requests trigger Singleflight lock, ensuring only one database query executes.

---

## 20. Assumptions

- Existing database schemas (`scan_snapshots`, `scan_snapshot_records`, `market_data.scan_results`) remain unchanged during Sprint 2.
- Sprint 1 Redis caching infrastructure (`scanner_cache_service`) is available and operational.
- Authentication, authorization, and CORS settings remain unchanged for both public endpoints.

---

## 21. Constraints

- **No Public API Schema Changes**: Zero breaking changes allowed for external API consumers.
- **No Task/Code Generation in Spec Phase**: This specification defines architecture and behavioral requirements only.
- **Zero-Downtime Rollback**: Feature flag evaluation must support zero-downtime runtime switching.

---

## 22. Out of Scope

- Modifying write paths or scan ingestion routines (`ScreenerService`, `OrchestratorAgent`).
- Creating new HTTP endpoints or changing URL route prefixes.
- Schema migrations or database DDL changes.
- Modifying authentication or authorization middleware.
