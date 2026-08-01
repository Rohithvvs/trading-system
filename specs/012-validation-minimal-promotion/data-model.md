# Data Model Design: Validation & Minimal Promotion

This document details the data model and persistence schemas used to track rule lifecycle states, validation reports, and state transition audit events.

---

## 1. Rule Lifecycle State Store (`rule_states.json`)

* **Storage mechanism**: Standard JSON file located at `backend/app/config/rule_states.json`.
* **State schema**:
  ```json
  {
    "news_dedup": "shadow"
  }
  ```
* **Supported lifecycle states**:
  * `shadow`: Deduplication logic runs in the background, logging telemetry to `shadow_outputs` and deduplication audit logs. Sentiment scoring uses the original, undeduplicated article list.
  * `production`: Sentiment scoring uses the deduplicated article list. Shadow deduplication runs are bypassed (as deduplication occurs in-line).
  * `disabled`: Deduplication logic is completely bypassed. Sentiment scoring uses the original, undeduplicated article list.

---

## 2. Challenger Validation Report Schema (`challenger_report_news_dedup.json`)

When generated, the report is compiled into a machine-readable JSON format and saved in a standardized folder (e.g., `governance/reports/`).

### Fields
* `rule_id` (string): Unique identifier for the rule (e.g., `"news_dedup"`).
* `generated_at` (string, ISO-8601): Timestamp when the report was run.
* `window_start` (string, ISO-8601): Start of the 14-day analysis window.
* `window_end` (string, ISO-8601): End of the 14-day analysis window.
* `total_recommendations_analyzed` (integer): Count of `AnalysisHistory` records matching the window.
* `total_articles_processed` (integer): Total articles loaded before deduplication.
* `total_articles_deduplicated` (integer): Total articles removed by shadow deduplication.
* `deduplication_rate` (float, 0.0 - 1.0): `total_articles_deduplicated / total_articles_processed`.
* `average_sentiment_score` (float, -1.0 - 1.0): Mean of the sentiment scores calculated.
* `false_positive_count` (integer): Count of signals where no corresponding trade order was executed within 24 hours.
* `false_positive_rate` (float, 0.0 - 1.0): Ratio of false positives to total signals.
* `baseline_false_positive_rate` (float): Fixed reference value from `baseline_v1.0.json`.
* `baseline_sentiment_score` (float): Fixed reference value from `baseline_v1.0.json`.
* `status` (string): `"PASS"` or `"FAIL"`. Passes if deduplication rate is between 5% and 40%, and false-positive rate is stable or lower than the baseline.
* `data_incomplete` (boolean): `true` when fewer than 14 days of shadow data are available.
* `incomplete_data_warning` (string | null): Human-readable warning when data is incomplete; `null` when the window is fully covered.
* `available_data_span_days` (float | null): Observed span (days) from earliest shadow sample to report generation time; `null` when no samples exist.

---

## 3. State Transition Audit Event

State transitions are saved using the existing `AuditTrailManager` (persisted to `logs/audit.jsonl` with hash chaining integrity).

### Event Fields
* `uuid` (string, UUIDv4): Unique identifier of the audit log event.
* `actor` (string): Actor performing the action (defaults to `"admin"`).
* `action` (string): `"rule.promote"` or `"rule.kill"`.
* `target_type` (string): `"rule"`.
* `target_id` (string): Name of the rule (e.g., `"news_dedup"`).
* `outcome` (string): `"success"` or `"failure"`.
* `timestamp` (string, ISO-8601): Event time.
* `details` (JSON object):
  * For `rule.promote`: `{"checklist_approved": true, "reason": "..."}`
  * For `rule.kill`: `{"reason": "..."}`
