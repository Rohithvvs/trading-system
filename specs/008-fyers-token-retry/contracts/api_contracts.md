# Interface Contracts: Sprint 3 – Retry Logic in Token Generation

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/008-fyers-token-retry/spec.md)
**Created**: 2026-07-20

---

## 1. Python Library Interface (Preserved Signature)

The function signature remains identical to Sprint 2 to maintain backwards compatibility:

```python
def generate_fyers_access_token() -> str:
    """
    Generates a valid Fyers API v3 access token using TOTP.
    Automatically retries up to 3 times on transient failures.

    Returns:
        str: The generated Fyers API v3 access token.

    Raises:
        FyersConfigError: Fail-fast if configuration is missing or invalid.
        FyersAuthError: If authentication fails permanently or after 3 transient retries.
        FyersConnectionError: If network connections fail persistently after 3 retries.
    """
```

### Caller guidance (error handling)

- Prefer catching **exception types** (`FyersConfigError`, `FyersAuthError`, `FyersConnectionError`).
- After exhausted retries, the raised message retains the original step error text and appends  
  `[after N attempts; maximum retries exhausted]`.
- Attributes on the raised exception (when retries exhausted):
  - `attempts` — number of attempts used
  - `max_attempts` — configured maximum (3)
  - `original_error` / `__cause__` — underlying step failure
- Do **not** confuse this module with the ORM model:
  - Generator: `from fyers_token import generate_fyers_access_token`
  - Model: `from backend.app.models.fyers_token import FyersToken` (or `app.models.fyers_token` under `backend/`)

### Scope boundary

This contract covers **token generation only**. Saving to `fyers_tokens`, UI save APIs, and cron/scheduler wiring are **out of scope** for Sprint 3 and remain downstream concerns.

---

## 2. CLI Interface (Preserved Behavior)

### Command Execution
```bash
python fyers_token.py
```

### Outputs
- **On Success**: Prints only the raw access token string to `stdout` and exits with code `0`.
- **On Permanent / Retried Failure**: Writes a descriptive error message to `stderr` and exits with status code `1` after all attempts fail.
