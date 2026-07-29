# Service & API Contracts: Reduce Scan-Result Fan-out (Sprint 3)

## 1. Scanner Persistence Service Internal Interface

```python
class ScanPersistenceManager:
    """Unified persistence controller for scan execution results."""

    async def persist_scan_results(
        self,
        scan_id: str,
        response: ScreenerResponse,
        duration_ms: int,
        save_history: bool = False,
    ) -> ScanPersistOutcome:
        """
        Executes scan result persistence according to feature flag configuration.

        If SCAN_RESULT_MINIMAL_WRITES is OFF:
            Executes legacy multi-table writes across all 6 tables.

        If SCAN_RESULT_MINIMAL_WRITES is ON:
            1. Upserts candidates to `latest_scan_results` (Canonical Source).
            2. IF `save_history=true`, inserts scan envelope to `market_data.scan_results`.
            3. Bypasses writes to `scan_snapshots`, `scan_snapshot_records`,
               `scan_history_snapshots`, and `scanned_candidates`.
        """
        ...
```

---

## 2. Rest API Response Contracts (Immutable)

### Endpoint: `GET /api/v1/scanner/latest`

#### Response 200 OK (Contract Unchanged)
```json
{
  "scan_id": "8f3b2a1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "status": "COMPLETED",
  "data_source": "FYERS",
  "scanned_symbols": 500,
  "shortlisted_symbols": ["RELIANCE", "INFY"],
  "buy_candidate_symbols": ["RELIANCE"],
  "watch_candidate_symbols": ["INFY"],
  "scan_timestamp": "2026-07-27T14:00:00Z",
  "duration_ms": 1420,
  "items": [
    {
      "symbol": "RELIANCE",
      "signal": "BUY",
      "score": 88.0,
      "confidence": 0.95,
      "matched": true
    },
    {
      "symbol": "INFY",
      "signal": "WATCH",
      "score": 72.5,
      "confidence": 0.81,
      "matched": true
    }
  ]
}
```

### Endpoint: `GET /api/v1/dashboard/candidates`

#### Response 200 OK (Contract Unchanged)
```json
{
  "timestamp": "2026-07-27T14:00:00Z",
  "total_candidates": 2,
  "buy_count": 1,
  "watch_count": 1,
  "candidates": [
    {
      "symbol": "RELIANCE",
      "action": "BUY",
      "score": 88.0
    },
    {
      "symbol": "INFY",
      "action": "WATCH",
      "score": 72.5
    }
  ]
}
```
