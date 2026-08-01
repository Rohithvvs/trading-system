# Data Model & Domain Schema: Authoritative Candle Store (Sprint 4)

**Feature Branch**: `020-authoritative-candle-store`  
**Date**: 2026-07-27  
**Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/spec.md)  

---

## 1. Domain Entities & Schemas

### 1.1 `OHLCVPoint` (Canonical Data Transfer Object)
Pydantic v2 schema representing a single canonical candle point.

```python
class OHLCVPoint(BaseModel):
    timestamp: datetime       # UTC timezone aware datetime
    open: Decimal             # Numeric(18, 8)
    high: Decimal             # Numeric(18, 8)
    low: Decimal              # Numeric(18, 8)
    close: Decimal            # Numeric(18, 8)
    volume: Decimal           # Numeric(18, 8)
```

### 1.2 `HistoricalCandle` (Database Persistence Model)
Existing SQLAlchemy model mapped to `historical_candles` table in PostgreSQL.

| Field Name | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Auto-incrementing surrogate key |
| `symbol` | `String(50)` | Indexed, Nullable=False | Market symbol (e.g., `NSE:RELIANCE-EQ`) |
| `resolution` | `String(20)` | Indexed, Nullable=False | Timeframe resolution (e.g., `1D`, `5m`, `15m`) |
| `timestamp` | `DateTime(tz=True)` | Indexed, Nullable=False | UTC candle start timestamp |
| `open` | `Numeric(18,8)` | Nullable=False | Opening price |
| `high` | `Numeric(18,8)` | Nullable=False | Highest price |
| `low` | `Numeric(18,8)` | Nullable=False | Lowest price |
| `close` | `Numeric(18,8)` | Nullable=False | Closing price |
| `volume` | `Numeric(18,8)` | Nullable=False | Traded volume |
| `source` | `String(20)` | Default=`"FYERS"` | Market feed source tag |
| `created_at` | `DateTime(tz=True)` | Default=UTC now | Record insertion time |
| `updated_at` | `DateTime(tz=True)` | OnUpdate=UTC now | Record last update time |

#### Database Indexes & Constraints
- `UniqueConstraint("symbol", "resolution", "timestamp", name="uq_historical_candle")`
- `Index("idx_hist_candles_sym_res_ts", "symbol", "resolution", "timestamp")`
- `Index("idx_hist_candles_sym_ts", "symbol", "timestamp")`

---

## 2. In-Memory L1 Cache Data Model

### 2.1 Cache Key Structure
- **Format**: `candle_l1:{symbol}:{resolution}`
- **Example**: `candle_l1:NSE:RELIANCE-EQ:1D`

### 2.2 Cache Value Model
```python
@dataclass
class L1CacheEntry:
    symbol: str
    resolution: str
    candles: list[OHLCVPoint]
    start_time: datetime
    end_time: datetime
    last_accessed: float
```
- **Eviction Strategy**: Least Recently Used (LRU) with bounded maximum capacity (default: 2,000 active series).

---

## 3. Data Integrity & Validation Rules

1. **OHLC Constraint**: $high \ge \max(open, close)$ and $low \le \min(open, close)$.
2. **Timestamp Monotonicity**: For candle array $[c_0, c_1, \dots, c_n]$, $c_{i}.timestamp < c_{i+1}.timestamp$.
3. **Volume Constraint**: $volume \ge 0$.
4. **Timezone Rule**: All timestamps stored and returned must be timezone-aware UTC datetimes.
