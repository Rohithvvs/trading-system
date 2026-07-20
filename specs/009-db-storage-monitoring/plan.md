# Implementation Plan: Sprint 4 – Database Storage + Basic Monitoring

**Branch**: `009-db-storage-monitoring` | **Date**: 2026-07-20 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/spec.md)
**Input**: Feature specification from `specs/009-db-storage-monitoring/spec.md`

---

## Summary

This plan defines the step-by-step implementation for storing the Fyers access token and tracking token generation outcomes in the database. When the daily token generation executes, the system will save the new token, update the status to `"Success"`, clear errors, and refresh timestamps. If generation fails after retries, the system will record `"Failed"` status and log the error message in the database while leaving the previous token intact as a fallback.

---

## Technical Context

- **Language/Version**: Python 3.11  
- **Primary Dependencies**: SQLAlchemy, requests, pyotp, pydantic-settings
- **Storage**: PostgreSQL (Production/Render/Neon), SQLite/PostgreSQL (Development)  
- **Testing**: pytest
- **Target Platform**: Windows / Linux server
- **Project Type**: CLI / Web-service
- **Performance Goals**: Database updates finalized in under 2.0s
- **Constraints**: Access token ciphertext encryption via Fernet keys, zero hardcoded credentials
- **Scale/Scope**: 1 token record row (`id=1`) updated daily

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

1. **Principle I: Library-First**:
   - *Status*: Passed. The persistence logic is encapsulated as a library-first utility function inside the existing `backend.app.services.token_service` module.
2. **Principle II: CLI Interface**:
   - *Status*: Passed. The updated `update_token.py` script provides a direct, executable CLI wrapper that outputs the masked status/tokens.
3. **Principle III: Test-First (NON-NEGOTIABLE)**:
   - *Status*: Passed. Regression coverage and test cases for both success and failure persistence flows are outlined in the plan.
4. **Principle V: Observability**:
   - *Status*: Passed. Structured warnings for failed attempts and information on retries/success are integrated, as well as database-level error monitoring.

---

## Database Design

### Recommended Table Name
We will reuse and update the existing **`fyers_tokens`** table instead of creating a new one.

### Columns and Data Types
The table schema mapping to the `FyersToken` model is:
- `id` (`Integer`, Primary Key)
- `access_token` (`Text`, Encrypted Fernet ciphertext)
- `created_at` (`DateTime(timezone=True)`, Defaults to UTC)
- `expires_at` (`DateTime(timezone=True)`, Nullable)
- `is_active` (`Boolean`, Defaults to True)
- `validated_at` (`DateTime(timezone=True)`, Nullable)
- `status` (`String(32)`, Defaults to `"active"`, used to record `"Success"` or `"Failed"`)
- `access_token_saved_at` (`DateTime(timezone=True)`, equivalent to `updated_at`)
- `last_error` (`Text`, Nullable)

### Decision
Reuse the existing system-wide config table `fyers_tokens`. We do not create a new table because system-wide headless credentials are already stored and managed there, avoiding redundant schema configurations.

---

## Code Structure & Recommended Functions

### 1. Persistence Service Function
Add to [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py):
```python
async def generate_and_persist_fyers_token(db: AsyncSession) -> dict[str, Any]:
    """
    Import generate_fyers_access_token from fyers_token.
    Wrapper to invoke token generation and handle database persistence.
    """
```

### 2. CLI Automation Runner
Refactor [update_token.py](file:///D:/Work_Space/trading-system/update_token.py):
```python
import asyncio
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import generate_and_persist_fyers_token

async def main():
    async with AsyncSessionLocal() as db:
        await generate_and_persist_fyers_token(db)
```

---

## Step-by-Step Implementation Plan

### Step 1: Create Database Migration
If the existing `fyers_tokens` schema needs to be initialized or validated, apply migrations. Since the columns `status`, `access_token_saved_at`, and `last_error` already exist on `FyersToken` model, ensure development and production databases are synced:
- Run `alembic upgrade head` to apply any outstanding schema changes.

### Step 2: Implement Save Logic in `token_service.py`
1. Define `generate_and_persist_fyers_token(db)` function.
2. Inside `try` block:
   - Call `generate_fyers_access_token()`.
   - Call `save_access_token(token, db)`.
   - Explicitly ensure the active row (ID=1) has `status = "Success"`, `last_error = None`, and `access_token_saved_at = now()`.
   - Commit transaction.
3. Inside `except Exception as exc` block:
   - Begin transaction.
   - Query the singleton row (ID=1) or create a placeholder if it does not exist.
   - Set `status = "Failed"`, `last_error = str(exc)`, and `access_token_saved_at = now()`.
   - Commit transaction.
   - Re-raise exception.

### Step 3: Refactor the CLI script `update_token.py`
1. Import `AsyncSessionLocal` and the new persistence service.
2. Wrap execution in `asyncio.run()`.
3. Handle exceptions cleanly by printing error messages to `sys.stderr` and exiting with status code `1`.
4. Exit with status code `0` on successful completion.

### Step 4: Environment Configurations
1. Ensure `DATABASE_URL` is parsed by Pydantic settings. Pydantic settings already handles database variables automatically.
2. Confirm the host environment variables (`FYERS_CLIENT_ID`, `FYERS_PIN`, etc.) are configured.

---

## Success Case & Failure Case Handling

### Success Case
1. `generate_fyers_access_token()` returns access token.
2. Service encrypts token using Fernet keys.
3. Database record `id = 1` gets updated:
   - `access_token` = ciphertext
   - `status` = `"Success"`
   - `last_error` = `None`
   - `access_token_saved_at` = UTC timestamp
4. Diagnostic history gets appended.
5. Exit code 0 returned.

### Failure Case
1. `generate_fyers_access_token()` raises exception.
2. Exception caught in persistence service.
3. Database record `id = 1` gets updated:
   - `access_token` = left unchanged (preserving last working token)
   - `status` = `"Failed"`
   - `last_error` = string representation of exception
   - `access_token_saved_at` = UTC timestamp
4. CLI prints error message to `stderr` and exits with code 1.

---

## How to Test Locally

### Test Unit / Integration Script
Create `tests/test_token_persistence.py` to cover:
1. **Successful Persistence Test**: Mock `generate_fyers_access_token` to return a fake JWT token. Verify that `generate_and_persist_fyers_token()` updates `fyers_tokens` with status `"Success"`, saves the encrypted token, and sets `last_error` to `None`.
2. **Failure Persistence Test**: Mock `generate_fyers_access_token` to raise an exception. Verify that `generate_and_persist_fyers_token()` updates `fyers_tokens` with status `"Failed"`, records the exception details, and preserves the old token.

Run the tests:
```bash
pytest tests/test_token_persistence.py
```

---

## Definition of Done

- [ ] New persistence service method `generate_and_persist_fyers_token` implemented.
- [ ] Table `fyers_tokens` columns correctly updated on success and failure runs.
- [ ] Root `update_token.py` CLI refactored to use dynamic Postgres session and async runners.
- [ ] Unit/Integration tests cover success and failure persistence states.
- [ ] Test cases run and pass locally with 100% assertions satisfied.
- [ ] Zero secrets or credentials hardcoded.
- [ ] Post-implementation code review completed.
