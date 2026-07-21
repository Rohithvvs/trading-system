# Feature Specification: Sprint 5 – Internal API Endpoint

**Feature Branch**: `010-fyers-internal-api`  
**Created**: 2026-07-21  
**Status**: Draft  
**Input**: User description: "Generate a detailed technical specification for Sprint 5 of the Fyers Access Token Automation project. Objective: Create a protected internal API endpoint that triggers the full token generation and storage flow."

## Overview

Expose the automated Fyers access token generation and database storage system via a protected internal API endpoint. This endpoint will allow an external scheduler (such as a local cron job) to trigger the token refresh process daily, ensuring a fresh access token is always available for trading operations. The endpoint must be restricted from public access to prevent abuse or unauthorized execution of the token refresh logic.

## Clarifications

### Session 2026-07-21

- Q: Which environment variable and HTTP header name should protect `POST /internal/refresh-fyers-token`? → A: Reuse existing `SCHEDULER_SECRET` (header `X-Scheduler-Secret`).
- Q: Where should the code for the new `POST /internal/refresh-fyers-token` route be defined? → A: Define it in the existing `backend/app/routes/token.py` file using a secondary/unprefixed router.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Token Refresh Trigger (Priority: P1)

As an automated cron job or system scheduler, I want to call an internal API endpoint so that the system runs the token generation flow and persists the newly generated token to the database.

**Why this priority**: This is the core functionality required to enable hands-off, automated daily token updates. Without this trigger, token generation remains manual.

**Independent Test**: Execute a POST request to `/internal/refresh-fyers-token` with the correct internal authorization header, and verify that a fresh token is generated, stored in the database, and a success JSON message is returned.

**Acceptance Scenarios**:

1. **Given** the Fyers login credentials and TOTP parameters are configured, **When** a valid authorized request is made to `POST /internal/refresh-fyers-token`, **Then** the system calls the token generation function, successfully retrieves a token, saves it to the database, and returns `{"status": "success", "message": "Access token generated and saved successfully"}` with HTTP status 200.
2. **Given** the Fyers login credentials or network connection fails, **When** a valid authorized request is made to `POST /internal/refresh-fyers-token`, **Then** the system retries the token generation (up to 3 attempts), saves the failure status and error log to the database, and returns `{"status": "error", "message": "Failed to generate access token after retries"}` with HTTP status 500.

---

### User Story 2 - Endpoint Protection and Access Control (Priority: P2)

As a system administrator, I want to restrict access to the internal token refresh endpoint so that public users or unauthorized external entities cannot trigger token generation or database write operations.

**Why this priority**: Unprotected endpoints expose the system to denial-of-service attacks, rate-limiting by the broker, and unauthorized database modifications.

**Independent Test**: Execute a request to `/internal/refresh-fyers-token` without the secret header or with an invalid key, and verify that the request is rejected with an HTTP 401/403 error and no token generation logic is run.

**Acceptance Scenarios**:

1. **Given** the internal endpoint is active, **When** a request is made to `POST /internal/refresh-fyers-token` with a missing or empty authentication key in the headers, **Then** the system rejects the request, returning an HTTP 401 Unauthorized status.
2. **Given** the internal endpoint is active, **When** a request is made to `POST /internal/refresh-fyers-token` with an incorrect or invalid key in the headers, **Then** the system rejects the request, returning an HTTP 403 Forbidden status.

---

### Edge Cases

- **Broker API Downtime**: If the broker API is completely down or returns persistent errors during all retry attempts, the system must write the error message to the database, transition the status to "failed", and return a structured JSON error response.
- **Database Connection Failure**: If a token is successfully generated but the database is unreachable to save it, the system must log the critical failure, return an HTTP 500 error response, and ensure the generated token is discarded or flagged for manual review.
- **Concurrent Execution**: If multiple requests are sent to the endpoint simultaneously, the system should serialize or handle them gracefully without causing duplicate token generation attempts or database race conditions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose an internal HTTP endpoint at path `/internal/refresh-fyers-token` accepting only `POST` requests.
- **FR-002**: The endpoint MUST invoke the existing token generation function, reusing the retry and TOTP login mechanism from Sprint 3.
- **FR-003**: The endpoint MUST persist the token generation result (success token value or failure error details) to the database, utilizing the storage logic from Sprint 4.
- **FR-004**: The endpoint MUST validate the presence and correctness of an internal secret key in the request headers using the `X-Scheduler-Secret` header.
- **FR-005**: The internal secret key MUST NOT be hardcoded and must be resolved from the `SCHEDULER_SECRET` environment variable.
- **FR-006**: On successful generation and database storage, the endpoint MUST return a 200 OK HTTP status and the JSON body: `{"status": "success", "message": "Access token generated and saved successfully"}`.
- **FR-007**: On failure to generate the token after all retries, the endpoint MUST return a 500 Internal Server Error HTTP status and the JSON body: `{"status": "error", "message": "Failed to generate access token after retries"}`.

### Endpoint Interface Contract

- **HTTP Method**: `POST`
- **Path**: `/internal/refresh-fyers-token`
- **Request Headers**:
  - `Content-Type`: `application/json`
  - `X-Scheduler-Secret`: `<scheduler_secret>`
- **Request Body**: Empty
- **Expected Responses**:
  - **Success (200 OK)**:
    ```json
    {
      "status": "success",
      "message": "Access token generated and saved successfully"
    }
    ```
  - **Failure (500 Internal Server Error)**:
    ```json
    {
      "status": "error",
      "message": "Failed to generate access token after retries"
    }
    ```
  - **Unauthorized (401/403 Unauthorized/Forbidden)**:
    ```json
    {
      "status": "error",
      "message": "Unauthorized access"
    }
    ```

### Integration Requirements

- **Existing Logic Reuse**: The endpoint implementation must import and call the existing function `generate_fyers_access_token()` directly. It must not duplicate the authentication logic, login sequences, or retry configurations.
- **Route Definition**: The route code MUST be placed in `backend/app/routes/token.py` using a secondary, unprefixed `APIRouter` to handle the `/internal` path namespace.
- **Database Storage**: The endpoint must call the repository/service layer created in Sprint 4 to update the token record. The database record fields (`token`, `status`, `updated_at`, `last_error`) must be properly set based on the function's return value or exceptions raised.

### Key Entities *(include if feature involves data)*

- **Fyers Access Token**: The database entity representing the broker access token.
  - *Attributes*: `token` (string), `status` (success/failed), `updated_at` (timestamp), `last_error` (string/null).
- **Internal API Credentials**: Configuration settings defining the valid secret key for internal endpoint access.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of unauthorized requests are rejected without invoking the broker login process or database writes.
- **SC-002**: Authorized requests returning success persist the new token in the database and return the JSON response in under 15 seconds.
- **SC-003**: 100% of token generation failures (after 3 retries) are recorded in the database and return a 500 error response.

## Assumptions

- An external cron job or task scheduler will be set up independently to trigger this endpoint; the cron job setup itself is out of scope.
- The hosting environment allows configuring environment variables (`FYERS_API_KEY`, `FYERS_SECRET_KEY`, `SCHEDULER_SECRET`, etc.) securely.
- The existing `generate_fyers_access_token()` function raises a catchable exception or returns a clear indicator on ultimate failure.

## Out of Scope

- Setting up or configuring the OS cron table or task scheduler daemon.
- A user interface or frontend dashboard to trigger or monitor the token refresh.
- Refreshing tokens for brokers other than Fyers.
- Automated email or SMS alerts on token generation failure (which can be handled by a separate alerting system).
