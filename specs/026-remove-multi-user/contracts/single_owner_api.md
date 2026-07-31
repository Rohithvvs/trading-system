# Phase 1 Contracts: Single-Owner API Specification

**Feature Branch**: `026-remove-multi-user`  
**Date**: 2026-07-31  
**Updated**: 2026-07-31 (production cutover hardening)

---

## 1. Authentication Status

- **Global Policy**: End-user authentication is disabled (single trusted operator).
- **User JWT / cookies**: No `access_token` cookie or user `Authorization: Bearer <jwt>` is required for trading APIs.
- **Operator / diagnostics**: When `APP_ENV=production`, diagnostics and operator endpoints require `Authorization: Bearer <API_KEY>` (`API_KEY` env). Missing `API_KEY` in production is fail-closed (503).
- **Network**: Deploy only on a trusted network (private host, VPN, or reverse-proxy allowlist). The API is not multi-tenant safe on the public internet.

---

## 2. API Endpoint Classification

### Removed API Endpoints (`404 Not Found`)
- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/google`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/profile`
- `PUT /api/v1/auth/profile`
- `PATCH /api/v1/auth/profile`
- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{id}`

---

### Preserved API Endpoints (Direct Access — actual route prefixes)

#### Paper Trading API
- `GET /paper-trading/dashboard` → Primary paper desk under static owner context.
- `GET /paper-trading/account` / `GET /paper-trading/account/summary`
- `POST /paper-trading/orders` → Paper trade under static owner context.
- `GET /paper-trading/positions` → Open positions under static owner context.

#### Broker API
- `GET /api/broker-tokens` → FYERS broker credential metadata for static owner.
- `POST /api/broker-tokens` → Save FYERS credentials for static owner.
- `GET /fyers/auth/url` → FYERS OAuth login URL for broker token generation.
- `POST /fyers/auth/exchange` → Exchange FYERS OAuth code for access token.

#### Scanner & Recommendations API
- `GET /scanner/latest`
- Analysis routes under `/analysis/*` (and related screener routes as mounted).

#### Governance & System API
- `GET /api/v1/governance/routes`
- `GET /health`
- Diagnostics under `/api/v1/diagnostics/*` (operator `API_KEY` when configured / required in production)
