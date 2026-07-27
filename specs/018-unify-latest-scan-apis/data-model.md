# Phase 1 Data Model: Unify Latest-Scan APIs

**Feature**: Unify Latest-Scan APIs  
**Branch**: `018-unify-latest-scan-apis`  
**Date**: 2026-07-27  

## Entity Definitions & Schemas

This feature alters no database tables or ORM entities. It reads existing persistence models and maps them into format-specific representations.

### 1. Underlying Source Entities (PostgreSQL ORM)

#### `ScanSnapshot` (Table: `scan_snapshots`)
- `scan_id`: String (UUID) [Primary Key]
- `scan_timestamp`: DateTime (UTC)
- `status`: String (`"COMPLETED"`, `"RUNNING"`, `"FAILED"`)
- `total_scanned`: Integer
- `valid_symbols`: Integer
- `buy_count`: Integer
- `watch_count`: Integer
- `rejected_count`: Integer

#### `ScanSnapshotRecord` (Table: `scan_snapshot_records`)
- `id`: Integer [Primary Key]
- `scan_id`: String [Foreign Key -> `scan_snapshots.scan_id`]
- `symbol`: String
- `recommendation`: String (`"BUY"`, `"WATCH"`, `"REJECTED"`)
- `score`: Float
- `close_price`: Float
- `sma50`: Float (Nullable)
- `sma200`: Float (Nullable)
- `rsi`: Float (Nullable)
- `macd`: Float (Nullable)
- `volume`: Integer
- `reason`: String (Nullable)

---

### 2. Output Data Representations (Domain Adapters)

#### A. Dashboard Format Payload Schema (`format_type="dashboard"`)
```json
{
  "scan_id": "string (UUID)",
  "scan_timestamp": "string (ISO-8601 UTC)",
  "last_scan_completed_at": "string (ISO-8601 UTC)",
  "total_scanned": "integer",
  "valid_symbols": "integer",
  "buy_count": "integer",
  "watch_count": "integer",
  "rejected_count": "integer",
  "buy_candidates": [
    {
      "symbol": "string",
      "recommendation": "BUY",
      "score": "float",
      "close_price": "float",
      "sma50": "float | null",
      "sma200": "float | null",
      "rsi": "float | null",
      "macd": "float | null",
      "volume": "integer",
      "reason": "string | null"
    }
  ],
  "watch_candidates": [],
  "rejected_candidates": []
}
```

#### Empty Dashboard Representation (when no scans exist)
```json
{
  "message": "No completed scans found",
  "buy_candidates": [],
  "watch_candidates": [],
  "rejected_candidates": []
}
```

---

#### B. Analysis Format Payload Schema (`format_type="analysis"`)
```json
{
  "available": true,
  "timestamp": "string (ISO-8601 UTC)",
  "scan_id": "string (UUID)",
  "total_symbols": "integer",
  "buy_signals": "integer",
  "watch_signals": "integer",
  "no_signals": "integer",
  "items": [
    {
      "symbol": "string",
      "recommendation": "string",
      "score": "float",
      "close_price": "float",
      "technical": {
        "sma50": "float | null",
        "sma200": "float | null",
        "rsi": "float | null",
        "macd": "float | null"
      },
      "reason": "string | null"
    }
  ]
}
```

#### Empty Analysis Representation (when no scans exist)
```json
{
  "available": false
}
```
