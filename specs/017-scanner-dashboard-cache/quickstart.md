# Quickstart & Verification Guide: Scanner Dashboard Cache

**Feature Branch**: `017-scanner-dashboard-cache`  
**Created**: 2026-07-27  
**Status**: Completed  
**Feature Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md)

---

## 1. Prerequisites & Environment Setup

Ensure Redis is running locally or in Docker container:
```bash
docker run -d --name redis-trading -p 6379:6379 redis:alpine
```

Set environment variables in `.env`:
```env
SCANNER_LATEST_CACHE_ENABLED=true
SCANNER_LATEST_CACHE_TTL_SECONDS=300
REDIS_URL=redis://localhost:6379/0
```

---

## 2. End-to-End Test & Verification Scenarios

### Scenario 1: Feature Flag Disabled Baseline Test
1. Set `SCANNER_LATEST_CACHE_ENABLED=false`.
2. Send GET request to `/scanner/latest`:
   ```bash
   curl -i http://localhost:8000/scanner/latest
   ```
3. **Expected Outcome**:
   - HTTP 200 returned.
   - Header `X-Cache-Status: BYPASS` is present.
   - Database SQL query log executes.

---

### Scenario 2: Cold Cache Fill (Cache Miss)
1. Flush Redis: `redis-cli FLUSHALL`.
2. Set `SCANNER_LATEST_CACHE_ENABLED=true`.
3. Send GET request:
   ```bash
   curl -i http://localhost:8000/scanner/latest
   ```
4. **Expected Outcome**:
   - HTTP 200 returned.
   - Header `X-Cache-Status: MISS`.
   - Redis key `scanner:latest:v1` is created with TTL 300.

---

### Scenario 3: Hot Cache Hit (<10ms Response)
1. Execute second GET request immediately following Scenario 2:
   ```bash
   curl -i http://localhost:8000/scanner/latest
   ```
2. **Expected Outcome**:
   - HTTP 200 returned.
   - Header `X-Cache-Status: HIT`.
   - Response time <10ms.
   - **Zero PostgreSQL SELECT queries** in application logs.

---

### Scenario 4: Force Refresh (`?force=true`)
1. Send GET request with `force` parameter:
   ```bash
   curl -i "http://localhost:8000/scanner/latest?force=true"
   ```
2. **Expected Outcome**:
   - HTTP 200 returned.
   - Header `X-Cache-Status: MISS` (or `BYPASS`).
   - PostgreSQL query is executed and Redis key is updated.

---

### Scenario 5: Post-Scan Active Pre-Warming
1. Trigger a background scan execution.
2. Monitor Redis keys immediately upon scan completion:
   ```bash
   redis-cli GET scanner:latest:v1
   ```
3. **Expected Outcome**:
   - Key `scanner:latest:v1` holds updated JSON payload written by worker.
   - Next API read receives HTTP 200 (`X-Cache-Status: HIT`) instantly without hitting DB.

---

### Scenario 6: Redis Failure Resilience (Graceful Fallback)
1. Stop Redis server (`docker stop redis-trading`).
2. Send GET request to `/scanner/latest`.
3. **Expected Outcome**:
   - HTTP 200 returned successfully.
   - Header `X-Cache-Status: FALLBACK`.
   - Application logs structured warning; Prometheus counter `scanner_cache_redis_errors_total` increments.
   - Zero HTTP 5xx errors returned to client.

---

## 3. Operations Guide (Production)

### 3.1 Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SCANNER_LATEST_CACHE_ENABLED` | `false` | Master cache toggle (safe rollout default OFF). |
| `SCANNER_LATEST_CACHE_TTL_SECONDS` | `300` | Redis key TTL (≥ 10). |
| `REDIS_CACHE_READ_TIMEOUT_MS` | `50` | Max Redis GET wait before DB fallback. |
| `REDIS_CACHE_WRITE_TIMEOUT_MS` | `100` | Max Redis SET/DEL wait. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string. |

### 3.2 Response header `X-Cache-Status`

| Value | Meaning |
|---|---|
| `HIT` | Served from Redis. |
| `MISS` | Cache miss or force-refresh refill from PostgreSQL. |
| `BYPASS` | Flag disabled; no Redis read/write on the request path. |
| `FALLBACK` | Redis error/timeout; response from PostgreSQL. |

### 3.3 Rollback without code redeploy (audit H5)

`settings.is_scanner_latest_cache_enabled()` is evaluated **on every request**:

1. If `os.environ["SCANNER_LATEST_CACHE_ENABLED"]` is set (non-empty), that value wins and the settings attribute is synced.
2. Otherwise the in-process `settings.scanner_latest_cache_enabled` attribute is used.

**Rollback options (no code redeploy):**

| Method | How | Restart needed? |
|---|---|---|
| Process env inject | Set `SCANNER_LATEST_CACHE_ENABLED=false` in the running process environment (sidecar/agent that mutates env) | **No** (next request) |
| In-process attribute | `settings.scanner_latest_cache_enabled = False` | **No** |
| Container/env file | Update deployment env + restart/roll pods | Yes (normal k8s path) |

### 3.7 Staged production enablement (risk control)

Follow this sequence before leaving cache ON in production:

| Stage | Action | Success criteria |
|---|---|---|
| 1 | Deploy code with flag **false** | Dashboard unchanged; optional `X-Cache-Status: BYPASS` |
| 2 | Staging: set flag **true** | quickstart scenarios 2–6 pass; hit ratio rising |
| 3 | Production canary: flag **true** on one instance | No 5xx; `scanner_cache_redis_errors_total` quiet; p95 HIT &lt; 25ms |
| 4 | Full production ON | `scanner_cache_hit_ratio` &gt; 0.90 over 24h; SQL load down |

**Emergency rollback:** set `SCANNER_LATEST_CACHE_ENABLED=false` (env inject or attribute). Clients immediately take the PostgreSQL path.

### 3.8 Client compatibility (`X-Cache-Status`)

- Body JSON is **unchanged** vs pre-feature baseline (same keys/types when served from DB).
- `X-Cache-Status` is an **additive observability header** (`HIT`/`MISS`/`BYPASS`/`FALLBACK`).
- Browser clients that do not read custom headers are unaffected.
- If a reverse proxy strips unknown headers, metrics remain the source of truth.

### 3.4 Metrics (Prometheus)

- `scanner_cache_hits_total{endpoint=...}`
- `scanner_cache_misses_total{endpoint=...}`
- `scanner_cache_redis_errors_total{op=...}`
- `scanner_cache_force_refreshes_total{endpoint=...}`
- `scanner_cache_hit_ratio` (gauge)

### 3.5 Concurrency scope (audit M1)

Stampede protection is **two-layered**:

1. In-process `asyncio.Lock` — serializes concurrent tasks in one worker.
2. Redis `SET lock:{cache_key} NX EX 5` — serializes refills across workers/hosts (keys `lock:scanner:latest:v1`, `lock:analysis:scan:latest:v1`).

Workers that do not acquire the distributed lock poll Redis for the filled payload instead of querying PostgreSQL.

### 3.6 Pre-warm keys after scan completion

| Redis key | Writer | Schema |
|---|---|---|
| `analysis:scan:latest:v1` | `save_latest_scan` (orjson) | `{"available": true, ...scan_store payload}` |
| `scanner:latest:v1` | `LatestScanService.prewarm_scanner_latest_cache` after persist commit | Dashboard / `LatestScanService.get_latest_completed_scan` shape |
