# Implementation Plan: Sprint 2 – Core TOTP Token Generation Function

**Branch**: `007-fyers-totp-token` | **Date**: 2026-07-20 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/spec.md)
**Input**: Feature specification from `/specs/007-fyers-totp-token/spec.md`

---

## ## Summary / Overview

This plan defines the step-by-step implementation of the core TOTP-based Fyers login automation. We will create a reusable Python module `fyers_token.py` containing the `generate_fyers_access_token()` function. The function will generate a valid Fyers access token using pure HTTP API calls (the Fyers Vagator login APIs) and the `pyotp` library, entirely bypassing the browser login interface (no Playwright/Selenium).

---

## ## Technical Context

- **Language/Version**: Python 3.11  
- **Primary Dependencies**: `requests` (v2.31.0+), `pyotp` (v2.9.0+), `fyers-apiv3` (v3.1.12+)  
- **Storage**: N/A (transient token generation)  
- **Testing**: `pytest`  
- **Target Platform**: Windows / Linux server  
- **Project Type**: Library / CLI  
- **Performance Goals**: Successful token generation in < 5 seconds  
- **Constraints**: Pure API-based flow, no browser automation, credentials read exclusively from environment variables.
- **Scale/Scope**: Executed once daily by background tasks or schedulers.

---

## ## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status | Verification Method / Notes |
|-----------|-------|--------|-----------------------------|
| **I. Library-First** | Standalone module? | **PASS** | `fyers_token.py` will be a self-contained module containing the business logic and custom exceptions. |
| **II. CLI Interface** | Direct execution supported? | **PASS** | `fyers_token.py` will include an `if __name__ == "__main__":` block to write the access token to `stdout` and errors to `stderr`. |
| **III. Test-First** | Unit & integration tests defined? | **PASS** | Tests will be written in `tests/test_fyers_token.py` using mocked endpoints before/during implementation. |
| **IV. Integration Testing** | End-to-end integration scenario? | **PASS** | `quickstart.md` details how to run the E2E verification scenario. |
| **V. Observability** | Proper logging and error levels? | **PASS** | Uses standard `logging` at the `INFO` level for high-level steps; strictly prevents logging sensitive values. |

---

## ## Project Structure

The project structure for this feature is organized as follows:

### Documentation (this feature)
```text
specs/007-fyers-totp-token/
├── spec.md              # Feature Specification (with clarified requirements)
├── plan.md              # This Implementation Plan
├── research.md          # Phase 0 Research Notes (Vagator API analysis)
├── data-model.md        # Phase 1 Data Model (credential and token schemas)
├── quickstart.md        # Phase 1 Quickstart Validation Guide
└── contracts/
    └── api_contracts.md # Interface Contracts (function and CLI contract)
```

### Source Code
The files will be added directly to the repository root and standard folders:
```text
D:/Work_Space/trading-system/
├── fyers_token.py       # Core module containing generate_fyers_access_token() and CLI wrapper
└── tests/
    └── test_fyers_token.py # Pytest suite for unit testing and mocked responses
```

**Structure Decision**: Single project (root level). The core module is placed in the root directory for maximum reusability and ease of importing across backend services.

---

## ## Detailed Design & Function Specification

### 1. Function Design
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

### 2. Environment Variables Required
The function relies strictly on the following environment variables:
- `FYERS_CLIENT_ID`: Fyers User ID (e.g., `YJ08718`).
- `FYERS_APP_ID`: API App ID (e.g., `L9NY305RTW-100`).
- `FYERS_APP_SECRET`: API App Secret Key.
- `FYERS_TOTP_SECRET`: TOTP 2FA Secret Key (Base32 format).
- `FYERS_PIN`: 4-digit or 6-digit numeric login PIN.

### 3. Detailed Logic Flow
1. **Load Configuration**:
   - Retrieve env variables using `os.getenv()`.
   - Strip whitespace (`.strip()`).
   - If any variable is missing, raise `FyersConfigError`.
2. **Step 1: Request OTP**:
   - Send `POST` to `https://api-t2.fyers.in/vagator/v2/send_login_otp_v2`.
   - Payload: `{"fy_id": base64_encode(FYERS_CLIENT_ID), "app_id": "2"}`
   - Capture `request_key_1`.
3. **Step 2: Generate & Verify TOTP**:
   - Generate TOTP: `totp = pyotp.TOTP(FYERS_TOTP_SECRET).now()`.
   - Send `POST` to `https://api-t2.fyers.in/vagator/v2/verify_otp`.
   - Payload: `{"request_key": request_key_1, "otp": totp}`.
   - Capture `request_key_2`.
   - *Resiliency Handling*: If verification fails with a timing error, sleep until the start of the next 30-second TOTP window, generate a new TOTP, and try the sequence exactly once more.
4. **Step 3: Verify PIN**:
   - Send `POST` to `https://api-t2.fyers.in/vagator/v2/verify_pin_v2`.
   - Payload: `{"request_key": request_key_2, "identity_type": "pin", "identifier": base64_encode(FYERS_PIN)}`.
   - Capture temporary user `access_token` from `data.access_token`.
5. **Step 4: Request Auth Code**:
   - Send `GET` to `https://api-t1.fyers.in/api/v3/generate-authcode`.
   - Query Parameters: `client_id=FYERS_APP_ID`, `redirect_uri=redirect_uri`, `response_type=code`, `state=sample_state`.
   - Headers: `{"Authorization": f"Bearer {temp_token}"}`.
   - Disable redirects (`allow_redirects=False`).
   - Extract `auth_code` from the `Location` redirect header.
6. **Step 5: Exchange Auth Code for Final Token**:
   - Initialize Fyers SDK `SessionModel`.
   - Call `session.set_token(auth_code)` and `session.generate_token()`.
   - Return the final trading `access_token` string.

### 4. Error Handling Strategy
- Catch `requests.RequestException` and raise `FyersConnectionError`.
- Catch JSON parsing errors or API errors (where status `s` in response is not `"ok"`) and raise `FyersAuthError`.
- Use custom exceptions inheriting from standard `Exception` for precise diagnostics.

---

## ## Step-by-Step Implementation Plan

### Task 1: Environment Setup & Directory Check
- Verify that standard packages are available.
- Create dummy `.env` file for testing.

### Task 2: Create Core Exceptions (`fyers_token.py`)
- Implement `FyersAuthError`, `FyersConfigError`, and `FyersConnectionError`.

### Task 3: Implement Configuration Loader & Base64 Helpers
- Implement helper function to encode strings to Base64.
- Implement config loader that checks all 5 environment variables and strips whitespace.

### Task 4: Implement Step 1 & 2 (OTP and TOTP Verification)
- Implement `send_login_otp_v2` call.
- Integrate `pyotp.TOTP` generation.
- Implement `verify_otp` call.
- Integrate retry logic for TOTP window expiry.

### Task 5: Implement Step 3 & 4 (PIN and Auth Code Extraction)
- Implement `verify_pin_v2` call with Base64 PIN.
- Implement `generate-authcode` GET request with headers and parse the redirect `Location` header to retrieve `auth_code`.

### Task 6: Implement Step 5 (Token Exchange via SDK)
- Integrate Fyers V3 `SessionModel` to exchange the auth code for the final access token.

### Task 7: Implement CLI Interface Wrapper
- Add standard entry point block `if __name__ == "__main__":`.
- Use standard `sys.exit()` and printing to `stdout` / `stderr`.

---

## ## Testing Strategy

### 1. Mocked Unit Tests
Create unit tests in `tests/test_fyers_token.py` using Python's `unittest.mock` to mock all external API requests:
- **Test missing env variables**: Verify `FyersConfigError` is raised.
- **Test API connection failures**: Mock `requests.post` to throw exceptions, verify `FyersConnectionError` is raised.
- **Test OTP failure**: Mock `/send_login_otp_v2` to return error status, verify `FyersAuthError` is raised.
- **Test PIN failure**: Mock `/verify_pin_v2` to return invalid PIN error, verify `FyersAuthError` is raised.
- **Test TOTP retry logic**: Mock first OTP verification to fail and second to succeed; verify the retry is triggered and succeeds.

### 2. Live E2E Integration Test
Run the scripts against the real Fyers sandbox/endpoints using your `.env` credentials as detailed in [quickstart.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/quickstart.md).

---

## ## Definition of Done

- [ ] Reusable function `generate_fyers_access_token()` is created in `fyers_token.py`.
- [ ] CLI execution works, writing token to `stdout` and error details to `stderr`.
- [ ] All credentials are read from environment variables.
- [ ] Pytest suite `tests/test_fyers_token.py` passes with > 90% code coverage.
- [ ] No browser automation libraries (Selenium/Playwright) are used.
- [ ] E2E integration test successfully fetches a valid access token.

---

## ## Complexity Tracking

*No violations of Project Constitution are present. Stands fully compliant.*
