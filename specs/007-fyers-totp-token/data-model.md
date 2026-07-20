# Data Model: Sprint 2 – Core TOTP Token Generation Function

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/007-fyers-totp-token/spec.md)
**Created**: 2026-07-20

---

## 1. Transient Data Structure: FyersCredentials

Represents the configuration payload loaded from environment variables and validated before initiating authentication.

| Field Name | Type | Description | Validation Rules |
|------------|------|-------------|------------------|
| `client_id` | `str` | User login ID (e.g., `YJ08718`) | Cannot be empty, must be alphanumeric. |
| `app_id` | `str` | API App Client ID (e.g., `L9NY305RTW-100`) | Cannot be empty, must match Fyers client ID format. |
| `app_secret` | `str` | API App Secret | Cannot be empty. |
| `totp_secret` | `str` | Base32 TOTP secret key | Must be a valid Base32 string (only letters A-Z, digits 2-7). |
| `pin` | `str` | 4-digit or 6-digit numeric login PIN | Must consist of digits only. |

---

## 2. Transient State: FyersAuthResponse

Holds the intermediate response details exchanged with the Vagator API endpoints.

| Field Name | Type | Description | Lifecycle State |
|------------|------|-------------|-----------------|
| `request_key_1` | `str` | Key returned by `send_login_otp_v2` | Active after Step 1. |
| `request_key_2` | `str` | Key returned by `verify_otp` | Active after Step 2. |
| `temp_token` | `str` | User JWT token returned by `verify_pin_v2` | Active after Step 3. Used as Bearer token. |
| `auth_code` | `str` | OAuth2 auth code returned by redirect | Active after Step 4. Exchanged for final token. |

---

## 3. Final Output Structure: FyersAccessToken

Represents the final, successful token schema returned to the caller and downstream services.

| Field Name | Type | Description | Format |
|------------|------|-------------|--------|
| `access_token` | `str` | The final API access token string | Standard Fyers JWT token. |
| `created_at` | `datetime` | Generation timestamp (UTC) | ISO 8601 string. |
| `expires_at` | `datetime` | Token expiration timestamp (UTC) | ISO 8601 string (typically 24 hours from creation). |
