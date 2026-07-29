# Quickstart Validation Guide: Unify Latest-Scan APIs

**Feature**: Unify Latest-Scan APIs  
**Branch**: `018-unify-latest-scan-apis`  
**Date**: 2026-07-27  

## Overview
This guide provides actionable commands and verification scenarios to validate that Sprint 2 implementation preserves 100% backward compatibility and parity across `GET /scanner/latest` and `GET /analysis/scan/latest`.

---

## Prerequisites & Test Execution

### 1. Run Automated Integration & Parity Test Suite
```powershell
pytest backend/app/tests/test_scanner_routes_cached.py -v
```

### 2. Run Parity Verification Script (Dual-Path Comparison)
```powershell
python -m pytest backend/app/tests/test_unified_latest_scan_parity.py -v
```

---

## Validation Scenarios

### Scenario 1: Dual-Path Parity Verification
- **Goal**: Prove that response bodies from both endpoints under `SCANNER_UNIFIED_LATEST_ENABLED=true` are 100% identical to `SCANNER_UNIFIED_LATEST_ENABLED=false`.
- **Steps**:
  1. Execute `GET /scanner/latest` with feature flag `OFF`, record JSON body `B1`.
  2. Execute `GET /scanner/latest` with feature flag `ON`, record JSON body `B2`.
  3. Verify `B1 == B2`.
  4. Repeat for `GET /analysis/scan/latest`.

### Scenario 2: Feature Flag Toggle & Rollback
- **Goal**: Confirm instant zero-downtime path switching.
- **Steps**:
  1. Set `SCANNER_UNIFIED_LATEST_ENABLED=false`.
  2. Request `GET /scanner/latest` → Observe log: `latest_scan_requested`.
  3. Set `SCANNER_UNIFIED_LATEST_ENABLED=true`.
  4. Request `GET /scanner/latest` → Observe log: `unified_latest_scan_requested`.

### Scenario 3: Redis Cache Reuse & `X-Cache-Status`
- **Goal**: Verify Sprint 1 cache reuse under unified service.
- **Steps**:
  1. Send `GET /scanner/latest` twice.
  2. Request 1 header: `X-Cache-Status: MISS` (or `BYPASS` if cache disabled).
  3. Request 2 header: `X-Cache-Status: HIT`.
  4. Request with `?force=true`: `X-Cache-Status: MISS` and cache refreshed.
