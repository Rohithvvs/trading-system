# Implementation Plan: Sprint 5 – Internal API Endpoint

**Branch**: `010-fyers-internal-api` | **Date**: 2026-07-21 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/spec.md)
**Input**: Feature specification from [spec.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/spec.md)

## Summary

Expose an internal, protected HTTP endpoint `POST /internal/refresh-fyers-token` that triggers daily Fyers access token generation and persists the outcome in the database. The endpoint will reuse the existing `generate_and_persist_fyers_token()` service from Sprint 4 (which handles headless TOTP login and up to 3 generation retries) and will protect access using the standard system `SCHEDULER_SECRET` header validation.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, SQLAlchemy (async), PyJWT  
**Storage**: SQLite (local dev), PostgreSQL (Neon production)  
**Testing**: pytest, pytest-asyncio  
**Target Platform**: Linux server (cloud deployment)  
**Project Type**: web-service  
**Performance Goals**: <15 seconds total execution time (to allow broker API connections and 3 login retries)  
**Constraints**: Protected by `X-Scheduler-Secret` header; must return exact JSON response schemas; no raw credentials or tokens leaked.  
**Scale/Scope**: Executed automatically once per day via a cron job/scheduler.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate / Principle | Status | Compliance Details / Rationale |
|---|---|---|
| Safe Secrets Rule (CONVENTIONS) | **PASSED** | Resolves `SCHEDULER_SECRET` dynamically from the environment. No keys or secrets are hardcoded. |
| Async-First Standard (CONVENTIONS) | **PASSED** | The route handler is fully async (`async def`) and database calls use async session dependencies. |
| Mandatory Testing Rule (CONVENTIONS) | **PASSED** | Plan includes writing backend integration tests checking authorization, success, and error paths. |
| No Raw Errors (CONVENTIONS) | **PASSED** | Endpoint catches all exception types, logs them safely, and returns clean HTTP responses matching the contract. |

## Project Structure

### Documentation (this feature)

```text
specs/010-fyers-internal-api/
├── plan.md              # This file
├── research.md          # Design decisions and security rationale
├── data-model.md        # DB schema reference and state transition diagram
├── quickstart.md        # Local cURL and testing validation guide
└── contracts/
    └── api_contracts.md # HTTP endpoint request/response schema specification
```

### Source Code

```text
backend/app/
├── main.py              # Application entrypoint registering route routers
├── routes/
│   ├── __init__.py      # Router assembly mapping API paths
│   └── token.py         # Route logic containing new /internal/refresh-fyers-token handler
└── services/
    └── token_service.py # Existing token generation and db persistence layer

backend/tests/
└── integration/
    └── test_token_refresh_route.py  # New route handler integration tests
```

**Structure Decision**: Add the new `/internal` route to `backend/app/routes/token.py` via a new secondary `APIRouter()` named `internal_router`. Register `internal_router` in `backend/app/main.py` directly (or in `routes/__init__.py`) to support the root `/internal` namespace without the primary `/api/token` prefix.

## Complexity Tracking

*No constitution violations detected; complexity tracking is empty.*
