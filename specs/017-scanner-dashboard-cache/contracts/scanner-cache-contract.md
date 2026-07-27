# Interface & Contract Specification: Scanner Dashboard Cache

**Feature Branch**: `017-scanner-dashboard-cache`  
**Created**: 2026-07-27  
**Status**: Completed  
**Feature Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/017-scanner-dashboard-cache/spec.md)

---

## 1. Endpoint Response Guarantees (100% Contract Parity)

Sprint 1 enforces **zero change** to external HTTP contracts for `/scanner/latest` and `/analysis/scan/latest`.

### 1.1 Endpoint 1: `GET /scanner/latest`

#### Request Parameters
- **Query Parameters**: `force` (Optional, Boolean, e.g. `?force=true`)
- **Headers**: `Cache-Control` (Optional, String, e.g. `Cache-Control: no-cache`)

#### Response Headers
- `Content-Type`: `application/json`
- `X-Cache-Status`: `HIT` | `MISS` | `BYPASS` | `FALLBACK` (Observability header)

#### Response Body Schema (Unchanged Baseline)
```json
{
  "available": true,
  "scan_timestamp": "2026-07-27T09:45:00Z",
  "total_records": 150,
  "data": [
    {
      "symbol": "RELIANCE",
      "score": 85.5,
      "signal": "BUY",
      "indicators": {
        "rsi": 62.4,
        "ema_50": 2840.10
      }
    }
  ]
}
```

---

### 1.2 Endpoint 2: `GET /analysis/scan/latest`

#### Request Parameters
- **Query Parameters**: `force` (Optional, Boolean, e.g. `?force=true`)
- **Headers**: `Cache-Control` (Optional, String, e.g. `Cache-Control: no-cache`)

#### Response Headers
- `Content-Type`: `application/json`
- `X-Cache-Status`: `HIT` | `MISS` | `BYPASS` | `FALLBACK`

#### Response Body Schema (Unchanged Baseline)
```json
{
  "available": true,
  "analysis_id": "an-20260727-094500",
  "summary": {
    "bullish_count": 42,
    "bearish_count": 12,
    "market_regime": "BULLISH_TREND"
  },
  "items": []
}
```

---

## 2. Internal Cache Service Contract

```python
class IScannerCacheService:
    async def get_latest_scan(self, key: str) -> Optional[str]:
        """Fetch pre-serialized JSON string from Redis cache with timeout bound (50ms)."""
        ...

    async def set_latest_scan(self, key: str, payload_json: str, ttl_seconds: int) -> bool:
        """Store pre-serialized JSON string into Redis cache with TTL."""
        ...

    async def invalidate_scan_cache(self, keys: List[str]) -> bool:
        """Purge specified cache keys from Redis."""
        ...
```
