# REST API Interface Contracts (Single-Owner Platform)

**Feature Branch**: `027-phase2-transformation` | **Date**: 2026-07-31  
**Spec**: [spec.md](file:///E:/Trading_lab/trading-system/specs/027-phase2-transformation/spec.md)

---

## 1. Scanner & Market Discovery Endpoints

### 1.1 Trigger Market Scan
* **Endpoint**: `POST /api/v1/scanner/scan`
* **Auth**: None (Single-Owner Environment)
* **Response**:
  ```json
  {
    "status": "success",
    "scan_id": "8f3b2a11-5e29-4b89-a67b-123456789abc",
    "total_symbols_evaluated": 500,
    "candidates_found": 12,
    "completed_at": "2026-07-31T18:30:00Z"
  }
  ```

### 1.2 Fetch Latest Candidates
* **Endpoint**: `GET /api/v1/scanner/latest`
* **Response**:
  ```json
  {
    "scan_timestamp": "2026-07-31T18:30:00Z",
    "results": [
      {
        "symbol": "RELIANCE",
        "close_price": 2980.50,
        "supertrend_signal": "BUY",
        "score": 88.5,
        "ema50": 2910.00,
        "ema200": 2750.00
      }
    ]
  }
  ```

---

## 2. Recommendation Engine Endpoints

### 2.1 Get Active Recommendations
* **Endpoint**: `GET /api/v1/analysis/recommendations`
* **Response**:
  ```json
  [
    {
      "id": "rec_001",
      "symbol": "TCS",
      "signal_type": "BUY",
      "conviction_score": 92.0,
      "entry_target": 4150.00,
      "stop_loss": 4020.00,
      "target_price": 4350.00,
      "ai_rationale": "Strong sector relative strength combined with EMA50 breakout and bullish MACD crossover."
    }
  ]
  ```

---

## 3. Paper Trading Endpoints (Single Owner Context)

### 3.1 Fetch Account Details
* **Endpoint**: `GET /api/v1/paper-trading/accounts`
* **Response**:
  ```json
  {
    "account_id": "acc_001",
    "user_id": "00000000-0000-0000-0000-000000000001",
    "current_balance": 1054200.00,
    "realized_pnl": 54200.00,
    "unrealized_pnl": 12300.00,
    "open_positions_count": 3
  }
  ```

### 3.2 Place Paper Order
* **Endpoint**: `POST /api/v1/paper-trading/orders`
* **Request Payload**:
  ```json
  {
    "symbol": "TCS",
    "order_type": "MARKET",
    "side": "BUY",
    "quantity": 25,
    "stop_loss": 4020.00,
    "target_price": 4350.00
  }
  ```
* **Response**:
  ```json
  {
    "order_id": "ord_9912",
    "status": "FILLED",
    "executed_price": 4150.00,
    "timestamp": "2026-07-31T18:35:00Z"
  }
  ```

---

## 4. FYERS Broker & System Control Endpoints

### 4.1 FYERS OAuth Token Exchange
* **Endpoint**: `POST /fyers/auth/exchange`
* **Request Payload**:
  ```json
  {
    "auth_code": "fyers_auth_code_string"
  }
  ```
* **Response**:
  ```json
  {
    "status": "authenticated",
    "user_id": "00000000-0000-0000-0000-000000000001",
    "expires_at": "2026-08-01T06:00:00Z"
  }
  ```

### 4.2 Platform Governance Commands
* **Endpoint**: `GET /api/v1/governance/routes`
* **Response**: Exposes CLI governance command routing map from `AGENTS.md`.
