# Phase 0 Research: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Feature**: `014-shadow-sentiment-breadth`  
**Date**: 2026-07-22  
**Status**: Completed  

---

## 1. Technical Decisions & Research Findings

### Decision 1: Sentiment Time-Decay Formula & Cutoff (FEAT-018)
- **Decision**: Use half-life exponential decay formula $w(t) = 2^{-(t / 24.0)}$ for age $t \in [0, 72.0]$ hours, with a hard zero cutoff $w(t) = 0.0$ for $t > 72.0$ hours.
- **Rationale**: 
  - News relevance decays naturally with time. A 24-hour half-life means 1-day-old news carries 50% weight, 2-day-old news carries 25% weight, and 3-day-old news carries 12.5% weight before being hard-zeroed at 72 hours.
  - Provides a predictable, pure deterministic function without heavy external models.
- **Alternatives Considered**: 
  - *Linear Decay*: Simple, but fails to model the rapid drop-off in financial news sentiment impact.
  - *Step Functions*: Creates artificial score cliffs at boundary thresholds.

---

### Decision 2: Market Breadth Regime Thresholds & Soft Contribution (FEAT-016)
- **Decision**: Calculate percentage of universe stocks trading above their 200-day moving average. Map percentage to 5 discrete regime labels and soft score contributions:
  - $\ge 70.0\%$: `strong` $\to$ $+15.0$ soft score
  - $55.0\% \le \text{pct} < 70.0\%$: `favorable` $\to$ $+7.5$ soft score
  - $45.0\% \le \text{pct} < 55.0\%$: `neutral` $\to$ $0.0$ soft score
  - $30.0\% \le \text{pct} < 45.0\%$: `weak` $\to$ $-7.5$ soft score
  - $< 30.0\%$: `very_weak` $\to$ $-15.0$ soft score
- **Rationale**: 
  - Standard technical analysis convention uses 200-day moving average breadth to judge market health.
  - Soft score contributions provide a symmetrical $[-15.0, +15.0]$ scale suitable for future combination with stock-level scores without dominating them.
- **Guard Rails**: If total valid stocks with 200-day MAs $< 10$, mark `is_valid: false`, `regime_label: "unreliable"`, and soft score contribution `0.0`.

---

### Decision 3: Shadow Output Schema & Key Isolation
- **Decision**: Store independent telemetry entries in `analysis_history.shadow_outputs` under distinct keys: `shadow_outputs["sentiment_decay"]` and `shadow_outputs["market_breadth"]`.
- **Rationale**: 
  - The existing JSONB column supports nested key-value storage. Using dedicated top-level keys prevents key collisions between candidate features and preserves existing keys (`news_dedup`, `original_news_count`, `kept_news_count`).
- **Alternatives Considered**: 
  - *Single combined key*: High risk of tightly coupling two independent candidate features and causing overwrites if one feature fails.

---

### Decision 4: Concurrency & Fault Isolation Architecture
- **Decision**: Submit both shadow calculations via `ShadowThreadPool.submit_task()` **after** production `AnalysisHistory` persist (orchestrator). Each worker opens `SessionLocal()` and merges into `shadow_outputs` under a distinct key. PostgreSQL uses atomic JSONB `||` merge; SQLite uses a process lock + row re-read.
- **Rationale**: 
  - Dedicated thread pool prevents shadow execution from consuming FastAPI request loops (SC-001).
  - Independent `try...except` blocks ensure a crash in `market_breadth` does not impact `sentiment_decay`, and neither impacts production scoring (FR-009/010).
  - Post-persist submission and key merge prevent lost telemetry under concurrent writers (FR-008 / SC-002).
