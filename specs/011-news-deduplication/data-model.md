# Data Model Specification: News Deduplication & Shadow Telemetry

This document outlines the schema additions, model mappings, and telemetry JSON structures for the News Deduplication feature.

## 1. Database Model: `ArticleDedupLog` (`news_deduplication_audit`)

This table registers every deduplicated (removed) news article identified by the shadow deduplication runner.
Table name follows FR-009 / clarification: `news_deduplication_audit`.

### Schema Table: `news_deduplication_audit`

| Column Name | SQLAlchemy Type | DB Type | Constraints | Description |
|---|---|---|---|---|
| `id` | `Integer` | `SERIAL` | Primary Key | Auto-incrementing identifier. |
| `symbol` | `String(25)` | `VARCHAR(25)` | Nullable=False, Index=True | The stock symbol associated with the news scan. |
| `kept_id` | `String(500)` | `VARCHAR(500)` | Nullable=False | Unique identifier (e.g. URL or title-timestamp hash) of the kept article. |
| `deduplicated_id` | `String(500)` | `VARCHAR(500)` | Nullable=False | Unique identifier (e.g. URL or title-timestamp hash) of the removed duplicate article. |
| `kept_title` | `Text` | `TEXT` | Nullable=False | Title of the kept article. |
| `deduplicated_title` | `Text` | `TEXT` | Nullable=False | Title of the removed duplicate article. |
| `similarity` | `Float` | `DOUBLE PRECISION` | Nullable=False | The calculated word overlap count (minimum 3). |
| `reason` | `String(250)` | `VARCHAR(250)` | Nullable=False | Description detailing the decision boundary (e.g., "Duplicate in 4h window, source priority tie-breaker"). |
| `created_at` | `DateTime(timezone=True)` | `TIMESTAMP WITH TIME ZONE` | Nullable=False, server_default=now() | Audit log insertion timestamp. |

### Indexes
- Index on `symbol`: speeds up queries for deduplication logs by stock.
- Compound Index on `(kept_id, deduplicated_id)`: ensures fast lookups when verifying specific parent-child relationships.

---

## 2. Telemetry Schema: `AnalysisHistory.shadow_outputs`

The kept-vs-original telemetry statistics are stored in the existing JSONB column `shadow_outputs` of the `AnalysisHistory` record.

### JSON Structure: `shadow_outputs`

For this feature, a nested object under the key `"news_dedup"` is added:

```json
{
  "news_dedup": {
    "original_news_count": 12,
    "kept_news_count": 8,
    "removed_news_count": 4,
    "executed_at": "2026-07-21T13:07:35.123456Z"
  }
}
```

### Data Validation Rules
- `original_news_count` MUST be an integer between 0 and 50 (due to input capping).
- `kept_news_count` MUST be an integer between 0 and 50.
- `removed_news_count` MUST equal `original_news_count - kept_news_count`.
- `executed_at` MUST be a valid ISO 8601 UTC timestamp string.
