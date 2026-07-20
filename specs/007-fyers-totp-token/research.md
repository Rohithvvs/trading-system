# Research Notes: Sprint 2 – Core TOTP Token Generation Function

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/spec.md)
**Created**: 2026-07-20

---

## 1. Authentication Endpoints & Flow Research

### Decision
Use Fyers' internal authentication endpoints ("Vagator" API) via the standard Python `requests` library to complete the headless login sequence, and then use the official `fyers-apiv3` SDK for the final token exchange.

- **Vagator API URL**: `https://api-t2.fyers.in/vagator/v2`
- **Official API URL**: `https://api-t1.fyers.in/api/v3`

### Rationale
Headless login (without browser automation) requires mimicking the step-by-step API calls performed by the Fyers web portal during manual user login. The workflow consists of:
1. **POST** `/send_login_otp_v2`: Requests an OTP/TOTP request key by sending the Base64-encoded Fyers User ID.
2. **POST** `/verify_otp`: Submits the generated TOTP code using the previous request key to get a new request key.
3. **POST** `/verify_pin_v2`: Validates the Base64-encoded 4-digit PIN using the second request key to obtain a temporary user access token.
4. **GET** `/generate-authcode`: Obtains the OAuth2 authorization code by sending the temporary user access token as a Bearer authorization header.
5. **SDK call** `generate_token()`: Passes the authorization code to the official Fyers `SessionModel` to generate the final trading access token.

This API-based flow meets the constraint of zero browser automation (no Selenium/Playwright) and is highly efficient (completing in < 2 seconds).

### Alternatives Considered
- **Playwright/Selenium Browser Automation**: Rejected due to explicit user constraints and high resource footprint. Browser automation is also fragile when running on headless servers.
- **Direct App ID Login**: Fyers does not support direct credentials-to-token authentication for private API keys; it mandates user interaction or interactive redirect flows, making the Vagator endpoint simulation necessary.

---

## 2. TOTP Generation & Time Synchronization

### Decision
Use the Python standard `pyotp` library to generate the 6-digit TOTP code programmatically from the `FYERS_TOTP_SECRET` env variable.

### Rationale
- `pyotp` is the standard library in the Python ecosystem for generating RFC 6238 TOTP tokens.
- It calculates the TOTP based on standard Unix time intervals.

### Alternatives Considered
- **Manual TOTP Math / Custom Script**: Rejected. Re-implementing SHA1 HMAC-based TOTP generation is error-prone and insecure compared to using a well-vetted library like `pyotp`.

---

## 3. Resiliency & Timing Windows

### Decision
Implement a retry mechanism if TOTP verification fails. When a timing failure occurs, wait for the start of the next 30-second window, generate a fresh TOTP, and repeat the verification sequence once.

### Rationale
TOTP tokens rotate every 30 seconds. If a request is sent during the last 1–2 seconds of a window, network delay may cause it to arrive at the Fyers server after the token has expired, triggering a false-negative authentication failure. Waiting for the next window ensures that the retried token has a full 30-second validity period.

### Alternatives Considered
- **Proactive Time Check**: Checking the local system clock's seconds remainder before sending a request. Rejected because local clocks can drift relative to Fyers' servers, rendering local TTL estimates unreliable. Atomic retries are more robust.
