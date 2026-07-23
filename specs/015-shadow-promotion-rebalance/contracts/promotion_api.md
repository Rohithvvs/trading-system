# Contracts: Governance Promotion API

**Feature**: `015-shadow-promotion-rebalance`  
**Date**: 2026-07-22

---

## 1. Governance REST Endpoints

### `GET /api/v1/governance/attribution-report`
Generates and returns the 4-way A/B ablation attribution report for shadow mode candidate features.

- **Query Parameters**:
  - `days` (int, default=30): Lookback window in days.
- **Response**: `200 OK`
  ```json
  {
    "status": "VALID",
    "total_samples": 45,
    "baseline_metrics": { "false_positive_rate": 0.18, "win_rate": 0.62, "precision": 0.74 },
    "decay_only_metrics": { "false_positive_rate": 0.14, "win_rate": 0.65, "precision": 0.78 },
    "breadth_only_metrics": { "false_positive_rate": 0.15, "win_rate": 0.64, "precision": 0.76 },
    "combined_metrics": { "false_positive_rate": 0.11, "win_rate": 0.68, "precision": 0.81 }
  }
  ```

### `GET /api/v1/governance/interaction-check`
Calculates feature correlation between `sentiment_decay` and `market_breadth` and provides promotion recommendations.

- **Response**: `200 OK`
  ```json
  {
    "pearson_correlation": 0.28,
    "redundancy_classification": "COMPLEMENTARY",
    "decay_promotion_recommendation": "GO",
    "breadth_promotion_recommendation": "GO",
    "rationale": "Low correlation (r=0.28 < 0.70). Both features provide independent alpha."
  }
  ```

### `POST /api/v1/governance/rules/{rule_id}/promote`
Promotes a shadow feature to production stage (requires admin role & approved report).

- **URL Path**: `rule_id` (`sentiment_decay` or `market_breadth`)
- **Body**:
  ```json
  {
    "actor": "admin",
    "reason": "Approved Sprint 8 attribution report",
    "checklist_approved": true
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "rule_id": "sentiment_decay",
    "previous_state": "shadow",
    "new_state": "production",
    "message": "Rule 'sentiment_decay' promoted to production."
  }
  ```

### `POST /api/v1/governance/rules/{rule_id}/kill`
Triggers immediate kill-switch for a feature, reverting to baseline scoring logic.

- **URL Path**: `rule_id` (`sentiment_decay` or `market_breadth`)
- **Body**:
  ```json
  {
    "actor": "admin",
    "reason": "Emergency performance degradation"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "rule_id": "market_breadth",
    "previous_state": "production",
    "new_state": "disabled",
    "message": "Rule 'market_breadth' killed. Reverted to baseline math."
  }
  ```
