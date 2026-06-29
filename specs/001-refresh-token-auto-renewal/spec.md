# Feature Specification: Fyers Refresh Token Auto-Renewal

**Feature Directory**: `specs/001-refresh-token-auto-renewal`

**Created**: 2026-06-27

**Status**: Draft

## 1. Feature Summary
Currently, the user manually generates and pastes a new FYERS access token every day via the UI. This feature replaces the daily manual workflow with an automated refresh flow utilizing a 15-day refresh token. It will automatically call FYERS to get a new access token every morning, and display a visual warning in the frontend when the refresh token itself is nearing expiry.

## 2. User Stories

### User Story 1 - Providing Refresh Credentials (Priority: P1)
As a user, I want to input my FYERS refresh token securely so that the system can automatically generate access tokens.
**Why this priority**: Essential first step. Without the refresh token, automated renewals are impossible.
**Independent Test**: Can be fully tested by verifying the frontend accepts the token and the backend saves it properly to the database.
**Acceptance Scenarios**:
1. **Given** the user is on the Workstation or Paper Trading page, **When** they submit a valid refresh token, **Then** the refresh token is stored securely and the API responds successfully without logging the token.

### User Story 2 - Automated Daily Access Token Renewal (Priority: P1)
As a system, I want to automatically renew the FYERS access token every morning before the market opens, so that the trading engine is ready without user intervention.
**Why this priority**: Core value proposition. Removes the daily manual hassle.
**Independent Test**: Can be tested by manually triggering the `auto_token_refresh` job and verifying the access token is successfully updated.
**Acceptance Scenarios**:
1. **Given** a valid stored refresh token, **When** the scheduled job runs at 08:30 IST, **Then** the FYERS API is called and a new access token is generated and stored.
2. **Given** an invalid or expired refresh token, **When** the job runs, **Then** the engine is paused (`TOKEN_EXPIRED_PAUSED`), an error is logged, and a UI notification is sent.

### User Story 3 - Refresh Token Expiry Warning (Priority: P2)
As a user, I want to see a visual indicator of my refresh token's validity, so that I know exactly when I need to manually generate a new 15-day token.
**Why this priority**: Critical for continuous operation, but the system functions without the warning until day 15.
**Independent Test**: Can be tested by returning mocked expiry days in the status API and verifying the frontend badges/banners render correctly.
**Acceptance Scenarios**:
1. **Given** >5 days remaining, **When** viewing the UI, **Then** a green badge shows "Refresh Token Valid — X days left".
2. **Given** 3 to 5 days remaining, **When** viewing the UI, **Then** an amber badge shows "Expiring Soon — X days left".
3. **Given** <3 days remaining, **When** viewing the UI, **Then** a persistent, non-dismissable red badge and banner shows "Refresh Token Expiring in X days — Insert new token now".
4. **Given** the token is expired, **When** viewing the UI, **Then** a red banner shows "Refresh Token Expired — Auto-renewal disabled. Insert new token."

## 3. Functional Requirements

- **FR-001**: The UI MUST provide an input field for the refresh token in the Accounts section.
- **FR-002**: The system MUST store the refresh token alongside the access token and calculate its expiry as `created_at + 15 days`.
- **FR-003**: The FYERS PIN MUST be sourced from the `FYERS_PIN` environment config only, and NEVER stored in the database.
- **FR-004**: The system MUST NEVER expose the raw refresh token value in API responses, logs, or error messages.
- **FR-005**: An APScheduler job named `auto_token_refresh` MUST run automatically at 08:30 IST every Mon-Fri.
- **FR-006**: The auto-renewal job MUST use `httpx.AsyncClient` with a 30-second timeout directly in `fyers_service.py` to fetch a new access token, bypassing the FYERS SDK.
- **FR-007**: The HTTP request to FYERS MUST include an `appIdHash` computed as `SHA256(client_id + secret_key)`.
- **FR-008**: Upon successful renewal, the new access token MUST be saved and the old one deactivated (`is_active=False`).
- **FR-009**: On renewal failure (e.g., token expired), the engine MUST transition to `TOKEN_EXPIRED_PAUSED` and dispatch a frontend notification.
- **FR-010**: The `GET /fyers/token/status` API MUST return `refresh_token_days_remaining` and `refresh_token_status`.
- **FR-011**: The frontend MUST conditionally render inline banners/badges based on the `refresh_token_days_remaining` field without using `window.alert`.

## 4. Non-Functional Requirements
- **NFR-001 (Resilience)**: Missing `FYERS_PIN` or failed renewals MUST log an error and notify the UI, but MUST NOT crash the scheduler or market engine.
- **NFR-002 (Concurrency)**: The scheduler job MUST acquire a distributed lock named `auto_token_refresh` before execution.
- **NFR-003 (Performance)**: The scheduled HTTP call MUST not block the main asyncio event loop (use `httpx.AsyncClient` or `asyncio.to_thread`).
- **NFR-004 (Idempotency)**: Concurrent job triggers MUST execute safely using distributed locking.
- **NFR-005 (Security)**: The refresh token and PIN must not be leaked. Only standard JWT-like protections are applied.

## 5. Out of Scope
- Modifying the existing manual access-token-only flow (must remain intact).
- Auto-trading or triggering any orders upon token renewal.
- Implementing state management libraries in the frontend (use existing vanilla hooks).
- Polling for token status at intervals faster than 5 seconds.
- Using the `fyers-apiv3` SDK for the refresh token validation call.

## 6. Data Model Changes

**Table**: `fyers_tokens`
**New Columns**:
- `refresh_token`: `Text` (nullable).
- `refresh_token_expires_at`: `DateTime(timezone=True)` (nullable).
- `last_auto_renewal_at`: `DateTime(timezone=True)` (nullable).
- `last_auto_renewal_status`: `String(32)` (nullable, values: "success" | "failed").

*Migration Notes*: 
An Alembic migration is required. All new columns must be nullable without default constraints so existing data isn't broken. A working downgrade function must be included.

## 7. API Contract Changes

**POST `/fyers/token`**:
Accepts optional `refresh_token` string. No PIN field.

**GET `/fyers/token/status`**:
New Response Fields:
- `refresh_token_present`: `bool`
- `refresh_token_expires_at`: `datetime` (ISO 8601, AwareDatetime)
- `refresh_token_days_remaining`: `int`
- `refresh_token_status`: `"valid" | "expiring_soon" | "critical" | "expired"`
- `last_auto_renewal_at`: `datetime | null`
- `last_auto_renewal_status`: `"success" | "failed" | null`

*Security*: The raw `refresh_token` MUST NOT be in the response. All errors must follow `API-004`.

## 8. UI Changes
- Extend existing token UI in Workstation/Paper Trading pages.
- Add an input field for the refresh token.
- Add a visual badge/banner using rules:
  - `>5 days`: Green badge "Refresh Token Valid — X days left"
  - `3 to 5 days`: Amber badge "Expiring Soon — X days left"
  - `<3 days`: Persistent Red badge & banner "Refresh Token Expiring in X days — Insert new token now"
  - `expired`: Persistent Red banner "Refresh Token Expired — Auto-renewal disabled. Insert new token."
- Banners for critical and expired states must not be dismissable.
- No `window.alert` used anywhere.

## 9. Scheduler Changes
- **Job Name**: `auto_token_refresh`
- **Trigger**: `CronTrigger(hour=8, minute=30, timezone="Asia/Kolkata", day_of_week="mon-fri")`
- **Lock**: Acquires distributed lock `"auto_token_refresh"`.
- **Job Settings**: `maxinstances=1`, `coalesce=True`, `misfire_grace_time=300`.
- **Logging**: 
  - Start: `INFO job_id, trigger_time, lock_acquired`
  - End: `INFO job_id, duration_ms, status`

## 10. Security Constraints
- **SEC-003**: The raw refresh token is sensitive and must not be logged, sent to the frontend, or output in exception stack traces.
- **SEC-004**: `FYERS_PIN` and `FYERS_CLIENT_ID` / `FYERS_SECRET_KEY` must come exclusively from environment variables.

## 11. Testing Requirements

**Unit Tests (`backend/tests/unit/`)**:
- Validate `refresh_token_days_remaining` and `refresh_token_status` math for all edge cases (normal, 0, negative).
- Validate `appIdHash` SHA256 computation returns correct known output.
- Auto-renewal success path (mock httpx).
- Auto-renewal failure path (401 response).
- Auto-renewal failure path (missing `FYERS_PIN`).

**Integration Tests (`backend/tests/integration/`)**:
- Full auto-renewal flow: expired detected → refreshed → old deactivated, new active.
- Scheduler job runs, acquires lock, and logs correctly.
- Idempotency: duplicate trigger runs once.
- Missing refresh token transitions engine to `TOKEN_EXPIRED_PAUSED`.

**API Contract Tests (`backend/tests/api/`)**:
- `POST /fyers/token` accepts new fields without breaking legacy flow.
- `GET /fyers/token/status` returns correct AwareDatetime and new fields.
- Raw refresh token never returned.

**Frontend Tests (`frontend/tests/components/`)**:
- Badge renders matching `refresh_token_days_remaining` (Green/Amber/Red).
- Banner is persistent for critical/expired states.
- `window.alert` is strictly absent.

## 12. Constitution Rules Referenced
ARCH-001, ARCH-003, ARCH-005, ARCH-006, ARCH-007, ARCH-008
API-002, API-003, API-004, API-007, API-010
DB-001, DB-002, DB-003, DB-006, DB-007
FE-001, FE-002, FE-005, FE-006, FE-007, FE-009, FE-010
JOB-001, JOB-002, JOB-005, JOB-006, JOB-007, JOB-008
SEC-001, SEC-003, SEC-004
TRADE-014
TEST-001, TEST-002, TEST-003, TEST-004

## 13. Open Questions

- DECIDED: The refresh token will be encrypted at rest using Python Fernet symmetric encryption (from the cryptography library). The encryption key is stored as the FYERS_TOKEN_ENCRYPTION_KEY environment variable. encrypt_token() and decrypt_token() utility functions live in fyers_service.py or utils/crypto.py. The raw refresh token is never stored in plain text in the database.
