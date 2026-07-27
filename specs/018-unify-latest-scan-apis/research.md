# Phase 0 Research: Unify Latest-Scan APIs

**Feature**: Unify Latest-Scan APIs  
**Branch**: `018-unify-latest-scan-apis`  
**Date**: 2026-07-27  

## Research Decisions & Rationale

### 1. Canonical Service Strategy
- **Decision**: Extend `LatestScanService` in `backend/app/services/latest_scan_service.py` with a unified method `get_latest_scan(format_type: str, force: bool = False)` that delegates payload creation to format-specific adapters (`_format_dashboard_payload` vs `_format_analysis_payload`).
- **Rationale**: Keeps all scan loading, snapshot fallback selection (`COMPLETED` status filtering), and scoring logic within a single service class, minimizing code duplication and avoiding multi-service dependencies.
- **Alternatives Considered**:
  - *Option A: Create a brand new service file `unified_scan_service.py`*: Rejected because `LatestScanService` already handles scan snapshot persistence and scanner latest queries. Creating a second service file would add unnecessary structural fragmentation.
  - *Option B: Call `scan_store.load_latest_scan()` inside `LatestScanService`*: Rejected because `scan_store` queries `market_data.scan_results` JSONB directly, whereas `LatestScanService` queries ORM tables `ScanSnapshot` and `ScanSnapshotRecord`, which provide richer candidate details and score sorting.

### 2. Response Adapter Pattern
- **Decision**: Define explicit output format adapters inside `LatestScanService`:
  - `format_type="dashboard"`: Returns `{ scan_id, scan_timestamp, total_scanned, valid_symbols, buy_count, watch_count, rejected_count, buy_candidates, watch_candidates, rejected_candidates }`.
  - `format_type="analysis"`: Returns `{ available: true/false, timestamp, total_symbols, buy_signals, watch_signals, no_signals, items: [...] }`.
- **Rationale**: Allows both endpoints to share 100% of the database retrieval, fallback query, and caching mechanisms, while rendering their required legacy JSON structures without breaking schema contracts.
- **Alternatives Considered**:
  - *Option A: Force frontend to adapt to a single unified schema*: Rejected because Sprint 2 strictly forbids changing public API contracts or requiring frontend changes.

### 3. Sprint 1 Redis Cache Integration
- **Decision**: Reuse existing `scanner_cache_service` in `backend/app/services/scanner_cache_service.py` with existing keys (`scanner:latest:v1` and `analysis:scan:latest:v1`). The unified `LatestScanService.get_latest_scan()` invokes `scanner_cache_service.resolve_latest_scan()` passing the format-specific JSON generator function.
- **Rationale**: Completely reuses Sprint 1 caching, singleflight stampede prevention, TTL management, and `X-Cache-Status` header generation without duplicating Redis cache logic.

### 4. Feature Flag Protection (`SCANNER_UNIFIED_LATEST_ENABLED`)
- **Decision**: Add boolean property `SCANNER_UNIFIED_LATEST_ENABLED` to `backend/app/config/settings.py` (environment variable default `false`).
- **Rationale**: Allows instant per-request toggling. If `false`, route handlers call legacy methods (`service.get_latest_completed_scan()` or `scan_store.load_latest_scan()`). If `true`, route handlers call `service.get_latest_scan("dashboard"|"analysis")`.

---

## Technical Context Summary

- **Language/Version**: Python 3.11+
- **Framework**: FastAPI (Async ecosystem)
- **Database**: PostgreSQL (SQLAlchemy AsyncSession with asyncpg)
- **Caching**: Redis (aioredis / `scanner_cache_service` with Singleflight Lock)
- **Feature Flag**: Environment setting `SCANNER_UNIFIED_LATEST_ENABLED`
- **Testing**: pytest (`pytest-asyncio`, `httpx.AsyncClient`)
