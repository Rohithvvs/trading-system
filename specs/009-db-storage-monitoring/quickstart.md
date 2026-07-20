# Quickstart & Validation Guide: Sprint 4 – Database Storage + Basic Monitoring

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/spec.md)
**Created**: 2026-07-20

---

## 1. Prerequisites

1. Ensure the active database migrations are applied:
   ```bash
   alembic upgrade head
   ```
2. Verify environment configuration variables are populated in your `.env` file:
   - `FYERS_CLIENT_ID`, `FYERS_APP_ID`, `FYERS_APP_SECRET`, `FYERS_TOTP_SECRET`, `FYERS_PIN`
   - `DATABASE_URL` (pointing to the correct environment DB instance: local/development or production)

---

## 2. Validation Scenarios

### Scenario A: Verify Success Persistence

1. Set up valid Fyers credential variables in your shell or `.env` file.
2. Run the update token script:
   ```bash
   python update_token.py
   ```
3. **Expected Output**:
   - Console logs `Token updated successfully. Masked token: FYERS:******[Last 4 chars]`.
   - Exit code is `0`.
4. Run the validation query using [check_token.py](file:///D:/Work_Space/trading-system/check_token.py):
   ```bash
   python check_token.py
   ```
5. **Expected Outcome**:
   - The retrieved token record shows `is_active = True`, `status = "Success"`, `last_error` is empty or `None`, and the updated timestamp matches the execution time.

---

### Scenario B: Verify Failure Logging

1. Temporarily modify your `.env` to set an invalid `FYERS_PIN` (e.g. `9999`).
2. Run the update token script:
   ```bash
   python update_token.py
   ```
3. **Expected Output**:
   - The CLI writes the authentication failure error to standard error.
   - Exit code is `1`.
4. Run the validation query using [check_token.py](file:///D:/Work_Space/trading-system/check_token.py):
   ```bash
   python check_token.py
   ```
5. **Expected Outcome**:
   - The retrieved token record shows `status = "Failed"`, `last_error` contains the PIN verification failure details, and the updated timestamp matches the failure execution time.
   - The previous valid access token is preserved (not deleted or nullified) in the `access_token` column.
