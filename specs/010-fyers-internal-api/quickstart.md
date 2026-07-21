# Quickstart Validation Guide: Sprint 5 – Internal API Endpoint

This guide details how to run, test, and validate the `POST /internal/refresh-fyers-token` endpoint locally.

## Prerequisites
- Backend local environment set up with dependencies installed.
- Valid `SCHEDULER_SECRET` variable set in your `.env` configuration file.
- SQLite or local Postgres DB running and accessible.

---

## 1. Local Validation with cURL

### A. Start the Local Server
From the project root directory, run:
```powershell
./start_backend.ps1
```
(By default, the server runs on `http://127.0.0.1:8000`)

---

### B. Test Unauthorized Access (Missing Header)
Verify that the security checks block requests without credentials.
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/internal/refresh-fyers-token"
```
* **Expected Outcome**: HTTP status `401 Unauthorized`.

---

### C. Test Forbidden Access (Invalid Key)
Verify that requests with a mismatched secret are blocked.
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/internal/refresh-fyers-token" -Headers @{"X-Scheduler-Secret" = "wrong_secret_key"}
```
* **Expected Outcome**: HTTP status `403 Forbidden`.

---

### D. Test Successful Token Refresh (Valid Key)
Using your configured secret:
```powershell
$secret = "your_actual_scheduler_secret_from_env"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/internal/refresh-fyers-token" -Headers @{"X-Scheduler-Secret" = $secret}
```
* **Expected Outcome**: HTTP status `200 OK` with JSON:
  ```json
  {"status": "success", "message": "Access token generated and saved successfully"}
  ```

---

## 2. Automated Test Suite Validation

Execute the backend routing test cases to verify contract compliance:
```powershell
pytest backend/tests/integration/test_token_refresh_route.py
```
* **Expected Outcome**: All route test cases pass (including mock success, failure exceptions, missing credentials, and wrong key verification).
