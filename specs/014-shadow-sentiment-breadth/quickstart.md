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
  - 72-hour old article: $multiplier = 0.0$, $decayed = 0.0$.
  - $>72$-hour old article or missing timestamp: $multiplier = 0.0$, $decayed = 0.0$.
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
