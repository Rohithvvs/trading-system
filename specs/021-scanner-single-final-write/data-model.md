# Data Model & In-Memory Entities: Scanner Single Final Write (Sprint 5)

**Feature**: Scanner Single Final Write  
**Status**: Complete  
**Spec**: [spec.md](spec.md)  

---

## 1. In-Memory Aggregate Entities (Non-Persisted until Final Write)

### `ScanAggregateResult`
Represents the complete aggregated outcome of a market scan execution before persistence.

```python
class ScanAggregateResult:
    scan_id: str                          # Unique execution UUID for the scan cycle
    symbol_universe: str                  # Target universe (e.g., "NIFTY500")
    execution_timestamp: datetime         # ISO-8601 UTC timestamp of scan execution
    candidates: List[ScanCandidateDTO]    # List of filtered symbol candidates matching setup criteria
    total_scanned: int                    # Total count of symbols evaluated
    total_candidates: int                 # Total count of matching candidates
    execution_duration_ms: float          # Time taken for in-memory analysis
    save_history: bool                    # Flag indicating whether history retention is requested
    status: str                           # "SUCCESS", "TIMEOUT", "FAILED"
```

### `ScanCandidateDTO`
Represents an individual symbol candidate match identified during in-memory technical analysis.

```python
class ScanCandidateDTO:
    symbol: str                           # Trading symbol (e.g., "NSE:RELIANCE-EQ")
    strategy_name: str                    # Name of setup strategy (e.g., "MOMENTUM_BREAKOUT")
    signal_type: str                      # "BUY", "SELL", "NEUTRAL"
    score: float                          # Candidate ranking score (0.0 to 100.0)
    timeframe: str                        # Chart timeframe (e.g., "5m", "15m", "1d")
    close_price: float                    # Asset price at scan time
    volume: int                           # Volume snapshot
    indicator_values: Dict[str, Any]      # Extracted indicators (e.g., {"rsi": 68.5, "ema50": 2450.0})
    metadata: Dict[str, Any]              # Additional contextual signals
```

---

## 2. Canonical Target Entities (Database Tables)

### `latest_scan_results` (Primary Canonical Storage Target)
Maintains current market scan state for live dashboard queries.

| Field Name | Type | Key Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigInt | Primary Key (Auto-increment) | Internal record identifier |
| `symbol` | VarChar(50) | Unique Composite Index | Target asset symbol |
| `strategy_name` | VarChar(100) | Unique Composite Index | Applied strategy identifier |
| `signal_type` | VarChar(20) | Indexed | "BUY", "SELL", or "NEUTRAL" |
| `score` | Numeric(10,4) | Indexed | Calculated setup score |
| `timeframe` | VarChar(20) | - | Chart candle timeframe |
| `close_price` | Numeric(14,4) | - | Last traded price at scan time |
| `volume` | BigInt | - | Volume at scan time |
| `indicators_json` | JSONB | - | Serialized indicator dictionary |
| `updated_at` | TimestampTZ | Indexed | Timestamp of last scan update |

---

### `market_data.scan_results` (Conditional Historical Retention Target)
Stores historical scan records when `save_history=true`.

| Field Name | Type | Key Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigInt | Primary Key | Historical record ID |
| `scan_id` | UUID | Foreign Key / Index | Execution run identifier |
| `symbol` | VarChar(50) | Indexed | Target asset symbol |
| `strategy_name` | VarChar(100) | Indexed | Strategy name |
| `signal_type` | VarChar(20) | - | Signal classification |
| `score` | Numeric(10,4) | - | Setup score |
| `created_at` | TimestampTZ | Partition / Index | Execution timestamp |

---

## 3. Entity State Transitions

```
[ Scan Initiated ]
       │
       ▼
[ Universe Fetching (In-Memory) ]
       │
       ▼
[ Technical Analysis & Filtering (In-Memory) ]
       │
       ▼
[ ScanAggregateResult Built (In-Memory) ]
       │
       ├─────────────────────────────────┐
       ▼ (Valid Result & Flag ON)        ▼ (Timeout / Calculation Error)
[ Single Final DB Transaction ]    [ Abort - 0 DB Writes ]
       │                                 │
       ├── Upsert latest_scan_results     ▼
       │   (And insert history if true)  [ Emit Telemetry & Log Error ]
       │
       ▼
[ Transaction Committed (1 Commit) ]
```
