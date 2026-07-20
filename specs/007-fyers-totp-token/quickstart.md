# Quickstart Validation Guide: Sprint 2 – Core TOTP Token Generation Function

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/spec.md)
**Created**: 2026-07-20

This guide documents runnable scenarios to validate the implementation of the `generate_fyers_access_token()` function and the companion CLI interface.

---

## Prerequisites

1. Active Python environment.
2. Required packages installed:
   ```bash
   pip install requests pyotp fyers-apiv3 python-dotenv
   ```
3. Prepare a local `.env` file in the project root with valid credentials:
   ```env
   FYERS_CLIENT_ID="your_fyers_id"
   FYERS_APP_ID="your_app_id"
   FYERS_APP_SECRET="your_app_secret"
   FYERS_TOTP_SECRET="your_totp_secret"
   FYERS_PIN="your_pin"
   ```

---

## Validation Scenario 1: Python Function E2E Success

### Execution Steps
Run the following verification snippet in Python:

```python
import os
from dotenv import load_dotenv
from fyers_token import generate_fyers_access_token

load_dotenv()

try:
    token = generate_fyers_access_token()
    print("SUCCESS: Token retrieved successfully!")
    print(f"Token length: {len(token)} characters.")
    print(f"Token starts with: {token[:20]}...")
except Exception as e:
    print(f"FAILURE: An error occurred: {e}")
```

### Expected Outcome
- Output displays: `SUCCESS: Token retrieved successfully!`
- Token length is > 100 characters.
- No exceptions are raised.

---

## Validation Scenario 2: CLI Wrapper E2E Success

### Execution Steps
Execute the script directly from your terminal:

```powershell
# On Windows PowerShell, ensure env variables from .env are loaded first
# (or pass them in directly before execution)
$env:FYERS_CLIENT_ID="your_fyers_id"
$env:FYERS_APP_ID="your_app_id"
$env:FYERS_APP_SECRET="your_app_secret"
$env:FYERS_TOTP_SECRET="your_totp_secret"
$env:FYERS_PIN="your_pin"

python fyers_token.py
```

### Expected Outcome
- The command outputs only the raw, complete access token string.
- The command exits with status code `0`.

---

## Validation Scenario 3: Validation Error on Missing Config

### Execution Steps
Unset one of the required environment variables and run the script:

```powershell
$env:FYERS_TOTP_SECRET=""
python fyers_token.py
```

### Expected Outcome
- Output is written to `stderr` indicating: `Error: FyersConfigError - Missing required environment variable: FYERS_TOTP_SECRET`
- The command exits with a non-zero exit code (e.g., `1`).
