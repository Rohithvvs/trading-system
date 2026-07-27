# Implementation Plan: Unify Latest-Scan APIs

**Branch**: `018-unify-latest-scan-apis` | **Date**: 2026-07-27 | **Spec**: [`specs/018-unify-latest-scan-apis/spec.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/spec.md)  
**Input**: Sprint 2 Specification from `specs/018-unify-latest-scan-apis/spec.md`

---

## Technical Context

- **Language/Version**: Python 3.11+
- **Primary Dependencies**: FastAPI, SQLAlchemy (AsyncSession / asyncpg), Pydantic v2
- **Storage**: PostgreSQL (tables: `scan_snapshots`, `scan_snapshot_records`, `market_data.scan_results`), Redis (via `scanner_cache_service`)
- **Testing**: pytest (`pytest-asyncio`, `httpx.AsyncClient`)
- **Target Platform**: Linux / Windows Python runtime (FastAPI ASGI server)
- **Project Type**: Web Service / REST API Backend
- **Performance Goals**: p95 < 10ms for cached responses; p95 < 150ms for cold database reads; < 0.5ms adaptation overhead.
- **Constraints**: 100% backward compatibility required; 0 breaking changes to public contracts; feature flag protected (`SCANNER_UNIFIED_LATEST_ENABLED`).
- **Scale/Scope**: Serves high-frequency dashboard polls and background analytical engine consumers.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- [x] **Principle 1 (Library-First / Modular Architecture)**: Refactoring consolidates query & transformation logic into `LatestScanService` module without introducing global state.
- [x] **Principle 2 (Interface Separation & Contracts)**: Public API contracts remain 100% untouched; thin controller layers delegate to clean service interfaces.
- [x] **Principle 3 (Test-First & Parity Validation)**: Dual-path parity tests verify legacy vs unified path equality prior to feature flag enablement.
- [x] **Principle 4 (Integration Testing)**: End-to-end route tests verify Redis cache headers (`X-Cache-Status`) and response status codes.
- [x] **Principle 5 (Observability & Versioning)**: Retains structured JSON diagnostic logging (`log_dashboard_request`) and Prometheus metric tracking.

---

## Project Structure

### Documentation (`specs/018-unify-latest-scan-apis/`)

```text
specs/018-unify-latest-scan-apis/
├── spec.md              # Feature specification
├── plan.md              # Implementation Plan (this document)
├── research.md          # Phase 0 research decisions & context
├── data-model.md        # Phase 1 data model & payload schemas
├── quickstart.md        # Phase 1 validation guide & test scenarios
└── contracts/           # Phase 1 API contract definitions
    └── api-contracts.md
```

### Source Code Paths (Repository Root)

```text
backend/app/
├── routes/
│   ├── scanner.py       # Controller for GET /scanner/latest (delegates to LatestScanService)
│   └── analysis.py      # Controller for GET /analysis/scan/latest (delegates to LatestScanService)
├── services/
│   ├── latest_scan_service.py # Canonical service implementing get_latest_scan()
│   └── scanner_cache_service.py # Sprint 1 Redis cache service (reused without duplication)
├── config/
│   └── settings.py      # Feature flag SCANNER_UNIFIED_LATEST_ENABLED
└── db/
    └── scan_store.py    # Repository read layer for scan persistence

tests/
├── unit/
│   └── test_latest_scan_service.py # Unit tests for LatestScanService format adapters
└── integration/
    ├── test_scanner_routes_cached.py # Contract and caching integration tests
    └── test_unified_latest_scan_parity.py # Dual-path parity verification tests
```

---

## 1. Executive Summary

### 1.1 Implementation Strategy
Sprint 2 introduces a single canonical service method—`LatestScanService.get_latest_scan(format_type: str, force: bool)`—to unify the fetching, sorting, adaptation, and caching of the latest completed scanner results across the application. 

The two existing public endpoints (`GET /scanner/latest` and `GET /analysis/scan/latest`) will be modified to act as thin HTTP controllers. When the feature flag `SCANNER_UNIFIED_LATEST_ENABLED` is `ON`, both controllers will delegate scan retrieval to `LatestScanService`. When the feature flag is `OFF`, both controllers will execute their existing legacy routines.

### 1.2 Expected Technical Outcome
- 100% elimination of duplicated business logic for scan snapshot lookup, sorting, and payload preparation.
- Complete reuse of Sprint 1 Redis caching infrastructure (`scanner_cache_service`) with zero duplicated Redis query code.
- Zero breaking changes to public HTTP contracts, status codes, query parameters, or response headers.

### 1.3 Expected Business Outcome
- Reduced ongoing maintenance complexity and bug risk.
- Absolute data consistency between dashboard signal views and analytical engine views.
- Accelerated velocity for future scanner enhancements (e.g. multi-timeframe filtering), which will require updates in only one codebase location.

---

## 2. Architecture Plan

### 2.1 Current vs. Future Architecture

```
Current Legacy Architecture:

   Client ──► GET /scanner/latest ──► [routes/scanner.py] ──► LatestScanService.get_latest_completed_scan() ──► ORM (scan_snapshots)
   Client ──► GET /analysis/scan/latest ──► [routes/analysis.py] ──► scan_store.load_latest_scan() ──► Raw JSONB (scan_results)


Future Unified Architecture (Sprint 2):

   Client ──► GET /scanner/latest ─────────┐
                                           ├─► Feature Flag Router ─► LatestScanService.get_latest_scan() ─┬─► Redis Cache (Sprint 1)
   Client ──► GET /analysis/scan/latest ───┘   (SCANNER_UNIFIED_LATEST_ENABLED)                           └─► DB Repository (ORMs)
```

### 2.2 Architectural Justification
- **Single Responsibility Principle (SRP)**: Controllers focus strictly on HTTP request parsing and response delivery. `LatestScanService` owns 100% of domain business logic for scan snapshot resolution.
- **Single Source of Truth (SSOT)**: Guarantees that both dashboard users and analytical engines read from the exact same snapshot selection criteria (`status == 'COMPLETED'`, ordered by `scan_timestamp DESC`).
- **Encapsulated Cache Strategy**: Reuses Sprint 1 `scanner_cache_service` Singleflight lock and TTL mechanisms, preventing cache stampedes.

---

## 3. Component Impact Analysis

| Component | Current Responsibility | Required Modification | Reason for Change | Impact on Surrounding Components |
| :--- | :--- | :--- | :--- | :--- |
| **API Controller (`scanner.py`)** | Executes ORM queries & cache lookups for `/scanner/latest`. | Add feature flag check. If `true`, delegate to `LatestScanService.get_latest_scan("dashboard")`. | Remove duplicate logic & delegate to canonical service. | Zero contract change; clients receive identical JSON. |
| **API Controller (`analysis.py`)** | Executes `scan_store` queries for `/analysis/scan/latest`. | Add feature flag check. If `true`, delegate to `LatestScanService.get_latest_scan("analysis")`. | Remove duplicate logic & delegate to canonical service. | Zero contract change; clients receive identical JSON. |
| **Canonical Service (`latest_scan_service.py`)** | Handles ORM snapshot persistence and dashboard fetch. | Add `get_latest_scan(format_type, force)`. Implement format adapters (`dashboard` & `analysis`). | Establish canonical service layer for all endpoints. | Core service consumed by both controllers. |
| **Cache Layer (`scanner_cache_service.py`)** | Manages Redis reads/writes & Singleflight locks. | No modification required. Reused as-is by `LatestScanService`. | Reuses Sprint 1 cache implementation without duplication. | None; operates as shared utility. |
| **Settings (`settings.py`)** | Manages app configuration. | Add `SCANNER_UNIFIED_LATEST_ENABLED` boolean property. | Guard unified delegation behind dynamic feature flag. | Configured via environment variables. |
| **Observability (`scan_diagnostics.py`)** | Logs dashboard requests & snapshot stats. | Invoked within `LatestScanService.get_latest_scan()`. | Ensure diagnostic logging remains active. | Standard logging output. |

---

## 4. Module Breakdown

### 4.1 `LatestScanService` (`backend/app/services/latest_scan_service.py`)
- **Responsibilities**: Query database for newest completed scan, apply fallback rules if no completed scan exists, format data for requested target (`"dashboard"` or `"analysis"`), resolve cache via `scanner_cache_service`.
- **Inputs**: `db: AsyncSession`, `format_type: str`, `force: bool`, `cache_enabled: bool`.
- **Outputs**: Tuple `(serialized_payload: str, cache_status: str)`.
- **Dependencies**: `ScanSnapshot`, `ScanSnapshotRecord`, `scanner_cache_service`, `settings`, `log_dashboard_request`.
- **Ownership**: Core Backend Engineering Team.

### 4.2 Scanner Controller (`backend/app/routes/scanner.py`)
- **Responsibilities**: Handle `GET /scanner/latest`, inspect `force` flag and feature flag, invoke service, return HTTP 200 response with `X-Cache-Status`.
- **Inputs**: `request: Request`, `force: bool`, `db: AsyncSession`.
- **Outputs**: FastAPI `Response(content=payload, media_type="application/json")`.
- **Ownership**: Core Backend Engineering Team.

### 4.3 Analysis Controller (`backend/app/routes/analysis.py`)
- **Responsibilities**: Handle `GET /analysis/scan/latest`, inspect `force` flag and feature flag, invoke service, return HTTP 200 response with `X-Cache-Status`.
- **Inputs**: `request: Request`, `force: bool`.
- **Outputs**: FastAPI `Response(content=payload, media_type="application/json")`.
- **Ownership**: Core Backend Engineering Team.

---

## 5. Implementation Strategy

### Phase 1: Preparation & Infrastructure (Pre-Coding)
1. Verify feature flag configuration `SCANNER_UNIFIED_LATEST_ENABLED` in `backend/app/config/settings.py`.
2. Ensure test baseline suite (`test_scanner_routes_cached.py`) passes 100% clean.

### Phase 2: Canonical Service Enhancement
1. Implement `LatestScanService.get_latest_scan(format_type: str, force: bool = False)` in `backend/app/services/latest_scan_service.py`.
2. Implement format adapters:
   - `_format_dashboard_payload(snapshot, records)`
   - `_format_analysis_payload(snapshot, records)`
3. Integrate `scanner_cache_service.resolve_latest_scan()` into `get_latest_scan()`.

### Phase 3: Route Controller Migration
1. Update `GET /scanner/latest` in `backend/app/routes/scanner.py`:
   - Check `settings.is_scanner_unified_latest_enabled()`.
   - If `true`, call `service.get_latest_scan("dashboard", force=force_refresh)`.
   - If `false`, execute existing legacy path.
2. Update `GET /analysis/scan/latest` in `backend/app/routes/analysis.py`:
   - Check `settings.is_scanner_unified_latest_enabled()`.
   - If `true`, call `service.get_latest_scan("analysis", force=force_refresh)`.
   - If `false`, execute existing legacy path.

### Phase 4: Dual-Path Validation & Parity Testing
1. Create integration test `test_unified_latest_scan_parity.py`.
2. Run test suite verifying that for 100+ simulated scans, response payloads under `ON` vs `OFF` are 100% byte-identical.

### Phase 5: Rollout & Cleanup
1. Deploy code to Staging environment; set `SCANNER_UNIFIED_LATEST_ENABLED=true`.
2. Perform Canary rollout to Production (10% -> 50% -> 100%).
3. After 14 days of error-free production operation, deprecate legacy code branches.

---

## 6. Dependency Analysis

- **Internal Dependencies**: `backend/app/services/latest_scan_service.py`, `backend/app/routes/scanner.py`, `backend/app/routes/analysis.py`, `backend/app/config/settings.py`.
- **External Dependencies**: Redis (via `aioredis` / `scanner_cache_service`), PostgreSQL database engine.
- **Repository Dependencies**: SQLAlchemy `AsyncSession` database session injected via FastAPI `Depends(get_db)`.
- **Cache Dependencies**: `scanner_cache_service` managing keys `scanner:latest:v1` and `analysis:scan:latest:v1`.
- **Runtime Dependencies**: Python 3.11 async event loop (`asyncio`).

---

## 7. Request Flow

```
Sequence Diagram: Unified Scan Retrieval Flow

Client           FastAPI Router        FeatureFlag      LatestScanService     Redis Cache       PostgreSQL DB
  │                    │                    │                   │                  │                  │
  │ GET /scanner/latest│                    │                   │                  │                  │
  ├───────────────────►│                    │                   │                  │                  │
  │                    │ Check Feature Flag │                   │                  │                  │
  │                    ├───────────────────►│                   │                  │                  │
  │                    │                    │ Return ON (True)  │                  │                  │
  │                    │◄───────────────────┤                   │                  │                  │
  │                    │                    │                   │                  │                  │
  │                    │ get_latest_scan("dashboard")           │                  │                  │
  │                    ├───────────────────────────────────────►│                  │                  │
  │                    │                                        │ Check Cache      │                  │
  │                    │                                        ├─────────────────►│                  │
  │                    │                                        │                  │                  │
  │                    │                                        │◄─ [Cache HIT] ───┤ (Return Fast)    │
  │                    │                                        │                  │                  │
  │                    │                                        │ (If Cache MISS)  │                  │
  │                    │                                        │ Query Snapshot   │                  │
  │                    │                                        ├────────────────────────────────────►│
  │                    │                                        │                  │                  │
  │                    │                                        │◄── Snapshot DB Row ─────────────────┤
  │                    │                                        │                  │                  │
  │                    │                                        │ Adapt & Store Cache                 │
  │                    │                                        ├─────────────────►│                  │
  │                    │                                        │                  │                  │
  │                    │ Return Response Payload + X-Cache-Status│                  │                  │
  │◄───────────────────┴────────────────────────────────────────┤                  │                  │
```

---

## 8. Feature Flag Strategy

- **Flag Identifier**: `SCANNER_UNIFIED_LATEST_ENABLED`
- **Default Value**: `false` (Legacy path active on initial code deployment).
- **Runtime Evaluation**: Evaluated dynamically on every HTTP request via `settings.is_scanner_unified_latest_enabled()`.
- **Rollout Sequence**:
  - `false` in local development / baseline CI.
  - `true` in integration test suites.
  - `true` in Staging environment.
  - `true` enabled via environment variable in Production.
- **Rollback Protocol**: If an unexpected anomaly occurs in Production, change environment variable `SCANNER_UNIFIED_LATEST_ENABLED=false` to immediately restore legacy endpoint pathways in zero downtime.

---

## 9. Cache Integration Strategy

Sprint 2 reuses the exact Redis caching layer built in Sprint 1 without duplicating code:
- **Service Reuse**: `LatestScanService.get_latest_scan()` calls `scanner_cache_service.resolve_latest_scan()`.
- **Cache Key Preservation**:
  - Dashboard format uses key `scanner:latest:v1`.
  - Analysis format uses key `analysis:scan:latest:v1`.
- **Singleflight Stampede Protection**: Retains singleflight locking per key during cache misses, ensuring that concurrent hits to `/scanner/latest` and `/analysis/scan/latest` execute exactly one underlying database query.

---

## 10. Error Handling Plan

- **Repository / Database Outage**:
  - If Redis cache contains valid snapshot, return cached payload with `X-Cache-Status: HIT` or `FALLBACK`.
  - If cache is empty and DB fails, catch exception, log error with stack trace, and return HTTP 500 error response.
- **Cache Layer Failure**:
  - `scanner_cache_service` handles Redis connection failures gracefully, falling back to direct database execution with `X-Cache-Status: FALLBACK`.
- **Invalid / Corrupted Data**:
  - Default fallbacks applied for missing indicators (`score=0.0`, missing signals `null`).
- **Concurrent Request Stampede**:
  - Coalesced by Singleflight lock in `scanner_cache_service`.

---

## 11. Performance Plan

- **Reduced Duplicated Processing**: Refactoring removes duplicate snapshot selection logic, keeping CPU overhead < 0.5ms.
- **Cache Hit Latency**: p95 < 10ms for cached responses.
- **Cold Read Latency**: p95 < 150ms for cold database reads.
- **Database Query Count**: Exactly 1 snapshot parent query + 1 record child query per cache miss across both endpoints.

---

## 12. Risk Assessment

| Risk | Impact | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Payload Schema Parity Mismatch** | High | Low | Run dual-path integration tests (`test_unified_latest_scan_parity.py`) verifying exact JSON key/value parity before enabling flag. |
| **Redis Cache Key Collision** | Medium | Low | Maintain distinct, isolated cache keys (`scanner:latest:v1` vs `analysis:scan:latest:v1`). |
| **Feature Flag Overhead** | Low | Low | Feature flag is a fast in-memory boolean property check in `settings.py`. |

---

## 13. Validation Plan

Before entering the Task Generation (`/speckit-tasks`) phase:
1. All design artifacts (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/api-contracts.md`) are complete and consistent.
2. The Constitution Check passes with 0 unmitigated violations.
3. Dual-path testing strategy is defined to guarantee zero regression.

---

## 14. Monitoring Plan

The following metrics and logs will monitor the unified service:
- **Prometheus Metrics**:
  - `http_requests_total{endpoint="/scanner/latest"}`
  - `http_requests_total{endpoint="/analysis/scan/latest"}`
  - `scanner_cache_status_total{endpoint="...", status="HIT|MISS|FALLBACK"}`
  - `http_request_duration_seconds{endpoint="..."}`
- **Diagnostic Logging**:
  - `log_dashboard_request(scan_id, endpoint, returned_records, query_duration_ms)` emitted on every request.

---

## 15. Rollout Plan

1. **Development**: Implement `LatestScanService.get_latest_scan()` and update route controllers behind `SCANNER_UNIFIED_LATEST_ENABLED`.
2. **Automated Testing**: Run unit and dual-path integration test suites in CI pipeline.
3. **Staging Validation**: Enable `SCANNER_UNIFIED_LATEST_ENABLED=true` in Staging for 48 hours of continuous verification.
4. **Production Canary**: Deploy to 10% of Production instances. Monitor error rates, cache hit ratios, and latency.
5. **Full Enablement**: Expand to 100% Production instances.
6. **Legacy Code Cleanup**: Remove legacy code branches after 14 days of error-free operation.

---

## 16. Assumptions

- Existing database tables (`scan_snapshots` and `scan_snapshot_records`) remain unchanged.
- Sprint 1 Redis cache service (`scanner_cache_service`) remains fully operational.
- Existing frontend clients require zero modifications.

---

## 17. Constraints

- **Zero Breaking Changes**: Must preserve exact JSON schemas, HTTP status codes, headers, and query parameters.
- **No Task / Code Generation in Plan Phase**: Defines technical architecture and implementation roadmap only.
- **Protected by Feature Flag**: All unified delegation code MUST execute conditionally based on `SCANNER_UNIFIED_LATEST_ENABLED`.

---

## 18. Deliverables

Before advancing to Task Generation (`/speckit-tasks`):
- [x] Feature Specification: [`specs/018-unify-latest-scan-apis/spec.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/spec.md)
- [x] Implementation Plan: [`specs/018-unify-latest-scan-apis/plan.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/plan.md)
- [x] Phase 0 Research Artifact: [`specs/018-unify-latest-scan-apis/research.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/research.md)
- [x] Phase 1 Data Model Artifact: [`specs/018-unify-latest-scan-apis/data-model.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/data-model.md)
- [x] Phase 1 API Contracts Artifact: [`specs/018-unify-latest-scan-apis/contracts/api-contracts.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/contracts/api-contracts.md)
- [x] Phase 1 Quickstart Validation Artifact: [`specs/018-unify-latest-scan-apis/quickstart.md`](file:///D:/Work_Space/trading-system/specs/018-unify-latest-scan-apis/quickstart.md)
