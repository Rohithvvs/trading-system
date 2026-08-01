# API Contracts: Unify Latest-Scan APIs

**Feature**: Unify Latest-Scan APIs  
**Branch**: `018-unify-latest-scan-apis`  
**Date**: 2026-07-27  

## Endpoint Contracts (Preserved 100% Backward Compatibility)

### 1. `GET /scanner/latest`

#### Description
Retrieves the latest completed market scanner snapshot categorized into buy candidates, watch candidates, and rejected candidates for dashboard rendering.

#### Request Parameters
- **Query Parameters**:
  - `force` (boolean, optional, default: `false`): Force bypass of Redis cache and query fresh snapshot from database.
- **Headers**:
  - `Cache-Control` (string, optional): If `no-cache`, forces cache refresh.

#### Response Specifications
- **HTTP 200 OK**:
  - **Content-Type**: `application/json`
  - **Headers**:
    - `X-Cache-Status`: `HIT` | `MISS` | `BYPASS` | `FALLBACK`
  - **Body Schema (Populated)**:
    ```json
    {
      "scan_id": "string",
      "scan_timestamp": "string (ISO-8601)",
      "last_scan_completed_at": "string (ISO-8601)",
      "total_scanned": 0,
      "valid_symbols": 0,
      "buy_count": 0,
      "watch_count": 0,
      "rejected_count": 0,
      "buy_candidates": [],
      "watch_candidates": [],
      "rejected_candidates": []
    }
    ```
  - **Body Schema (Empty State)**:
    ```json
    {
      "message": "No completed scans found",
      "buy_candidates": [],
      "watch_candidates": [],
      "rejected_candidates": []
    }
    ```

---

### 2. `GET /analysis/scan/latest`

#### Description
Retrieves the latest completed scan payload formatted for deep technical analysis engines and research consumers.

#### Request Parameters
- **Query Parameters**:
  - `force` (boolean, optional, default: `false`): Force bypass of Redis cache and query fresh snapshot from database.
- **Headers**:
  - `Cache-Control` (string, optional): If `no-cache`, forces cache refresh.

#### Response Specifications
- **HTTP 200 OK**:
  - **Content-Type**: `application/json`
  - **Headers**:
    - `X-Cache-Status`: `HIT` | `MISS` | `BYPASS` | `FALLBACK`
  - **Body Schema (Populated)**:
    ```json
    {
      "available": true,
      "timestamp": "string (ISO-8601)",
      "scan_id": "string",
      "total_symbols": 0,
      "buy_signals": 0,
      "watch_signals": 0,
      "no_signals": 0,
      "items": []
    }
    ```
  - **Body Schema (Empty State)**:
    ```json
    {
      "available": false
    }
    ```
