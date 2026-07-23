# Data Model & Schema Definitions: Operational Governance & Analytics Layer

**Feature**: `016-operational-governance-analytics`  
**Date**: 2026-07-22  

---

## 1. Governance Entities

### `RuleGovernanceRecord`
Represents the 30-day performance evaluation snapshot of a promoted production rule.

| Field Name | Type | Description | Constraints / Validation |
|---|---|---|---|
| `rule_id` | `str` | Unique identifier of promoted rule (e.g. `news_dedup`, `sentiment_decay`, `market_breadth`) | Required |
| `evaluated_at` | `datetime` | UTC timestamp of evaluation run | Isoformat UTC |
| `false_positive_rate_30d` | `float \| None` | Rolling 30-day false-positive rate | $0.0 \le \text{rate} \le 1.0$, `None` if sample count < 15 |
| `baseline_false_positive_rate` | `float` | Original baseline false-positive rate from `baseline_v1.0.json` | Default `0.15` if baseline missing |
| `sample_count_30d` | `int` | Number of BUY recommendations evaluated in 30d window | $\ge 0$ |
| `health_status` | `str` | Assigned health status code | Allowed values: `GREEN`, `YELLOW`, `RED`, `INSUFFICIENT_DATA` |
| `health_label` | `str` | Spec FR-003 vocabulary | `healthy`, `caution`, `degraded`, `insufficient data` (mapped from `health_status`) |
| `status_reason` | `str` | Explanatory text for assigned health status | Non-empty string |

---

## 2. Sector Strength Telemetry Schema (`shadow_outputs["sector_strength"]`)

Represents passive watch-only evaluation of sector performance relative to broader market benchmarks.

```json
{
  "sector_strength": {
    "executed_at": "2026-07-22T15:00:00Z",
    "status": "success",
    "benchmark_symbol": "NIFTY50",
    "benchmark_return_pct": 0.45,
    "sectors": [
      {
        "sector": "NIFTY_IT",
        "sector_return_pct": 1.20,
        "relative_strength": 0.75,
        "label": "Outperforming",
        "constituent_count": 10,
        "confidence": "high"
      },
      {
        "sector": "NIFTY_BANK",
        "sector_return_pct": 0.10,
        "relative_strength": -0.35,
        "label": "Underperforming",
        "constituent_count": 12,
        "confidence": "high"
      }
    ]
  }
}
```

---

## 3. Analytics API Schemas

### `EngineHealthResponse` (`GET /api/v1/analytics/engine-health`)
```json
{
  "window_days": 7,
  "total_scans": 140,
  "total_recommendations": 420,
  "signal_distribution": {
    "BUY": 120,
    "SELL": 80,
    "HOLD": 220
  },
  "positive_outcome_rate": 0.68,
  "average_confidence_score": 78.5,
  "generated_at": "2026-07-22T15:45:00Z"
}
```

### `ShadowStatusResponse` (`GET /api/v1/analytics/shadow-status`)
```json
{
  "active_shadow_rules": ["news_dedup", "sentiment_decay", "market_breadth", "sector_strength"],
  "rules_telemetry": {
    "news_dedup": { "status": "active", "total_executions_7d": 140, "last_executed_at": "2026-07-22T15:30:00Z" },
    "sentiment_decay": { "status": "active", "total_executions_7d": 140, "last_executed_at": "2026-07-22T15:30:00Z" },
    "market_breadth": { "status": "active", "total_executions_7d": 140, "last_executed_at": "2026-07-22T15:30:00Z" },
    "sector_strength": { "status": "active", "total_executions_7d": 140, "last_executed_at": "2026-07-22T15:30:00Z" }
  },
  "generated_at": "2026-07-22T15:45:00Z"
}
```

### `RuleGovernanceResponse` (`GET /api/v1/analytics/rule-governance`)
```json
{
  "evaluated_at": "2026-07-22T15:45:00Z",
  "promoted_rules_count": 3,
  "rules": [
    {
      "rule_id": "news_dedup",
      "health_status": "GREEN",
      "false_positive_rate_30d": 0.12,
      "baseline_false_positive_rate": 0.15,
      "sample_count_30d": 85,
      "status_reason": "30-day false-positive rate (12.0%) is within baseline tolerance (15.0% + 5.0%)"
    },
    {
      "rule_id": "sentiment_decay",
      "health_status": "GREEN",
      "false_positive_rate_30d": 0.14,
      "baseline_false_positive_rate": 0.15,
      "sample_count_30d": 62,
      "status_reason": "30-day false-positive rate (14.0%) is within baseline tolerance (15.0% + 5.0%)"
    },
    {
      "rule_id": "market_breadth",
      "health_status": "GREEN",
      "false_positive_rate_30d": 0.11,
      "baseline_false_positive_rate": 0.15,
      "sample_count_30d": 45,
      "status_reason": "30-day false-positive rate (11.0%) is within baseline tolerance (15.0% + 5.0%)"
    }
  ]
}
```
