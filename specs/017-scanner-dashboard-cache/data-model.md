# Data Model & Configuration Specification: Scanner Dashboard Cache

**Feature Branch**: `017-scanner-dashboard-cache`  
**Created**: 2026-07-27  
**Status**: Completed  
**Feature Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md)

---

## 1. Core Entities

### 1.1 `ScannerLatestCacheEntry`
Represents a cached JSON response entry stored in Redis for scanner read endpoints.

| Attribute | Type | Description |
|---|---|---|
| `key` | String (Key) | Unique cache key namespace string (`scanner:latest:v1` or `analysis:scan:latest:v1`). |
| `payload` | String (JSON) | Pre-serialized JSON HTTP response body identical to direct DB output. |
| `ttl_seconds` | Integer | Time-To-Live in seconds (`SCANNER_LATEST_CACHE_TTL_SECONDS`, default 300). |
| `created_at` | Timestamp (ISO-8601) | Timestamp recorded inside metadata headers (optional). |

### 1.2 `CacheControlDirective`
Parsed from incoming HTTP request metadata to evaluate cache bypass rules.

| Attribute | Type | Description |
|---|---|---|
| `force_refresh` | Boolean | `true` if query param `?force=true` OR header `Cache-Control: no-cache` is present. |
| `bypass_cache` | Boolean | `true` if feature flag is disabled (`SCANNER_LATEST_CACHE_ENABLED=false`). |

---

## 2. Key Namespaces & Versioning

```
+------------------------------------+---------------------------------------+
| Endpoint                           | Redis Cache Key                       |
+------------------------------------+---------------------------------------+
| GET /scanner/latest                | scanner:latest:v1                     |
| GET /analysis/scan/latest          | analysis:scan:latest:v1               |
| Lock: GET /scanner/latest          | lock:scanner:latest:v1                |
| Lock: GET /analysis/scan/latest    | lock:analysis:scan:latest:v1          |
+------------------------------------+---------------------------------------+
```

### Versioning Rule
The `:v1` suffix isolates schema definitions. If API response structures change in future sprints, updating the key version suffix to `:v2` instantly isolates cache entries without requiring `FLUSHALL` commands on shared Redis clusters.

---

## 3. Environment & Configuration Settings

| Variable Name | Type | Default | Description | Validation Rule |
|---|---|---|---|---|
| `SCANNER_LATEST_CACHE_ENABLED` | Boolean | `false` | Master feature flag enabling cache layer. | Must be boolean `true`/`false`. |
| `SCANNER_LATEST_CACHE_TTL_SECONDS` | Integer | `300` | Expiration time for cached keys. | Must be positive integer >= 10. |
| `REDIS_CACHE_READ_TIMEOUT_MS` | Integer | `50` | Max ms for Redis GET lookup before DB fallback. | Must be integer >= 5. |
| `REDIS_CACHE_WRITE_TIMEOUT_MS` | Integer | `100` | Max ms for Redis SET write operations. | Must be integer >= 10. |
| `REDIS_URL` | String | `redis://localhost:6379/0` | Connection string for Redis instance. | Valid URI scheme `redis://` or `rediss://`. |
