# API & Service Contracts: Scanner Single Final Write (Sprint 5)

**Feature**: Scanner Single Final Write  
**Status**: Complete  
**Spec**: [spec.md](../spec.md)  

---

## 1. REST API Contracts (100% Unchanged & Backward Compatible)

### GET `/api/v1/scanner/latest`
Returns current market scan candidates. Must produce identical payloads whether `SCANNER_SINGLE_FINAL_WRITE_ENABLED` is `ON` or `OFF`.

#### Response Contract (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "timestamp": "2026-07-28T10:30:00Z",
    "total_candidates": 12,
    "universe": "NIFTY500",
    "candidates": [
      {
        "symbol": "NSE:RELIANCE-EQ",
        "strategy_name": "MOMENTUM_BREAKOUT",
        "signal_type": "BUY",
        "score": 88.5,
        "timeframe": "15m",
        "close_price": 2450.75,
        "volume": 1254000,
        "indicators": {
          "rsi": 68.5,
          "ema50": 2410.0
        },
        "updated_at": "2026-07-28T10:30:00Z"
      }
    ]
  }
}
```

---

### GET `/api/v1/dashboard/candidates`
Returns candidate setups formatted for frontend dashboard display.

#### Response Contract (`200 OK`)
```json
{
  "count": 12,
  "last_updated": "2026-07-28T10:30:00Z",
  "results": [
    {
      "symbol": "NSE:RELIANCE-EQ",
      "setup": "MOMENTUM_BREAKOUT",
      "signal": "BUY",
      "rank_score": 88.5,
      "price": 2450.75
    }
  ]
}
```

---

## 2. Internal Service Contracts

### `ScannerPersistenceManager.persist_single_final_write`
Internal method contract executing the single final write transaction.

#### Signature
```python
async def persist_single_final_write(
    self,
    aggregate: ScanAggregateResult,
    db_session: AsyncSession
) -> SingleWriteResult:
    """
    Executes an atomic single-transaction persistence operation for a completed scan.
    
    Args:
        aggregate: Validated ScanAggregateResult holding all candidate DTOs.
        db_session: SQLAlchemy AsyncSession context.
        
    Returns:
        SingleWriteResult: Object containing write counts and transaction status.
    """
```

#### Return Object (`SingleWriteResult`)
```python
@dataclass
class SingleWriteResult:
    success: bool
    latest_rows_upserted: int
    history_rows_inserted: int
    transaction_duration_ms: float
    error_message: Optional[str] = None
```
