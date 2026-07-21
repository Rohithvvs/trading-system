# API Contract: Sprint 5 – Internal API Endpoint

## Overview
This document specifies the HTTP request/response interface contract for the protected internal API endpoint.

## Endpoint Specification

### Refresh Fyers Token Endpoint
* **URL**: `/internal/refresh-fyers-token`
* **HTTP Method**: `POST`
* **Content-Type**: `application/json`

### Security Authentication
The endpoint requires header-based token authentication matching the existing system scheduler credentials.

| Header | Type | Description |
|---|---|---|
| `X-Scheduler-Secret` | String (Required) | Secret key matching the system's `SCHEDULER_SECRET` configuration. |

---

## Response Schemas

### 1. Successful Execution (200 OK)
Returned when the Fyers token is successfully generated and persisted in the database.

* **HTTP Status**: `200 OK`
* **Response Body**:
```json
{
  "status": "success",
  "message": "Access token generated and saved successfully"
}
```

---

### 2. Execution Failure (500 Internal Server Error)
Returned when token generation fails after all retries or if database persistence fails.

* **HTTP Status**: `500 Internal Server Error`
* **Response Body**:
```json
{
  "status": "error",
  "message": "Failed to generate access token after retries"
}
```

---

### 3. Authentication Failures (401 / 403)
Returned when the incoming request fails security validation.

#### A. Missing Header
* **HTTP Status**: `401 Unauthorized`
* **Response Body**:
```json
{
  "detail": "Unauthorized"
}
```

#### B. Invalid Key
* **HTTP Status**: `403 Forbidden`
* **Response Body**:
```json
{
  "detail": "Forbidden"
}
```
