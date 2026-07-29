# Interface Contract: Authoritative Candle Store API (Sprint 4)

**Feature Branch**: `020-authoritative-candle-store`  
**Date**: 2026-07-27  
**Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/spec.md)  

---

## 1. Internal Service Interface Contract

The `AuthoritativeCandleStore` service interface (`backend/app/services/authoritative_candle_store.py`) exposes the following methods:

### 1.1 `get_candles()`

Retrieve continuous OHLCV candles for a given symbol, resolution, and date range.

#### Request Parameters
```python
async def get_candles(
    self,
    symbol: str,
    resolution: str,
    start_date: datetime | str,
    end_date: datetime | str,
    force_provider_fetch: bool = False
) -> list[OHLCVPoint]:
```

#### Response Contract
- Returns: `list[OHLCVPoint]` sorted chronologically ascending by timestamp.
- Guarantees:
  - Timezone-aware UTC timestamps.
  - Zero data gaps for valid trading days within provider availability boundaries.
  - Byte-level identical arrays for identical query arguments across Scanner, Analysis, Backtest, and Dashboard API callers.

---

### 1.2 `ingest_candles()`

Idempotently persist external or generated candle arrays into storage.

#### Request Parameters
```python
async def ingest_candles(
    self,
    symbol: str,
    resolution: str,
    candles: list[OHLCVPoint],
    source: str = "FYERS"
) -> IngestionResult:
```

#### Response Contract
```python
class IngestionResult(BaseModel):
    symbol: str
    resolution: str
    inserted_count: int
    updated_count: int
    dual_write_status: str  # "SUCCESS", "SKIPPED", or "DEGRADED"
```

---

### 1.3 `validate_consistency()`

Audit database candles against external provider state or secondary cache.

#### Request Parameters
```python
async def validate_consistency(
    self,
    symbols: list[str],
    resolution: str,
    sample_ratio: float = 0.01
) -> AuditReport:
```

#### Response Contract
```python
class AuditReport(BaseModel):
    total_audited: int
    matched_count: int
    mismatched_count: int
    repaired_count: int
    discrepancies: list[dict]
```

---

## 2. Dynamic Governance Route API

Existing runtime routing table endpoint exposed per `AGENTS.md` rules:

```http
GET /api/v1/governance/routes
```

#### Response Payload
```json
{
  "total_routes": 16,
  "routes": {
    "experiment.start": "app.governance.experiment_cli:experiment_cli start",
    "candle_store.status": "app.services.authoritative_candle_store:status"
  }
}
```
