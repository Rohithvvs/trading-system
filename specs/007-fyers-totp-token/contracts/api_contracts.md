# Interface Contracts: Sprint 2 – Core TOTP Token Generation Function

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/spec.md)
**Created**: 2026-07-20

---

## 1. Python Library Interface (Function Signature)

The function is exposed from the module `fyers_token` as:

```python
def generate_fyers_access_token() -> str:
    """
    Generates a valid Fyers API v3 access token using TOTP.

    Reads configuration from environment variables:
      - FYERS_CLIENT_ID
      - FYERS_APP_ID
      - FYERS_APP_SECRET
      - FYERS_TOTP_SECRET
      - FYERS_PIN

    Returns:
        str: The generated Fyers API v3 access token.

    Raises:
        FyersConfigError: If any required environment variable is missing or empty.
        FyersAuthError: If login, TOTP verification, or PIN verification fails.
        FyersConnectionError: If API requests fail due to network/server errors.
    """
```

### Exception Class Hierarchy
The module will define three custom exceptions mapping to domain-specific failures:

```python
class FyersAuthError(Exception):
    """Raised when authentication credentials or TOTP fail verification."""
    pass

class FyersConfigError(Exception):
    """Raised when environment variables are missing or invalid."""
    pass

class FyersConnectionError(Exception):
    """Raised when connections to Fyers API endpoints fail or timeout."""
    pass
```

---

## 2. CLI Interface

To satisfy the **CLI Interface** principle of the Project Constitution, the module `fyers_token.py` can be executed directly from the command line.

### Command Execution
```bash
python fyers_token.py
```

### Outputs
- **On Success**: The script writes only the clean, raw access token string to `stdout` and exits with code `0`.
- **On Error**: The script writes a descriptive error message to `stderr` and exits with a non-zero exit code (e.g., `1`).

### Example Success Output
```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0s...
```

### Example Error Output
```text
Error: FyersAuthError - PIN verification failed: Invalid PIN.
```
