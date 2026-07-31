# Feature Specification: Phase 1 — Remove Multi-User & Single-User Application Simplification

**Feature Branch**: `026-remove-multi-user`  
**Created**: 2026-07-31  
**Status**: Draft  
**Input**: User description: "/speckit-specify # ROLE You are a Senior AI Software Architect working with Spec Driven Development (SDD)... Simplify application from multi-user platform into personal single-user AI Trading Research Platform."

---

## Executive Summary & Scope Boundary

The trading platform is transitioning from a generic multi-user SaaS application into a dedicated, local/personal single-user AI Trading Research Platform. This application will be owned and operated by a single individual. Consequently, all multi-tenant isolation, user authentication, registration, password management, role-based authorization, and user administration features are obsolete and must be cleanly removed.

### Strict Scope Bounds
- **Logic Safeguards (Zero Modification)**:
  - Recommendation Engine scoring, ranking, and signal generation algorithms.
  - Market Scanner vectorization, indicators, and candle persistence.
  - AI Trading Agents and Orchestrator state machines.
  - Market Permission Service (Market Regime & Permissiveness filters).
  - Technical analysis computations (EMA, MACD, Supertrend, RSI).
  - Backtesting engines and paper trading execution models.
  - FYERS Broker API integration & automated token refresh workflow (`/fyers/auth/url`, `/fyers/auth/exchange`).
  - Governance command routing (`GET /api/v1/governance/routes`).

---

## Required Architecture Analysis

### 1. Files Affected
#### Frontend Files to Remove:
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Signup.tsx`
- `frontend/src/pages/ForgotPassword.tsx`
- `frontend/src/pages/ResetPassword.tsx`
- `frontend/src/pages/SettingsSessions.tsx`
- `frontend/src/components/ProtectedRoute.tsx`
- `frontend/src/components/AdminRoute.tsx`
- `frontend/src/components/AuthInput.tsx`
- `frontend/src/components/AuthLayout.tsx`
- `frontend/src/components/GoogleSignInButton.tsx`
- `frontend/src/components/PasswordInput.tsx`
- `frontend/src/components/PasswordStrength.tsx`
- `frontend/src/components/profile/UserProfilePage.tsx`
- `frontend/src/components/profile/ProfileCharts.tsx`
- `frontend/src/hooks/useAuth.tsx`
- `frontend/src/api_auth.ts`
- `frontend/src/api_auth_login.ts`

#### Frontend Files to Modify:
- `frontend/src/main.tsx` — Remove `AuthProvider`, `GoogleOAuthProvider`, login/signup/reset routes, and `ProtectedRoute` wrapper.
- `frontend/src/App.tsx` — Remove `useAuth` hook, `prefetchAppData` user checks, profile page routes, and auth-dependent state.
- `frontend/src/api.ts` — Remove auth, profile, and session API client helpers.
- `frontend/src/layout/AppShell.tsx` — Remove user profile avatar, profile menu, and logout action.
- `frontend/src/components/DashboardHeader.tsx` — Remove user profile dropdown and logout trigger.
- `frontend/src/components/WatchlistTab.tsx` — Remove `user.id` dependency for watchlist loading/saving.
- `frontend/src/pages/MarketsPage.tsx` — Remove user context checks.
- `frontend/src/pages/WatchlistPage.tsx` — Remove user context checks.

#### Backend Files to Remove:
- `backend/app/models/auth.py` — Delete `User`, `UserSession`, `Device`, `AuditLog`, `OTP` SQLAlchemy models.
- `backend/app/models/user_profile.py` — Delete `UserProfile` SQLAlchemy model.
- `backend/app/routes/auth.py` — Delete auth/user endpoints router.
- `backend/app/services/auth_service.py` — Delete authentication, session management, and password reset service logic.
- `backend/app/services/user_profile_service.py` — Delete user profile service.
- `backend/app/services/email_service.py` — Delete password reset and email notification service.
- `backend/app/schemas/auth.py` — Delete authentication request/response Pydantic schemas.
- `backend/app/schemas/user_profile.py` — Delete user profile Pydantic schemas.

#### Backend Files to Modify:
- `backend/app/core/deps.py` — Remove `get_current_user`, `_extract_user_id_from_request`, and `get_current_active_user`. Introduce static application owner context provider.
- `backend/app/core/security.py` — Remove JWT encoding/decoding and password hashing routines; retain Fernet encryption for broker tokens.
- `backend/app/routes/__init__.py` — Remove `auth_router` inclusion.
- `backend/app/routes/broker_tokens.py` — Replace `get_current_user` dependency with single application owner context.
- `backend/app/routes/paper_trading.py` — Replace `get_current_user_id_sync` dependency with single application owner context.
- `backend/app/models/broker_token.py` — Remove Foreign Key constraint to `users.id`; default `user_id` column to static owner UUID `00000000-0000-0000-0000-000000000001`.
- `backend/app/models/paper_trading.py` — Remove Foreign Key constraint from `PaperTradingAccount.user_id` to `users.id`.

---

### 2. APIs Affected
#### APIs Removed:
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

#### APIs Preserved & Modified for Single-Owner Access (No Auth Header/Cookie Required):
- `/api/v1/screener/*` & `/api/v1/scanner/*`
- `/api/v1/analysis/*`
- `/api/v1/paper-trading/*`
- `/api/v1/broker-tokens/*`
- `/fyers/*` (FYERS OAuth callback & token exchange)
- `/api/v1/governance/*`
- `/api/v1/health`, `/api/v1/logs`, `/api/v1/system`, `/api/v1/diagnostics`, `/api/v1/analytics`

---

### 3. Database Tables Affected
#### Tables to Drop:
- `users`
- `user_sessions`
- `devices`
- `audit_logs` (admin & user authentication logs)
- `otps`
- `user_profiles`

#### Foreign Keys to Drop/Modify:
- `broker_tokens`: Drop constraint `fk_broker_tokens_user_id`. Retain `user_id` column with default static owner UUID `00000000-0000-0000-0000-000000000001`.
- `paper_trading_accounts`: Drop constraint `fk_paper_trading_accounts_user_id`. Retain `user_id` column with default static owner UUID `00000000-0000-0000-0000-000000000001`.

---

### 4. Frontend Pages Affected
- **Removed**: Login (`/login`), Signup (`/signup`), Forgot Password (`/auth/forgot-password`), Reset Password (`/auth/reset-password`), User Profile (`/profile`), Settings Sessions (`/settings/sessions`).
- **Retained Direct Access**: Central Command / Scanner (`/`), Watchlist (`/watchlist`), Markets (`/markets`), Paper Trading (`/paper-trading`), Performance (`/performance`), Diagnostics (`/diagnostics`), System Logs (`/logs`).

---

### 5. Backend Services Affected
- **Removed**: `AuthService`, `UserProfileService`, `EmailService`.
- **Modified**: `BrokerTokenService`, `PaperTradingService` (refactored to resolve single application owner context without JWT cookie/token verification).

---

### 6. Dependencies Affected
- **Frontend**: Remove `@react-oauth/google` package and `VITE_GOOGLE_CLIENT_ID` environment configuration.
- **Backend**: Remove unused auth dependencies (`python-jose`, `passlib`, `bcrypt`) while preserving `cryptography` (Fernet) for broker credential encryption.

---

### 7. Breaking Changes
- Eliminates JWT cookie (`access_token`, `refresh_token`) issuance and verification.
- Requests to backend endpoints no longer return HTTP 401 Unauthorized due to missing user sessions.
- Default owner context (`00000000-0000-0000-0000-000000000001`) automatically applies to paper trading accounts and broker credentials.

---

### 8. Migration Steps
1. Run Alembic migration script to drop FK constraints on `broker_tokens` and `paper_trading_accounts`, update existing records to `user_id = '00000000-0000-0000-0000-000000000001'`, and drop tables (`user_profiles`, `otps`, `audit_logs`, `devices`, `user_sessions`, `users`).
2. Deploy simplified backend without auth routers or security dependencies.
3. Deploy updated frontend opening directly to Central Command (`/`).

---

### 9. Risks & Mitigations
- **Risk**: Accidentally removing FYERS broker OAuth flow (`/fyers/auth/url`, `/fyers/auth/exchange`) when removing user auth.
  - *Mitigation*: Explicitly verify FYERS token exchange endpoints remain functional for market data ingestion.
- **Risk**: Accidentally removing `MarketPermissionService`.
  - *Mitigation*: Retain `MarketPermissionService` in `backend/app/services/market_permission_service.py` as it controls market regime permissiveness for trading agents.
- **Risk**: Orphaned paper trading state.
  - *Mitigation*: Alembic migration updates existing paper account `user_id` to owner UUID before dropping `users` table.

---

### 10. Rollback Strategy
- Perform a PostgreSQL database snapshot before executing the Alembic migration.
- Clean git branch isolation (`026-remove-multi-user`) enables instant revert to multi-user state if required.

---

## User Scenarios & Testing

### User Story 1 — Instant Application Launch without Authentication (Priority: P1)

As the single owner of the AI Trading Platform,  
I want the application to launch directly into the Central Command trading dashboard when opened in the browser,  
So that I can immediately monitor market scans and AI recommendations without logging in or managing credentials.

**Why this priority**: Core objective of transforming into a single-user personal platform.

**Independent Test**: Opening `http://localhost:5173/` in a fresh browser session with cleared cookies immediately loads the Central Command dashboard without redirects to `/login`.

**Acceptance Scenarios**:
1. **Given** a browser with no cookies, **When** navigating to `/`, **Then** the Central Command dashboard renders immediately.
2. **Given** any direct link to `/scanner`, `/watchlist`, `/markets`, or `/paper-trading`, **When** loaded, **Then** the requested page renders without authentication checks or redirects.

---

### User Story 2 — Seamless Single-Owner Paper Trading & Broker Connectivity (Priority: P2)

As the single owner,  
I want paper trading orders and FYERS broker API settings to function seamlessly under a single owner context,  
So that trade execution, position tracking, and FYERS data feeds operate continuously without user session constraints.

**Why this priority**: Preserves core trading engine functionality post-simplification.

**Independent Test**: Executing a paper trading order from a recommendation card succeeds without auth headers and updates the primary paper account balance.

**Acceptance Scenarios**:
1. **Given** an active market scan recommendation, **When** clicking "Paper Trade", **Then** the order is executed under the default owner context.
2. **Given** valid FYERS credentials, **When** initiating broker token validation in settings, **Then** FYERS API profile validation completes successfully.

---

### User Story 3 — Simplified UI Shell without User Profile Overhead (Priority: P3)

As the single owner,  
I want the UI header and navigation shell to be clean of user profile menus, avatars, signup links, or logout buttons,  
So that the interface is focused purely on trading research and system observability.

**Why this priority**: Enhances visual clarity and removes dead UI elements.

**Independent Test**: Inspecting the application header confirms no profile dropdown, user email, or logout button is visible.

**Acceptance Scenarios**:
1. **Given** the AppShell header, **When** rendered, **Then** only theme toggles, system status badges, and navigation links are displayed.

---

## Edge Cases

- **Direct navigation to deprecated route `/login` or `/signup`**: System gracefully redirects to `/` (Central Command).
- **Existing database with paper accounts assigned to historical user IDs**: Alembic migration updates `user_id` on all paper accounts and broker tokens to `00000000-0000-0000-0000-000000000001` before dropping `users`.
- **FYERS Token Refresh**: FYERS OAuth token generation endpoints (`/fyers/auth/url`, `/fyers/auth/exchange`) remain fully operational for broker API data feed connectivity.

---

## Requirements

### Functional Requirements

- **FR-010-01**: System MUST remove all authentication pages (`Login`, `Signup`, `ForgotPassword`, `ResetPassword`) and authentication API endpoints (`/api/v1/auth/*`).
- **FR-010-02**: System MUST remove JWT token generation, cookie-based session verification, OAuth authentication providers, and authentication middleware dependencies.
- **FR-011-01**: System MUST remove User Profile pages, User Settings pages, User Preferences services, and user-specific database tables (`users`, `user_profiles`, `user_sessions`, `devices`, `audit_logs`, `otps`).
- **FR-011-02**: System MUST provide a single application owner context (`SYSTEM_OWNER_ID = UUID('00000000-0000-0000-0000-000000000001')`) for all paper trading accounts and broker credentials.
- **FR-012-01**: System MUST remove all admin dashboards, role management, role-based authorization dependencies, and admin-only audit components.
- **FR-013-01**: System MUST retain all recommendation engine, scanner, market data, paper trading, backtesting, AI agent, scheduler, and research logic without modification.
- **FR-013-02**: System MUST preserve `MarketPermissionService` (market regime & permissiveness logic) and FYERS broker API authentication workflows (`/fyers/auth/*`).

---

### Key Entities

- **ApplicationOwnerContext**: Represents the single owner of the application system.
  - Attributes: `owner_id` (`00000000-0000-0000-0000-000000000001`), `role` (`Owner`).
- **PaperTradingAccount**: Primary paper trading account scoped to the single Application Owner Context.
- **BrokerToken**: Encrypted FYERS broker API token scoped to the single Application Owner Context.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of user authentication screens, user management components, and admin pages are removed.
- **SC-002**: 0 HTTP requests require `Authorization` headers or JWT cookies for application navigation or trading operations.
- **SC-003**: 100% of core trading engine tests (Scanner, Recommendations, Paper Trading, AI Agents) pass without regression.
- **SC-004**: Initial application load time improves as auth pre-check overhead and session round-trips are eliminated.

---

## Assumptions

- The application is deployed in a trusted environment (e.g., local workstation, private LAN, or secured cloud instance) dedicated exclusively to the application owner.
- FYERS broker OAuth tokens are required solely for market data feed access and are managed under the single application owner context.
- System logs and diagnostic endpoints remain accessible for platform monitoring.

---

## Definition of Done

- [ ] All FEAT-010 auth files, routes, services, and tables removed.
- [ ] All FEAT-011 user management files, routes, services, and tables removed.
- [ ] All FEAT-012 admin dashboard components and role authorization checks removed.
- [ ] Single application owner context integrated into paper trading and broker token services.
- [ ] Database migration successfully tested and verified.
- [ ] Zero changes made to Recommendation Engine, Market Scanner, AI Agents, or MarketPermissionService.
- [ ] Automated and manual verification demonstrates clean application startup directly to Central Command.
