# REAL SCANNER RUNTIME AUDIT

## Objective
Audit the actual runtime performance of the market screening pipeline under true production conditions (live PostgreSQL, actual FYERS APIs, real NIFTY 500 universe constraints) without utilizing mock data or synthetic substitutions.

## Execution Details
- **Trigger**: `automated_screening_job`
- **Execution Date**: `2026-05-31 16:05:57 UTC`
- **Universe Configuration**: NIFTY 500 / BSE 500 equivalent sets (Total requested: 755)

## Overall Runtime Measurements
- **Scanner Start Time**: `2026-05-31 16:05:57.18 UTC`
- **Scanner End Time**: `2026-05-31 16:14:44.32 UTC`
- **Total Duration**: **527.14 seconds** (approx 8.7 minutes)

## Verification of Output (Captured before crash)
- **Total Symbols Requested**: 755
- **Valid Symbols** (Post-FYERS & Data Quality): 700
- **Rejected by Technical Conditions**: 619
- **Matched for Shortlist**: 81 (Filtered down to Top 20)
- **Buy Count / Watch Count**: N/A (Execution failed prior to recommendation assignment)

## Verification of Persistence
- **scan_snapshots row created**: Verified (1 row created before failure)
- **scan_snapshot_records inserted**: 0 (Failed before population phase)
- **Latest snapshot timestamp**: `2026-05-31 14:32:08.75 UTC` (from a prior successful run, confirming database connectivity and schema).

## Dashboard Flow Verification
- `GET /scanner/latest` was not populated with the *current* 16:05 UTC run due to execution crash prior to the final persistence commit.

## Final Conclusion
**SCANNER_FAILURE_DETECTED**

The scanner executed for 527.14 seconds before hitting a fatal structural crash during Stage 7 (Full Analysis / Recommendation Generation). A core `UnboundLocalError: cannot access local variable 'asyncio'` inside `_analyze_symbol_post_bulk` completely halted the final leg of execution.
