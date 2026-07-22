# Implementation Plan: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Branch**: `014-shadow-sentiment-breadth` | **Date**: 2026-07-22 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/014-shadow-sentiment-breadth/spec.md)  
**Input**: Feature specification from `specs/014-shadow-sentiment-breadth/spec.md`

---

## 1. Summary

This technical plan details the implementation of two new candidate features running concurrently in Shadow Mode during live stock scans: **Sentiment Time-Decay (FEAT-018)** and **Market Breadth (FEAT-016)**. 

Both features are implemented as pure, deterministic, easily auditable functions. They are executed asynchronously via the existing `ShadowThreadPool`, saving telemetry independently to `analysis_history.shadow_outputs` without mutating live production scoring or interfering with each other.

---

## 2. Technical Context

- **Language/Version**: Python 3.11+
- **Framework & DB**: FastAPI, SQLAlchemy (PostgreSQL with JSONB), `asyncio`
- **Concurrency Infrastructure**: `ShadowThreadPool` (dedicated thread pool, `max_workers=4`)
- **Storage**: `analysis_history.shadow_outputs` (PostgreSQL `JSONB` column with GIN index)
- **Testing**: `pytest`, `pytest-asyncio`
- **Target Platform**: Linux / Windows server environment
- **Performance Goals**: Asynchronous background shadow execution adds 0 ms blocking latency to live scans.
- **Constraints**:
  1. Never rewrite core architecture; add isolated logic only.
  2. Database telemetry updates must use isolated transactions (`db.session.begin_nested()` / SAVEPOINT) or dedicated sessions.
  3. No machine learning, embeddings, or new external data APIs.
  4. 100% pure, deterministic calculations.
  5. Live production recommendation path remains completely untouched (zero points contributed).

---

## 3. Constitution Check

| Rule / Principle | Compliance Status | Implementation Strategy |
|---|---|---|
| **I. Library-First & Pure Functions** | **PASSED** | Core logic implemented as pure functions with zero side effects (`calculate_sentiment_time_decay`, `calculate_market_breadth`). |
| **II. Auditability & Observability** | **PASSED** | Full diagnostic metadata saved into `shadow_outputs["sentiment_decay"]` and `shadow_outputs["market_breadth"]`. |
| **III. Test-First (TDD)** | **PASSED** | Unit tests for pure functions and integration tests for shadow execution written prior to production wiring. |
| **IV. Fault & Data Isolation** | **PASSED** | Shadow functions wrapped in isolated `try...except` blocks; DB updates use independent sessions/SAVEPOINTs; live scoring math unchanged. |

---

## 4. Project Structure

### Documentation & Design Artifacts

```text
specs/014-shadow-sentiment-breadth/
├── spec.md              # Feature specification
├── plan.md              # Technical implementation plan (this file)
├── research.md          # Phase 0 research decisions
├── data-model.md        # Data models and schemas
├── quickstart.md        # Validation & quickstart guide
└── contracts/
    └── shadow_telemetry_schema.json  # Schema for shadow_outputs
```

### Source Code Layout

```text
backend/
├── app/
│   ├── services/
│   │   ├── sentiment_decay.py      # [NEW] Pure function for FEAT-018 Sentiment Time-Decay
│   │   ├── market_breadth.py       # [NEW] Pure function for FEAT-016 Market Breadth
│   │   ├── analytics_service.py    # [MODIFIED] Shadow+tags correlation query helper
│   │   └── shadow_executor.py      # [MODIFIED] Shadow workers + atomic shadow_outputs merge
│   ├── schemas/
│   │   └── shadow_telemetry.py     # [NEW] Pydantic telemetry schemas
│   └── agents/
│       ├── news_analysis_agent.py  # [MODIFIED] Shadow news_dedup only (not sentiment decay)
│       └── orchestrator_agent.py   # [MODIFIED] Post-persist FEAT-018 + FEAT-016 submission
└── tests/
    ├── unit/
    │   ├── test_sentiment_decay.py # [NEW] Unit tests for Sentiment Time-Decay
    │   ├── test_market_breadth.py  # [NEW] Unit tests for Market Breadth
    │   └── test_shadow_candidate_*.py
    ├── integration/
    │   └── test_parallel_shadow_features.py # [NEW] Concurrent shadow execution & fault isolation tests
    └── regression/
        └── test_shadow_sentiment_breadth_regression.py
```

---

## 5. Detailed Technical Design & Decisions

### 5.1 Sentiment Time-Decay (FEAT-018)

#### Pure Function Signature
```python
def calculate_sentiment_time_decay(
    articles: list[ArticleSentimentItem],
    scan_time: datetime | None = None,
    half_life_hours: float = 24.0,
    max_age_hours: float = 72.0,
) -> SentimentDecayResult:
```

#### Age & Decay Math
1. **Timezone Handling**: Timestamps normalized to UTC via `_as_utc(published_at)`.
2. **Age Calculation**: $t = (\text{scan\_time} - \text{published\_at}).\text{total\_seconds}() / 3600.0$.
   - If $t < 0.0$ (future timestamp or clock skew), set $t = 0.0$.
   - If `published_at` is missing or `None`, set $t = \text{max\_age\_hours} + 1.0$ (hard zero).
3. **Decay Formula & Hard Cutoff**:
   $$w(t) = \begin{cases} 2^{-(t / 24.0)} & \text{if } 0 \le t \le 72.0 \\ 0.0 & \text{if } t > 72.0 \end{cases}$$
4. **Article Decayed Score**: $s_{\text{decayed}, i} = s_{\text{raw}, i} \times w(t_i)$.
5. **Aggregate Score**: Weighted average $\bar{S}_{\text{decayed}} = \frac{\sum (s_{\text{raw}, i} \cdot w(t_i))}{\sum w(t_i)}$. If $\sum w(t_i) == 0$, returns $0.0$.

#### Output Telemetry (`shadow_outputs["sentiment_decay"]`)
Contains aggregate raw score, aggregate decayed score, total article count, decayed article count, zeroed article count, and article breakdown details.

#### Pipeline Insertion Point
Submitted **after** `OrchestratorAgent._persist_analysis` (so `AnalysisHistory` exists), independent of the `news_dedup` rule lifecycle and independent of the experimental shadow ruleset executor:

```python
# OrchestratorAgent._submit_shadow_candidate_features(...)
ShadowThreadPool.submit_task(
    execute_shadow_sentiment_decay,
    symbol,
    articles or [],
    None,       # scan_time
    stock_id,
)
```

Rationale (audit H1/H3): early news-agent submission raced history creation and was incorrectly gated on `news_dedup == "shadow"`.

---

### 5.2 Market Breadth (FEAT-016)

#### Pure Function Signature
```python
def calculate_market_breadth(
    universe_prices: list[StockBreadthItem],
    min_universe_size: int = 10,
) -> MarketBreadthResult:
```

#### Breadth & Regime Mapping
1. **Breadth Percentage**:
   $$\text{breadth\_pct} = \frac{\text{count}(\text{current\_price} > \text{sma\_200})}{\text{count}(\text{valid stocks with 200MA})} \times 100.0$$
2. **Regime Mapping Table**:
   | Breadth % Range | Regime Label | Soft Score Contribution |
   |---|---|---|
   | $\ge 70.0\%$ | `strong` | $+15.0$ |
   | $55.0\% \le \text{pct} < 70.0\%$ | `favorable` | $+7.5$ |
   | $45.0\% \le \text{pct} < 55.0\%$ | `neutral` | $0.0$ |
   | $30.0\% \le \text{pct} < 45.0\%$ | `weak` | $-7.5$ |
   | $< 30.0\%$ | `very_weak` | $-15.0$ |

3. **Guard Rails**: If valid stock count $< \text{min\_universe\_size}$ (10), set `is_valid: false`, `regime_label: "unreliable"`, and `soft_score_contribution: 0.0`.

#### Output Telemetry (`shadow_outputs["market_breadth"]`)
Contains universe size, valid stock count, above 200MA count, breadth percentage, regime label, soft score contribution, and validity flag.

#### Pipeline Insertion Point
Submitted from the same post-persist helper as FEAT-018, with **bulk technical universe** rows (close + `sma_200` for all symbols in the scan batch):

```python
breadth_items = self._universe_breadth_items_from_bulk(bulk_technical_results)
ShadowThreadPool.submit_task(
    execute_shadow_market_breadth,
    symbol,
    breadth_items,
    None,       # scan_time
    stock_id,
)
```

Note: single-symbol analysis may yield `regime_label=unreliable` when valid count &lt; 10 (FR-006 guard rail). Full bulk scans supply the monitored universe.

---

### 5.3 Parallel Shadow Wiring & Telemetry Persistence

1. **Concurrent Submission**: Both shadow tasks are submitted independently to `ShadowThreadPool` after production persist (non-blocking; SC-001).
2. **Telemetry Atomic Update**:
   - Workers merge into `shadow_outputs` under distinct keys (`sentiment_decay`, `market_breadth`).
   - PostgreSQL: JSONB `||` merge; SQLite/tests: process lock + `FOR UPDATE` + dict merge (FR-008 / SC-002).
   - Sibling keys such as `news_dedup` are preserved.
3. **Fault Isolation**:
   - Every shadow worker wraps calculation and persistence in `try...except Exception:`.
   - Candidate submits are isolated from each other and from the experimental ruleset executor.
   - Production recommendation pipelines continue without interruption (FR-009 / FR-010).

---

### 5.4 Observability & Future Analysis (Sprint 8 A/B Ablation)

- `analysis_history` records contain `situation_tags` (e.g., `["GOOD_NEWS_CATALYST", "MARKET_REGIME"]`) and `shadow_outputs`.
- Sprint 8 analytics queries can filter history by situation tags and compare live scores against `shadow_outputs["sentiment_decay"]` and `shadow_outputs["market_breadth"]` to evaluate signal efficacy prior to production promotion.

---

### 5.5 Testing Strategy

1. **Unit Tests** (`test_sentiment_decay.py` & `test_market_breadth.py`):
   - Test exponential decay calculation at 0h, 24h, 48h, 72h, and 96h boundaries.
   - Test missing timestamps, empty article lists, and invalid input strings.
   - Test market breadth calculations for all 5 regime tiers.
   - Test guard rail behavior for small universe sizes ($<10$ stocks).
2. **Integration Tests** (`test_parallel_shadow_features.py`):
   - Verify concurrent submission of both shadow rules during a scan.
   - Verify that `shadow_outputs` contains `sentiment_decay`, `market_breadth`, and `news_dedup` simultaneously.
   - Crash isolation test: mock `calculate_market_breadth` to raise an exception, verify `sentiment_decay` finishes and writes telemetry, and verify production recommendation path completes cleanly.
   - Score identity test: confirm live production recommendation points remain 100% identical before and after enabling candidate shadow features.
