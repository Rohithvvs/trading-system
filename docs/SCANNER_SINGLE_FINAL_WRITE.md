# Technical Architecture: Scanner Single Final Write (Sprint 5)

## Overview
Sprint 5 introduces a **Single Final Write** architecture for the market scanning engine in `trading-system`. 

Instead of progressively persisting symbol results or scan metadata during analysis loops, the scanner performs 100% of candle fetching, technical indicator evaluation, filtering, and candidate ranking in memory. Upon scan completion, an in-memory `ScanAggregateResult` object is passed to `ScannerSingleWriteService`, which executes a single atomic transaction updating `latest_scan_results` (and optionally `market_data.scan_results` if `save_history=true`).

---

## Configuration & Feature Flag
Protected under the feature flag:

```env
SCANNER_SINGLE_FINAL_WRITE_ENABLED=true
```

- **`true` / `ON`**: Single final write architecture (100% in-memory analysis, 1 atomic DB commit, 30s timeout guard).
- **`false` / `OFF`**: Legacy / minimal write persistence path. Instant zero-downtime operational rollback.

---

## Data Flow & Architecture

```
[ Market Data Fetching & Technical Analysis ] ◄── (100% In-Memory)
                       │
                       ▼
            [ ScanAggregateResult ]
                       │
     [ SCANNER_SINGLE_FINAL_WRITE_ENABLED? ]
                       │
        ┌──────────────┴──────────────┐
     ON │                          OFF│
        ▼                             ▼
[ Single Atomic DB Commit ]   [ Legacy Multi-Commit ]
        │ (1 Commit)
        ├─► latest_scan_results
        └─► (Opt) market_data.scan_results (if save_history=true)
```

---

## Performance & Telemetry Metrics

- `scanner_single_write_duration_seconds`: Histogram measuring single final transaction duration.
- `scanner_analysis_duration_seconds`: Histogram measuring in-memory calculation time.
- `scanner_transactions_total`: Counter measuring total DB transactions per scan.
- `scanner_single_write_failures_total`: Counter tracking transaction rollbacks.
- `scanner_feature_flag_single_write`: Gauge indicating current `SCANNER_SINGLE_FINAL_WRITE_ENABLED` status (1=ON, 0=OFF).
