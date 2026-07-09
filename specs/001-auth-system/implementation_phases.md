# Implementation Phases

## Phase 1: Authentication Infrastructure & Database
- **Objective**: Setup the core database tables and security primitives (Argon2, Redis).
- **Files to Modify**: `backend/requirements.txt`, `backend/app/db/base.py`
- **Files to Create**: `backend/app/models/auth.py`, `backend/app/core/security.py`, `backend/app/core/redis.py`
- **Estimated Complexity**: Medium

## Phase 2: Core Authentication APIs
- **Objective**: Implement `/signup`, `/login`, and `/logout`.
- **Files to Modify**: `backend/app/main.py`
- **Files to Create**: `backend/app/routes/auth.py`, `backend/app/services/auth_service.py`, `backend/app/schemas/auth.py`
- **Estimated Complexity**: High

## Phase 3: Email Verification & Security Policies
- **Objective**: Implement OTP generation, email sending, and rate limiting / brute force protection.
- **Files to Create**: `backend/app/services/email_service.py`, `backend/app/middleware/rate_limit.py`
- **Estimated Complexity**: Medium

## Phase 4: PIN & Biometric APIs
- **Objective**: Implement `/pin/setup` and Biometric login fallback flows.
- **Estimated Complexity**: Medium

## Phase 5: Session Management
- **Objective**: Implement active sessions tracking, device fingerprinting, and session revocation.
- **Files to Create**: `backend/app/routes/sessions.py`, `backend/app/services/session_service.py`
- **Estimated Complexity**: Medium

## Phase 6: Frontend UI - Foundations
- **Objective**: Implement `AuthLayout`, `AuthInput`, `AuthButton`, and routing structure.
- **Files to Modify**: `frontend/src/App.tsx`
- **Files to Create**: `frontend/src/components/AuthLayout.tsx`, `frontend/src/components/AuthInput.tsx`
- **Estimated Complexity**: Low

## Phase 7: Frontend UI - Login & Signup
- **Objective**: Build the pixel-perfect `Login` and `Signup` pages mapping to `LOGIN_PAGE_VIEW.png`.
- **Files to Create**: `frontend/src/pages/Login.tsx`, `frontend/src/pages/Signup.tsx`
- **Estimated Complexity**: High

## Phase 8: Frontend UI - PIN & MFA
- **Objective**: Build `PinSetup` screen and OTP verification modals.
- **Estimated Complexity**: Medium

## Phase 9: Protected Routes & Middlewares Integration
- **Objective**: Wrap existing trading endpoints with the new Auth dependencies.
- **Files to Modify**: `backend/app/routes/trading.py` (and all other endpoints), `frontend/src/App.tsx` (ProtectedRoute wrappers).
- **Estimated Complexity**: High

## Phase 10: Testing & QA
- **Objective**: Achieve >90% coverage on authentication flows.
- **Files to Create**: `backend/app/tests/test_auth.py`, `frontend/src/tests/Login.test.tsx`
- **Estimated Complexity**: High
