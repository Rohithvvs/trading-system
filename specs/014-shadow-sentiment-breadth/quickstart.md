# Quickstart & Validation Guide: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Feature**: `014-shadow-sentiment-breadth`  
**Date**: 2026-07-22  

---

## 1. Unit Verification Scenarios

Run unit tests to verify pure calculations for Sentiment Time-Decay (FEAT-018) and Market Breadth (FEAT-016):

```bash
pytest backend/tests/unit/test_sentiment_decay.py -v
pytest backend/tests/unit/test_market_breadth.py -v
```

### Expected Outcomes
- **Sentiment Time-Decay**:
  - 0-hour old article: $multiplier = 1.0$, $decayed = raw$.
  - 24-hour old article: $multiplier = 0.5$, $decayed = 0.5 \times raw$.
  - 48-hour old article: $multiplier = 0.25$, $decayed = 0.25 \times raw$.
  - Exactly 72-hour old article: still within cutoff ($t \le 72$), $multiplier = 2^{-3} = 0.125$.
  - $>72$-hour old article or missing timestamp: $multiplier = 0.0$, $decayed = 0.0$ (hard zero only when age is **strictly greater than** 72h).
- **Market Breadth**:
  - $75\%$ above 200MA $\to$ regime `strong`, contribution $+15.0$, `is_valid: true`.
  - $60\%$ above 200MA $\to$ regime `favorable`, contribution $+7.5$, `is_valid: true`.
  - $50\%$ above 200MA $\to$ regime `neutral`, contribution $0.0$, `is_valid: true`.
  - $40\%$ above 200MA $\to$ regime `weak`, contribution $-7.5$, `is_valid: true`.
  - $20\%$ above 200MA $\to$ regime `very_weak`, contribution $-15.0$, `is_valid: true`.
  - $<10$ valid stocks $\to$ regime `unreliable`, contribution $0.0$, `is_valid: false`.

---

## 2. Parallel Shadow Integration & Isolation Verification

Run integration tests for concurrent execution and fault isolation:

```bash
pytest backend/tests/integration/test_parallel_shadow_features.py -v
```

### Expected Outcomes
- **Parallel Output Verification**:
  - Both `"sentiment_decay"` and `"market_breadth"` keys are populated in `analysis_history.shadow_outputs`.
  - Existing `"news_dedup"` and top-level metadata remain unmodified.
- **Fault Isolation Verification**:
  - Injecting a simulated exception in `market_breadth` leaves `"sentiment_decay"` fully intact in `shadow_outputs`.
  - Live production recommendation score and output match pre-Sprint-7 baseline 100%.

---

## 3. Regression & Related Suites

```bash
pytest backend/tests/unit/test_sentiment_decay.py \
  backend/tests/unit/test_market_breadth.py \
  backend/tests/unit/test_shadow_candidate_telemetry_schemas.py \
  backend/tests/unit/test_shadow_candidate_analytics.py \
  backend/tests/unit/test_news_deduplication.py \
  backend/tests/integration/test_parallel_shadow_features.py \
  backend/tests/regression/test_shadow_sentiment_breadth_regression.py \
  backend/tests/integration/test_news_dedup_shadow.py \
  backend/tests/integration/test_shadow_integration.py \
  backend/tests/integration/test_settings.py \
  backend/tests/regression/test_shadow_infra_foundation_regression.py -q
```

Expected: all green (feature + shadow infra + news-dedup + settings isolation).

---

## 4. Operational Notes (post-merge)

| Topic | Behavior |
|-------|----------|
| **Shadow gate** | Candidates run only when `settings.is_shadow_hook_enabled()` is true (`shadow_mode_enabled` and stage ≠ `OFF`). |
| **SC-001 latency** | Submit is fire-and-forget on `ShadowThreadPool` **after** production persist — no await on the recommendation path. |
| **SC-002 completeness** | Watch logs: `ShadowThreadPool queue full` (task drop), `telemetry not written after N attempts`, `telemetry saved`. |
| **Universe size** | Breadth uses bulk technical results. Single-symbol runs may correctly return `unreliable` when valid stocks &lt; 10 (FR-006). |
| **A/B analysis** | Use `AnalyticsService.query_shadow_candidates_by_situation_tags(...)` to join tags with both shadow keys. |
| **Production scoring** | Soft breadth contribution and decayed sentiment never enter recommendation scoring. |

---

## 5. Wiring Summary (as implemented)

| Feature | Submit location | Inputs |
|---------|-----------------|--------|
| FEAT-018 Sentiment decay | `OrchestratorAgent._submit_shadow_candidate_features` post-persist | `articles` (may be empty), `stock_id` |
| FEAT-016 Market breadth | Same helper, isolated try/except | Full bulk-universe `{symbol, current_price, sma_200}` |
| News dedup (prior) | `NewsAnalysisAgent._submit_shadow_dedup` when rule state is `shadow` | articles only |
