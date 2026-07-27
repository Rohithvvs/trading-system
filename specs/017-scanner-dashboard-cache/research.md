# Technical Research & Architecture Decisions: Scanner Dashboard Cache

**Feature Branch**: `017-scanner-dashboard-cache`  
**Created**: 2026-07-27  
**Status**: Completed  
**Feature Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md)

---

## 1. Research Topic: Redis Async Client Strategy in FastAPI / Python

### Decision
Use `redis.asyncio` (built into `redis-py` >= 4.2.0) with a connection pool initialized during FastAPI application startup.

### Rationale
- `redis.asyncio` is the official async client in modern `redis-py`, fully integrated with Python `asyncio`.
- Connection pooling prevents connection creation overhead on every HTTP request.
- Non-blocking I/O ensures the FastAPI main event loop is never stalled by cache operations.

### Alternatives Considered
- `aioredis` (Deprecated): Merged into `redis-py` 4.x; maintaining separate legacy dependency introduces maintenance risk.
- Sync `redis` client with thread pool executor: Introduces unnecessary thread context switches and overhead compared to native async socket IO.

---

## 2. Research Topic: Cache Stampede (Thundering Herd) Prevention

### Decision
Combine an in-process `asyncio.Lock` (Singleflight per instance) with a Redis `SETNX` distributed lock with a short 5-second TTL.

### Rationale
- When cache expires or is cold under 500 concurrent requests, multiple workers/threads will attempt to execute identical heavy PostgreSQL queries simultaneously.
- `asyncio.Lock` prevents multiple concurrent coroutines in the same API instance from executing the SQL query simultaneously.
- Redis `SETNX` (or `redis.lock.Lock`) ensures across multiple API replica containers that only 1 single instance queries PostgreSQL while others wait for the lock or poll the updated cache key.

### Alternatives Considered
- Probabilistic Early Expiration (XFetch algorithm): Effective for continuous high throughput, but adds complex math overhead; singleflight lock is deterministic and simpler for Sprint 1.
- No Lock (Allow concurrent miss reads): Causes severe database CPU spikes and connection pool starvation during cache expiration.

---

## 3. Research Topic: Serialization & Payload Storage Format

### Decision
Store pre-serialized JSON strings directly in Redis (`GET` / `SET`) and return a `fastapi.responses.Response(content=cached_json, media_type="application/json")`.

### Rationale
- Storing already-serialized JSON strings in Redis avoids the CPU overhead of deserializing JSON from Redis into Python dicts only to re-serialize them back to JSON in FastAPI's response middleware.
- Response time for cache hits drops to <5ms since it is a direct byte pass-through from Redis to the client HTTP socket.

### Alternatives Considered
- Storing Python dicts or Redis Hashes: Requires extra deserialization and CPU work on every read, increasing p95 latency.
- Binary MsgPack / Pickle: Breaks human debuggability via `redis-cli` and requires CPU conversion to JSON for HTTP response.

---

## 4. Research Topic: Scan Completion Active Pre-Warming Hook

### Decision
Inject an active cache write (`SET key json EX ttl`) directly into the background market scan worker's completion pipeline.

### Rationale
- Per approved specification clarification (Option B), active pre-warming ensures 100% cache hit rate for dashboard users immediately following a market scan run.
- Eliminates cold-cache database read penalties on the first user load post-scan.

### Alternatives Considered
- Simple Invalidation (`DEL` key): Next user request suffers a database query read penalty. Rejected based on clarification choice.
