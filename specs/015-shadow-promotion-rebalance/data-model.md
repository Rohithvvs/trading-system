# Data Model: Validation, Interaction Analysis, Rebalancing & Promotion

**Feature**: `015-shadow-promotion-rebalance`  
**Date**: 2026-07-22

---

## 1. Telemetry & Attribution Entities

### `AttributionReport`
Pydantic model representing the result of 4-way A/B ablation analysis.

```python
class AblationMetrics(BaseModel):
    sample_size: int
    false_positive_rate: float
    win_rate: float
    precision: float
    signal_accuracy: float
    alpha_attribution_pct: float

class AttributionReport(BaseModel):
    evaluation_window_days: int
    total_samples: int
    baseline_metrics: AblationMetrics
    decay_only_metrics: AblationMetrics
    breadth_only_metrics: AblationMetrics
    combined_metrics: AblationMetrics
    situation_tag_breakdown: dict[str, dict[str, float]]
    evaluated_at: datetime
    status: Literal["VALID", "INSUFFICIENT_DATA"]
```

---

## 2. Interaction & Governance Entities

### `InteractionAnalysis`
Pydantic model representing feature correlation and promotion recommendations.

```python
class InteractionAnalysis(BaseModel):
    decay_feature_key: str = "sentiment_decay"
    breadth_feature_key: str = "market_breadth"
    pearson_correlation: float
    spearman_correlation: float
    redundancy_classification: Literal["COMPLEMENTARY", "MODERATE_OVERLAP", "REDUNDANT"]
    decay_promotion_recommendation: Literal["GO", "NO_GO"]
    breadth_promotion_recommendation: Literal["GO", "NO_GO"]
    rationale: str
    evaluated_at: datetime
```

### `ScoringMatrixConfig`
Pydantic model enforcing 100-point matrix sum invariant.

```python
class ScoringMatrixConfig(BaseModel):
    version: str
    technical_weight: float
    sentiment_weight: float
    fundamental_weight: float
    volume_weight: float
    market_breadth_weight: float = 0.0

    @model_validator(mode="after")
    def validate_sum_100(self) -> "ScoringMatrixConfig":
        total = (
            self.technical_weight
            + self.sentiment_weight
            + self.fundamental_weight
            + self.volume_weight
            + self.market_breadth_weight
        )
        if abs(total - 100.0) > 1e-5:
            raise ValueError(f"Scoring matrix sum must equal exactly 100.0, got {total}")
        return self
```

### `PromotionStateRecord`
Pydantic model representing governance promotion status.

```python
class PromotionStateRecord(BaseModel):
    rule_id: str
    stage: Literal["STAGE_1_DECAY", "STAGE_2_BREADTH"]
    previous_state: RuleState
    new_state: RuleState
    promoted_at: datetime
    promoted_by: str
    attribution_report_approved: bool
    kill_switch_active: bool
```
