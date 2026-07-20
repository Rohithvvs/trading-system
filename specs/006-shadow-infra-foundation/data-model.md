# Data Model: Shadow Infrastructure Foundation

**Feature Branch**: `006-shadow-infra-foundation` | **Date**: 2026-07-20  
**Feature**: [spec.md](./spec.md)

---

## 1. Pydantic DTO Schemas (Non-persistent Contracts)

These schemas reside under `backend/app/schemas/analysis.py` (or a dedicated shadow module) to model the data snapshot.

### ShadowExecutionContext
Represents the input snapshot passed to the shadow ruleset.

| Field Name | Type | Description |
|---|---|---|
| `symbol` | `str` | The market ticker symbol (e.g., `RELIANCE-EQ`). |
| `candles` | `list[OHLCVPoint]` | Deep copied list of historical candles for the symbol. |
| `technical_results` | `list[TechnicalAnalysisResult]` | Deep copied technical indicator calculations and signals. |
| `sentiment_score` | `float` | News/sentiment score from sentiment analysis. |
| `fundamental_result` | `FundamentalAnalysisResult | None` | Fundamental data attributes if available. |
| `backtests` | `list[BacktestResult]` | Simulates single-asset metrics for the symbol. |
| `production_recommendation` | `FinalRecommendation` | The production advisory engine's recommendation. |
| `production_challenger_recommendation` | `FinalRecommendation` | The production downgrade-adjusted recommendation. |
| `scan_date` | `datetime` | Timestamp of the snapshot scan. |

### ShadowExecutionResult
Represents the result returned by the shadow executor.

| Field Name | Type | Description |
|---|---|---|
| `ruleset_name` | `str` | Name of the experimental ruleset evaluated (e.g., `experimental_v1`). |
| `score` | `float` | The composite score computed by the experimental logic. |
| `action` | `str` | The calculated action (`BUY`, `WATCH`, `REJECT`). |
| `reasoning` | `list[str]` | Bullets justifying the experimental decision. |
| `executed_at` | `datetime` | Timestamp when the shadow ruleset was executed. |

### ShadowComparisonLog
Models the audit and discrepancy analysis between production and shadow recommendations.

| Field Name | Type | Description |
|---|---|---|
| `symbol` | `str` | Mapped symbol ticker. |
| `scan_date` | `datetime` | Date of the snapshot evaluation. |
| `ruleset_name` | `str` | Name of the experimental ruleset evaluated. |
| `production_action` | `str` | Production action (e.g. `BUY`). |
| `production_score` | `float` | Production composite score. |
| `shadow_action` | `str` | Experimental shadow action. |
| `shadow_score` | `float` | Experimental shadow composite score. |
| `score_delta` | `float` | Difference between production and shadow score. |
| `is_mismatch` | `bool` | `True` if action labels do not match. |

---

## 2. Abstract Interface Contracts

These interfaces reside under `backend/app/services/`.

### IShadowExecutor
```python
class IShadowExecutor(abc.ABC):
    @abc.abstractmethod
    async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
        """Runs the experimental ruleset logic against the provided snapshot context."""
        pass
```

### IShadowStore
```python
class IShadowStore(abc.ABC):
    @abc.abstractmethod
    async def save_comparison(self, comparison: ShadowComparisonLog) -> None:
        """Persists the comparative log using an isolated database session context."""
        pass
```
