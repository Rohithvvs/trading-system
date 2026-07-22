# Phase 0 Research: Operational Governance & Analytics Layer

**Feature**: `016-operational-governance-analytics`  
**Date**: 2026-07-22  

---

## 1. Production Rule Governance (FEAT-026) Design

### Decision: Baseline Comparison & False-Positive Rate Logic
- **Baseline Source**: `baseline_v1.0.json` (located at repository root). If rule baseline is not present in `baseline_v1.0.json`, default to a conservative baseline of `0.15` (15% false-positive rate).
- **Calculation Formula**:
  $$\text{False Positive Rate (30d)} = \frac{\text{BUY Recommendations in last 30d with Negative Outcome / Loss}}{\text{Total Evaluated BUY Recommendations in last 30d}}$$
- **Sample-Size Protection**:
  - Minimum sample threshold: $N_{\text{min}} = 15$ recommendations in the 30-day window.
  - If total evaluated BUY recommendations $< N_{\text{min}}$, assign status `INSUFFICIENT_DATA` regardless of raw false-positive rate.
- **Status Assignment Rules**:
  - `GREEN` (`healthy`): 30d False-Positive Rate $\le$ Baseline + 0.05.
  - `YELLOW` (`caution`): Baseline + 0.05 < 30d False-Positive Rate $\le$ Baseline + 0.15.
  - `RED` (`degraded`): 30d False-Positive Rate > Baseline + 0.15.
  - `INSUFFICIENT_DATA`: Total sample count $< 15$.
- **CLI & Automated Execution**:
  - Script path: `app.governance.rule_governance` / `app/governance/rule_governance.py`.
  - Exposed via CLI routing in `AGENTS.md`: `experiment.report` or `experiment.governance_report`.
  - Callable on-demand via Python: `python -m app.governance.rule_governance`.

---

## 2. Sector Strength Watch-Only Feature (FEAT-020) Design

### Decision: Pure Function & Shadow Isolation
- **Pure Function Signature**:
  ```python
  def calculate_sector_strength(
      sector_prices: dict[str, list[float]],
      benchmark_prices: list[float],
      scan_time: datetime | None = None
  ) -> SectorStrengthTelemetry:
  ```
- **Relative Performance Calculation**:
  $$\text{Sector Return} = \frac{P_{\text{sector, current}} - P_{\text{sector, t-N}}}{P_{\text{sector, t-N}}}$$
  $$\text{Benchmark Return} = \frac{P_{\text{bm, current}} - P_{\text{bm, t-N}}}{P_{\text{bm, t-N}}}$$
  $$\text{Relative Strength Metric} = \text{Sector Return} - \text{Benchmark Return}$$
- **Labelling Rules**:
  - `Outperforming`: Relative Strength $> +0.01$ (+1%).
  - `Neutral`: $-0.01 \le \text{Relative Strength} \le +0.01$.
  - `Underperforming`: Relative Strength $< -0.01$ (-1%).
  - Low-confidence / missing data: If constituent price count $< 3$ or benchmark data missing, label `Low Confidence`, set metric to `None`, status to `insufficient_data`.
- **Shadow Execution & Savepoint Isolation**:
  - Executed via `ShadowThreadPool.submit_task(execute_shadow_sector_strength, ...)` on every scan.
  - Persisted using existing `_persist_shadow_key_telemetry` function into `AnalysisHistory.shadow_outputs` under key `"sector_strength"`.
  - Uses row-level `FOR UPDATE` lock and server-side JSONB `||` merge in PostgreSQL to ensure atomic, non-destructive write.
  - **Zero Production Score Impact**: Pure watch-only execution. `scoring_matrix_service.py` and `recommendation_service.py` NEVER import or consume sector strength values in live scoring paths.

---

## 3. Analytics Dashboard (FEAT-028) Endpoints Design

### Decision: FastAPI Router & Endpoint Responsibilities
- **Router Location**: `app/routes/analytics.py`, registered in `app/routes/__init__.py` under `/api/v1/analytics` tags `["Analytics"]`.
- **Endpoints & Schemas**:
  1. `GET /api/v1/analytics/engine-health`:
     - Parameters: `days: int = 7` (default 7).
     - Queries `AnalysisHistory` over rolling window.
     - Returns: `total_scans`, `total_recommendations`, `buy_count`, `sell_count`, `hold_count`, `win_rate`, `average_confidence`.
  2. `GET /api/v1/analytics/shadow-status`:
     - Queries recent `AnalysisHistory.shadow_outputs`.
     - Returns telemetry summaries for `news_dedup`, `sentiment_decay`, `market_breadth`, `sector_strength` (last execution timestamp, status, active rules count).
  3. `GET /api/v1/analytics/rule-governance`:
     - Invokes rule governance evaluation logic for promoted rules.
     - Returns: `evaluated_at`, `rules` list (rule_id, 30d_fp_rate, baseline_fp_rate, status, sample_count).
- **Error Handling & Empty Data**:
  - If database contains 0 records in window, returns standard HTTP 200 with zeroed/default schema (e.g. `total_recommendations: 0`, `status: "INSUFFICIENT_DATA"`). Never raises 500 on empty data.

---

## 4. Summary of Technical Rationale

| Requirement | Choice | Rationale | Alternatives Rejected |
|---|---|---|---|
| Rule Governance | 30d rolling FP rate vs baseline in `baseline_v1.0.json` | Reuses existing baseline artifact and avoids hardcoded thresholds. | Complex statistical ML decay model (violates rule #5). |
| Sector Strength | Pure function + `ShadowThreadPool` + JSONB `shadow_outputs` | Follows exact proven pattern of `sentiment_decay` and `market_breadth` (FEAT-016/018). | Inline synchronous calculation during live scoring (violates rule #2). |
| Analytics Router | Dedicated `app/routes/analytics.py` | Isolated, lightweight, auditable endpoints. | Modifying core `analysis.py` or `governance.py` routes (violates rule #1). |
