# Feature Specification: Sprint 2 – Core TOTP Token Generation Function

**Feature Branch**: `007-fyers-totp-token`  
**Created**: 2026-07-20  
**Status**: Draft  
**Input**: User description: "Generate a detailed technical specification for Sprint 2 of the Fyers Access Token Automation project. Sprint Name: Sprint 2 – Core TOTP Token Generation Function. Objective of this Sprint: Create a reusable Python function that can generate a valid Fyers access token using TOTP. Pure API-based approach. No browser automation (Playwright/Selenium) is allowed."

## Clarifications

### Session 2026-07-20

- Q: How should the function log progress or diagnostic messages given that it handles sensitive credentials? → A: High-level flow logging (INFO) using Python's standard logging library, ensuring secrets are never logged.
- Q: How should the function handle potential TOTP verification failures due to timing/window expiry? → A: Automatic retry on OTP expiry. If the OTP verification fails, wait for the next 30-second TOTP window, generate a fresh TOTP, and try the login sequence exactly once more before raising FyersAuthError.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Headless Token Generation via Environment Variables (Priority: P1)

As an automated background scheduler (cron job), I want to programmatically generate a fresh Fyers access token using TOTP and API credentials without requiring a browser, so that the trading system has active, authenticated access to Fyers API endpoints every morning.

**Why this priority**: This is the core MVP functionality of this sprint. Without a reliable headless token generation method, daily automated trading operations cannot run.

**Independent Test**:
Can be fully verified by executing a test script that imports `fyers_token.py`, sets valid environment variables, runs `generate_fyers_access_token()`, and asserts that a valid JWT token string is returned without invoking any browser automation.

**Acceptance Scenarios**:

1. **Given** valid Fyers credentials and TOTP secret configured in environment variables, **When** `generate_fyers_access_token()` is called, **Then** it generates the current 6-digit TOTP code, executes the API-based login flow, and returns a valid Fyers API v3 access token string.
2. **Given** missing configuration for any required environment variable (e.g., `FYERS_TOTP_SECRET` is unset), **When** `generate_fyers_access_token()` is called, **Then** it immediately raises a configuration exception before making any API requests, identifying the missing parameter.

---

### User Story 2 - Error Handling and Fault Diagnostics (Priority: P2)

As a system administrator, I want descriptive exception messages and logging output when token generation fails, so that I can diagnose and correct authentication issues (like invalid credentials, expired OTPs, or API downtime) quickly.

**Why this priority**: Headless authentication processes run unattended. Proper error reporting is necessary to trigger alerts and prevent silent system failures.

**Independent Test**:
Can be verified by calling the function with intentionally malformed inputs (e.g., incorrect base32 secret, expired TOTP, or incorrect PIN) and asserting that specific, descriptive exceptions (e.g., `FyersAuthError`) are raised.

**Acceptance Scenarios**:

1. **Given** an invalid `FYERS_PIN` configured in environment variables, **When** `generate_fyers_access_token()` is called, **Then** the function raises a `FyersAuthError` stating that PIN verification failed.
2. **Given** an invalid or expired `FYERS_TOTP_SECRET` that generates out-of-sync OTPs, **When** `generate_fyers_access_token()` is called, **Then** the function raises a `FyersAuthError` stating that OTP verification failed.
3. **Given** a network failure or HTTP error when reaching Fyers API endpoints, **When** `generate_fyers_access_token()` is called, **Then** the function raises a `FyersConnectionError` wrapping the underlying request exception.

---

### Edge Cases

- **OTP Window Boundaries**: If a TOTP is generated in the final seconds of a 30-second window, it might expire before the API endpoint validates it.
  * *Handling*: The function automatically retries the verification once in the next TOTP window if validation fails, minimizing timing-related failures.
- **Fyers System Maintenance / Downtime**: The Fyers authentication servers may be unreachable or return 5xx errors during off-market hours.
  * *Handling*: The function must fail fast by raising a clean `FyersConnectionError` with status code details rather than hanging or failing with unhandled exceptions.
- **Malformed / Whitespace Environment Variables**: Environment variables might contain copy-paste anomalies like leading/trailing spaces or newline characters.
  * *Handling*: The function must trim whitespace from environment variables before encoding or sending them to Fyers API endpoints.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST implement the core token generation logic in a standalone file named `fyers_token.py`.
- **FR-002**: The module MUST expose a public function named `generate_fyers_access_token()`.
- **FR-003**: The function MUST read all credentials ONLY from environment variables:
  - `FYERS_CLIENT_ID` (User ID / Client ID, e.g., `YJ08718`)
  - `FYERS_APP_ID` (API App ID / Client ID, e.g., `L9NY305RTW-100`)
  - `FYERS_APP_SECRET` (App Secret Key)
  - `FYERS_TOTP_SECRET` (TOTP 2FA Secret Key)
  - `FYERS_PIN` (4-digit numeric login PIN)
- **FR-004**: No sensitive values or credentials MUST be hardcoded in the codebase.
- **FR-005**: The function MUST generate a 6-digit TOTP code programmatically using the `pyotp` library from `FYERS_TOTP_SECRET`.
- **FR-006**: The authentication flow MUST be executed purely through HTTP API calls using the `requests` library.
- **FR-007**: The function MUST return the final Fyers API v3 access token as a string on successful login.
- **FR-008**: The function MUST raise clear, domain-specific Python exceptions (e.g., `FyersConfigError`, `FyersAuthError`, `FyersConnectionError`) with detailed error messages if any step fails.
- **FR-009**: The function MUST use Python's standard `logging` library to log high-level progress steps (e.g., requesting OTP, verifying TOTP, verifying PIN, token generated) at the `INFO` level, and MUST NEVER log any sensitive values such as credentials, OTP codes, PINs, or access tokens.
- **FR-010**: The function MUST implement an automatic retry mechanism for TOTP verification failure. If verification fails, it must wait for the start of the next 30-second TOTP window, generate a fresh TOTP, and retry the login flow exactly once before raising a `FyersAuthError`.

### Technical Requirements & Detailed Design

#### Function Signature
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
        FyersConfigError: If any required environment variable is missing.
        FyersAuthError: If login, TOTP verification, or PIN verification fails.
        FyersConnectionError: If API requests fail due to network/server errors.
    """
```

#### Step-by-Step Logic
1. **Load Config & Validate**:
   - Fetch the 5 environment variables.
   - Clean whitespace (use `.strip()`).
   - If any variable is missing or empty, raise `FyersConfigError` specifying the missing variable.
   - Resolve redirect URI (default to `https://trade.fyers.in/api-login/redirect-uri/index.html` unless overridden by `FYERS_REDIRECT_URI` env variable).

2. **Step 1: Request OTP**:
   - Endpoint: `https://api-t2.fyers.in/vagator/v2/send_login_otp_v2`
   - Method: POST
   - Payload:
     ```json
     {
       "fy_id": base64_encode(FYERS_CLIENT_ID),
       "app_id": "2"
     }
     ```
   - Headers: Mimic standard browser `User-Agent` to prevent rate-limit blocks.
   - Result: Capture `request_key` from response JSON. If response status `s` is not `'ok'`, raise `FyersAuthError`.

3. **Step 2: Verify TOTP**:
   - Generate TOTP: `totp = pyotp.TOTP(FYERS_TOTP_SECRET).now()`
   - Endpoint: `https://api-t2.fyers.in/vagator/v2/verify_otp`
   - Method: POST
   - Payload:
     ```json
     {
       "request_key": request_key_from_step_1,
       "otp": totp
     }
     ```
   - Result: Capture new `request_key` from response JSON. If response status `s` is not `'ok'`, raise `FyersAuthError`.

4. **Step 3: Verify PIN**:
   - Endpoint: `https://api-t2.fyers.in/vagator/v2/verify_pin_v2`
   - Method: POST
   - Payload:
     ```json
     {
       "request_key": request_key_from_step_2,
       "identity_type": "pin",
       "identifier": base64_encode(FYERS_PIN)
     }
     ```
   - Result: Capture temporary user access token from response JSON (`data.access_token`). If response status `s` is not `'ok'`, raise `FyersAuthError`.

5. **Step 4: Request Authorization Code**:
   - Endpoint: `https://api-t1.fyers.in/api/v3/generate-authcode`
   - Method: GET
   - Query Parameters:
     - `client_id`: `FYERS_APP_ID`
     - `redirect_uri`: redirect_uri
     - `response_type`: `"code"`
     - `state`: `"sample_state"`
   - Headers:
     ```
     Authorization: Bearer <temp_access_token>
     ```
   - Request Settings: `allow_redirects=False`
   - Result: Capture the `Location` header from the 302/307 redirect response. Parse this URL using `urllib.parse` to extract the `auth_code` query parameter. If `auth_code` is missing, raise `FyersAuthError`.

6. **Step 5: Exchange Authorization Code for Final Access Token**:
   - Initialize Fyers SDK `SessionModel`:
     ```python
     from fyers_apiv3 import fyersModel
     session = fyersModel.SessionModel(
         client_id=FYERS_APP_ID,
         secret_key=FYERS_APP_SECRET,
         redirect_uri=redirect_uri,
         response_type="code",
         grant_type="authorization_code"
     )
     ```
   - Execute:
     ```python
     session.set_token(auth_code)
     response = session.generate_token()
     ```
   - Result: Validate response status. Return `response["access_token"]` string. If response status is not successful, raise `FyersAuthError`.

---

### Key Entities *(Transient Data Objects)*

- **FyersCredentials**: Transitory config structure grouping `client_id`, `app_id`, `app_secret`, `totp_secret`, and `pin`.
- **FyersAuthResponse**: The response payload structures from `/send_login_otp_v2`, `/verify_otp`, and `/verify_pin_v2` containing `request_key` and temporary tokens.
- **FyersAccessToken**: The final token payload returned by the Fyers API (contains `access_token`, expiry, token type).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful executions return a valid Fyers access token string in under 5 seconds (excluding network latency variations).
- **SC-002**: 100% of executions with missing environment variables fail within 100 milliseconds with a `FyersConfigError`.
- **SC-003**: 100% of executions with invalid credentials (incorrect PIN, incorrect TOTP key) raise a `FyersAuthError` indicating validation failure.
- **SC-004**: No browser window or browser automation processes (e.g., Chrome/Chromium, Playwright, Selenium drivers) are launched during execution.

---

## Assumptions

- **System Compatibility**: The system has standard Python 3.8+ runtime with access to external PyPI repositories for installing `requests`, `pyotp`, and `fyers-apiv3`.
- **Active 2FA**: The Fyers account has "External 2FA TOTP" enabled, and the generated Base32 TOTP secret is active and correct.
- **Network Permissions**: The host environment running this script has outward HTTPS access to `api.fyers.in` and `api-t1.fyers.in`.

---

## Out of Scope

- **Browser Automation**: The use of Playwright, Selenium, Puppeteer, or any other headless browser automation technology is strictly out of scope.
- **Access Token Persistence**: Writing the token to a database (`fyers_tokens` table) or files is out of scope for this function. This function only generates and returns the token string; saving it to DB is handled by downstream consumer services.
- **Automatic Token Rotation Schedule**: Setting up a cron job or background worker to run this function periodically is out of scope for this sprint.
