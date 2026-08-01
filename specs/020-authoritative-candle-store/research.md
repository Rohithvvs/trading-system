# Research & Technical Decisions: Authoritative Candle Store (Sprint 4)

**Feature Branch**: `020-authoritative-candle-store`  
**Date**: 2026-07-27  
**Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/spec.md)  

---

## 1. Research Overview

This document resolves technical choices, design patterns, and architectural decisions for implementing Sprint 4 (Authoritative Candle Store). All decisions align strictly with the approved Sprint 4 Specification.

---

## 2. Decision Log

### Decision 1: Service Abstraction & Interface Pattern
- **Decision**: Encapsulate all candle operations inside `AuthoritativeCandleStore` service in `backend/app/services/authoritative_candle_store.py`.
- **Rationale**: Provides a single chokepoint for reading, writing, validating, and caching OHLCV candles. Downstream components (Scanner, Analysis Agent, Backtester, Dashboard API) interact exclusively with this service interface when `AUTHORITATIVE_CANDLE_STORE_ENABLED=true`.
- **Alternatives Considered**:
  - *Direct Database Layer Calls*: Rejected because it bypasses L1 memory caching and fails to centralize provider rate-limiting.
  - *Extending `MarketDataService` Directly*: Rejected to prevent bloating legacy service files and ensure clean feature-flagged separation.

### Decision 2: Multi-Tier Caching Architecture (L1 RAM + L2 DB)
- **Decision**: Implement an in-memory bounded LRU cache (L1) backed by PostgreSQL `historical_candles` table (L2).
- **Rationale**: Active market scanner loops repeatedly query candles for Nifty 500 universe symbols. L1 RAM cache delivers $< 2\text{ms}$ responses for 90%+ of queries, avoiding database connection pool exhaustion.
- **Alternatives Considered**:
  - *Redis L2 Cache*: Deferred to future sprint as PostgreSQL + L1 RAM satisfies latency requirements without introducing external infrastructure complexity.

### Decision 3: Idempotent Batch Persistence Strategy
- **Decision**: Use PostgreSQL `INSERT ... ON CONFLICT (symbol, resolution, timestamp) DO UPDATE` for all candle writes.
- **Rationale**: Prevents primary key / unique constraint violations during concurrent backfill operations or dual-write sync loops.
- **Alternatives Considered**:
  - *Select-before-Insert*: Rejected due to race conditions under multi-worker execution.

### Decision 4: Non-Blocking Dual-Write Synchronization
- **Decision**: Execute secondary dual-writes to legacy cache targets asynchronously via background tasks (`asyncio.create_task`).
- **Rationale**: Guarantees that secondary legacy write latencies or transient failures do not block primary Authoritative Store read/write operations during Phase 1 migration.
- **Alternatives Considered**:
  - *Synchronous Dual-Write*: Rejected due to double transaction latency penalty.

### Decision 5: Dynamic Feature Flag Evaluation
- **Decision**: Protect all authoritative read/write routing behind `settings.authoritative_candle_store_enabled` evaluated dynamically on every request.
- **Rationale**: Enables instant zero-downtime rollback to legacy behavior by toggling environment variable without requiring application restarts.
- **Alternatives Considered**:
  - *Compile-Time / Startup-Only Flag*: Rejected because it requires service restarts during emergency rollbacks.

---

## 3. Technology Stack & Constraints

- **Language**: Python 3.11+
- **Async Runtime**: `asyncio`
- **Database ORM**: SQLAlchemy 2.0 (AsyncSession) with PostgreSQL driver `asyncpg`
- **Configuration**: Pydantic Settings (`backend/app/config/settings.py`)
- **Testing**: `pytest`, `pytest-asyncio`
- **Schema Constraints**: Existing `historical_candles` table schema and index structures are preserved without modification.
