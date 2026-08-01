# Quickstart Validation Guide: Validation, Interaction Analysis, Rebalancing & Promotion

**Feature**: `015-shadow-promotion-rebalance`  
**Date**: 2026-07-22

---

## Prerequisites

- Active virtual environment with project dependencies (`pytest`, `sqlalchemy`, `pydantic`).
- Sprint 7 shadow telemetry stored in database or test sqlite fixture.

---

## Scenario 1: Generate Attribution & Interaction Report

Run the unit and integration tests for attribution analysis and feature correlation:

```bash
pytest backend/tests/unit/test_attribution_validation.py -v
```

**Expected Outcome**:
- 4-way ablation metrics calculated for Baseline, Decay-Only, Breadth-Only, and Combined.
- Pearson correlation coefficient computed.
- If $r < 0.70$, output `redundancy_classification = "COMPLEMENTARY"` and `recommendation = "GO"`.

---

## Scenario 2: Validate Matrix 100-Point Budget Invariant

Run matrix rebalancing validation tests:

```bash
pytest backend/tests/unit/test_scoring_matrix_rebalance.py -v
```

**Expected Outcome**:
- Rebalanced matrix (Tech 35, Sent 25, Fund 15, Vol 15, Breadth 10) passes `sum == 100.0` validation.
- Any candidate matrix with sum $\ne 100.0$ raises explicit `ValueError`.

---

## Scenario 3: Verify Sequential Promotion & Kill-Switch Fallback

Run end-to-end promotion and kill-switch integration tests:

```bash
pytest backend/tests/integration/test_sequential_promotion.py -v
```

**Expected Outcome**:
- **Stage 1**: Promote `sentiment_decay` via `RuleManager` $\to$ live sentiment calculation uses time-decay math while `market_breadth` remains in shadow mode.
- **Stage 2**: Promote `market_breadth` via `RuleManager` $\to$ live composite score uses rebalanced 100-point matrix.
- **Kill-Switch**: Disable `market_breadth` or `sentiment_decay` $\to$ system immediately reverts to baseline scoring in $<1\text{ms}$ with zero downtime.

---

## Scenario 4: Run Full Sprint 8 Test Suite

Execute all Sprint 8 validation, rebalancing, and promotion tests together:

```bash
pytest backend/tests/unit/test_attribution_validation.py backend/tests/unit/test_scoring_matrix_rebalance.py backend/tests/integration/test_sequential_promotion.py -v
```

**Expected Outcome**:
All tests pass cleanly.
