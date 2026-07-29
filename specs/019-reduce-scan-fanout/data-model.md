# Data Model & Storage Plan: Reduce Scan-Result Fan-out (Sprint 3)

## 1. Physical Table Classifications

Sprint 3 alters write behavior across 6 existing physical tables based on the `SCAN_RESULT_MINIMAL_WRITES` feature flag. **No tables or columns will be created, modified, or dropped.**

| Table Name | Schema | Primary Key / Constraints | Role under Minimal Write Mode (`SCAN_RESULT_MINIMAL_WRITES = ON`) |
| :--- | :--- | :--- | :--- |
| `latest_scan_results` | `public` | `id` (PK), `symbol` (Unique) | **Canonical Latest Source**: Always written via atomic batch upsert for every scan execution. |
| `market_data.scan_results` | `market_data` | `id` (PK) | **Conditional History Archive**: Written ONLY when `save_history=true` or scheduled milestone run. |
| `scan_snapshots` | `public` | `id` (PK), `scan_id` (Unique) | **Bypassed (No Write)**: Preserved on disk for historical audit; no new records inserted when flag is ON. |
| `scan_snapshot_records` | `public` | `id` (PK), `scan_id` (FK) | **Bypassed (No Write)**: Preserved on disk; candidates derived virtually from `latest_scan_results`. |
| `scan_history_snapshots` | `public` | `id` (PK) | **Bypassed (No Write)**: Preserved on disk; historical analytics pull from `market_data.scan_results`. |
| `scanned_candidates` | `public` | `id` (PK) | **Bypassed (No Write)**: Preserved on disk; virtual list projected from `latest_scan_results`. |

---

## 2. Canonical Model Projection: `LatestScanResult`

### Entity Attributes
* `id` (Integer): Primary Key
* `symbol` (String): Unique symbol identifier (e.g. `RELIANCE`, `TCS`)
* `signal_type` (String): Scanner recommendation (`BUY`, `WATCH`, `REJECT`)
* `score` (Float): Screener technical evaluation score
* `confidence` (Float): Signal confidence metric
* `scanned_at` (DateTime): Timestamp when scan cycle completed
* `created_at` (DateTime): Record creation timestamp
* `updated_at` (DateTime): Record update timestamp

### Upsert Contract
```sql
INSERT INTO latest_scan_results (symbol, signal_type, score, confidence, scanned_at, updated_at)
VALUES (:symbol, :signal_type, :score, :confidence, :scanned_at, NOW())
ON CONFLICT (symbol) DO UPDATE SET
    signal_type = EXCLUDED.signal_type,
    score = EXCLUDED.score,
    confidence = EXCLUDED.confidence,
    scanned_at = EXCLUDED.scanned_at,
    updated_at = NOW();
```

---

## 3. Read Projection Mapping for Virtual Candidates

When GET `/api/v1/scanner/latest` or `/api/v1/dashboard/candidates` is requested:
1. System queries `latest_scan_results` WHERE `updated_at >= :scan_window_start`.
2. Filter criteria (e.g., `signal_type IN ('BUY', 'WATCH')`) applied in-memory / SQL WHERE clause.
3. Outbound JSON payload structured identical to legacy response DTO.

```json
{
  "status": "COMPLETED",
  "scanned_symbols": 500,
  "shortlisted_symbols": ["RELIANCE", "TCS"],
  "buy_candidate_symbols": ["RELIANCE"],
  "watch_candidate_symbols": ["TCS"],
  "items": [
    {
      "symbol": "RELIANCE",
      "signal": "BUY",
      "score": 85.5,
      "confidence": 0.92,
      "matched": true
    }
  ]
}
```
