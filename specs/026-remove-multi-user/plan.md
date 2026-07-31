# Phase 1 Implementation Plan: Single-User Application Simplification

**Branch**: `026-remove-multi-user` | **Date**: 2026-07-31 | **Spec**: [spec.md](file:///E:/Trading_lab/trading-system/specs/026-remove-multi-user/spec.md)  
**Input**: Feature specification from `specs/026-remove-multi-user/spec.md`

---

## Technical Context

- **Language/Version**: Python 3.11+ (Backend), TypeScript 5.x / React 18 (Frontend)
- **Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2.0, Vite, React Router v6
- **Storage**: PostgreSQL, Redis, Alembic migrations
- **Testing**: pytest (Backend), Vitest / React Testing Library (Frontend)
- **Target Platform**: Desktop Web / Workstation (Single Personal Operator)
- **Project Type**: Web Application (Personal AI Trading Platform)
- **Performance Goals**: Zero auth middleware latency overhead; immediate application launch in < 1 second.
- **Constraints**: 100% preservation of Recommendation Engine, Market Scanner, AI Agents, Technical Analysis, Backtesting, Paper Trading logic, and `MarketPermissionService`.

---

## Constitution Check

- **Library-First / Modular Core**: Trading engine modules remain self-contained and decoupled from UI/auth layers.
- **Test-First & Regression Prevention**: All trading pipeline regression tests must pass before and after auth removal.
- **Observability**: System logs, diagnostics endpoints, and execution metrics remain fully intact.
- **Simplicity**: Multi-tenant isolation removed; application operates in a clean single-owner context (`SYSTEM_OWNER_ID = UUID('00000000-0000-0000-0000-000000000001')`).

---

# 1. Executive Summary

Phase 1 establishes the complete specification and architectural plan to transform the platform from a generic multi-tenant SaaS application into a dedicated personal AI Trading Research Platform. This platform will be operated exclusively by a single owner. 

All authentication screens, multi-user registration flows, user management services, role-based authorization rules, and administrative components are systematic overhead and will be removed. The application will launch directly into the Central Command trading dashboard. Crucially, 100% of the recommendation algorithms, market scanner vectorization, paper trading execution models, AI agents, and market permissiveness filters (`MarketPermissionService`) remain intact and untouched.

---

# 2. Current System Assessment

- **Current Architecture**: Modern FastAPI backend paired with a Vite + React SPA frontend, backed by PostgreSQL and Redis.
- **Current Strengths**: Highly optimized market scanner, vectorized indicator engine, sophisticated recommendation scoring, modular AI trading agents, robust FYERS broker integration.
- **Current Complexity**: Unnecessary multi-tenant abstraction layer including user login/signup, JWT session cookies, password reset workflows, user profile preferences, device fingerprinting, and role checks.
- **Current Technical Debt**: Unused authentication boilerplate, redundant user foreign key constraints on paper trading accounts and broker tokens, and overhead in checking session cookies for local single-user requests.

---

# 3. Product Simplification Strategy

- **Why Simplification is Required**: The platform is used solely by one person on a dedicated workstation. Multi-user security overhead creates friction, unnecessary network requests, and maintenance burden.
- **What Will Be Simplified**:
  - Remove all authentication screens (Login, Signup, Forgot/Reset Password).
  - Remove user profile management, user sessions, device tracking, and user preference database tables.
  - Remove JWT generation, verification, auth middleware, and password hashing logic.
  - Replace user resolution dependencies with a static Application Owner Context (`SYSTEM_OWNER_ID = UUID('00000000-0000-0000-0000-000000000001')`).
- **What Will Remain Unchanged**:
  - Recommendation Engine scoring and candidate ranking.
  - Market Scanner ingestion, vectorization, and candle cache persistence.
  - AI Trading Agents and Orchestrator state machines.
  - `MarketPermissionService` (market regime & permissiveness logic).
  - Technical analysis computations (EMA, MACD, Supertrend, RSI).
  - FYERS broker OAuth token exchange (`/fyers/auth/url`, `/fyers/auth/exchange`).
  - Governance command routing (`GET /api/v1/governance/routes`).

---

# 4. Feature Inventory

| Feature | Current Status | Decision | Reason | Dependencies | Priority |
|---|---|---|---|---|---|
| Login / Signup Screens | Active | REMOVE | Obsolete for single user | None | P1 |
| Auth Middleware & JWT | Active | REMOVE | Obsolete for single user | None | P1 |
| User Profile & Preferences | Active | REMOVE | Obsolete for single user | None | P1 |
| Admin Dashboard & Roles | Active | REMOVE | Obsolete for single user | None | P1 |
| Central Command / Scanner UI | Active | KEEP | Primary trading interface | Scanner API | P1 |
| Recommendation Engine | Active | KEEP | Core value driver | Market Engine | P1 |
| Paper Trading Engine | Active | MODIFY | Decouple from user auth; use owner context | DB Models | P1 |
| FYERS Broker Token Management | Active | MODIFY | Decouple from user auth; keep FYERS OAuth | Fyers API | P1 |
| MarketPermissionService | Active | KEEP | Governs market regime for trading agents | Analysis | P1 |
| AI Trading Agents | Active | KEEP | Automated research & orchestration | Orchestrator | P1 |
| Governance Command Routing | Active | KEEP | CLI command routing (`AGENTS.md`) | Governance CLI | P1 |

---

# 5. Frontend Analysis

- **Pages to Keep**: Central Command (`/`), Scanner (`/scanner`), Watchlist (`/watchlist`), Markets (`/markets`), Paper Trading (`/paper-trading`), Performance (`/performance`), Diagnostics (`/diagnostics`), System Logs (`/logs`).
- **Pages to Remove**: `Login.tsx`, `Signup.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`, `SettingsSessions.tsx`.
- **Pages to Modify**: None (Routing updated in `main.tsx` and `App.tsx`).
- **Pages to Rename**: None.
- **Shared Components Affected**:
  - *Remove*: `ProtectedRoute.tsx`, `AdminRoute.tsx`, `AuthInput.tsx`, `AuthLayout.tsx`, `GoogleSignInButton.tsx`, `PasswordInput.tsx`, `PasswordStrength.tsx`, `UserProfilePage.tsx`, `ProfileCharts.tsx`.
  - *Modify*: `AppShell.tsx` (remove profile avatar/menu), `DashboardHeader.tsx` (remove logout dropdown), `WatchlistTab.tsx` (remove user ID dependency).
- **Navigation Impact**: Application opens directly to Central Command (`/`) on load without auth guards or redirects.

---

# 6. Backend Analysis

- **Services to Keep**: `RecommendationService`, `ScanExecutionService`, `ScreenerService`, `TechnicalAnalysisService`, `MarketEngineService`, `PaperTradingService`, `MarketPermissionService`, `BrokerTokenService`, `FyersService`, `WalkForwardService`, `DailyAnalyticsService`.
- **Services to Remove**: `AuthService`, `UserProfileService`, `EmailService`.
- **Services to Modify**:
  - `deps.py`: Remove `get_current_user`, `get_current_user_id_sync`. Introduce `get_application_owner_context`.
  - `broker_token_service.py` & `paper_trading_service.py`: Use static owner context instead of dynamic user resolution.
- **Repositories Affected**: None (SQLAlchemy models updated directly).
- **Business Logic Impact**: Zero logic change to market analytics, scans, signals, or paper execution.

---

# 7. API Analysis

| API Endpoint | Purpose | Current Usage | Decision | Migration Required | Breaking Changes |
|---|---|---|---|---|---|
| `POST /api/v1/auth/signup` | User Registration | Multi-user signup | REMOVE | No | Yes (Endpoint removed) |
| `POST /api/v1/auth/login` | User Login | Multi-user authentication | REMOVE | No | Yes (Endpoint removed) |
| `POST /api/v1/auth/logout` | Session Revocation | Multi-user logout | REMOVE | No | Yes (Endpoint removed) |
| `GET /api/v1/auth/profile` | Profile Retrieval | Retail user details | REMOVE | No | Yes (Endpoint removed) |
| `GET /api/v1/paper-trading/*` | Paper Trading | Trade execution | KEEP (MODIFY) | Decouple auth check | No (Runs in owner context) |
| `GET /api/v1/broker-tokens/*` | Broker Credentials | FYERS API keys | KEEP (MODIFY) | Decouple auth check | No (Runs in owner context) |
| `GET /fyers/auth/*` | FYERS Token Exchange | Market Data access | KEEP | None | No |
| `GET /api/v1/scanner/*` | Market Scanner | Scanning stocks | KEEP | None | No |
| `GET /api/v1/analysis/*` | Stock Recommendations | Scoring & analysis | KEEP | None | No |
| `GET /api/v1/governance/routes` | Governance Routes | CLI routing table | KEEP | None | No |

---

# 8. Database Analysis

| Table | Purpose | Current Usage | Decision | Migration Needed | Risk Level |
|---|---|---|---|---|---|
| `users` | User credentials & roles | Multi-user authentication | REMOVE | Drop table | Low |
| `user_sessions` | JWT refresh tokens | Session tracking | REMOVE | Drop table | Low |
| `devices` | Trusted devices | Fingerprinting | REMOVE | Drop table | Low |
| `audit_logs` | Auth audit trail | Login logs | REMOVE | Drop table | Low |
| `otps` | One-time passwords | Password reset | REMOVE | Drop table | Low |
| `user_profiles` | User preferences | Retail settings | REMOVE | Drop table | Low |
| `broker_tokens` | FYERS API keys | Data feed tokens | MODIFY | Drop FK to `users` | Medium |
| `paper_trading_accounts` | Paper trading capital | Virtual trading | MODIFY | Drop FK to `users` | Medium |
| `paper_trading_positions` | Open paper trades | Position tracking | KEEP | None | Low |
| `stock_analyses` | Recommendation scores | Analysis storage | KEEP | None | Low |
| `latest_scan_snapshots` | Scanner cache | Fast dashboard load | KEEP | None | Low |

---

# 9. Dependency Analysis

- **Direct Dependencies**: FastAPI, SQLAlchemy, React, React Router.
- **Indirect Dependencies**: Fernet (`cryptography`) used for broker token encryption (MUST BE RETAINED).
- **Shared Services**: Redis (candle/scanner caching) - RETAINED.
- **High-Risk Dependencies**: FYERS OAuth endpoints (`/fyers/auth/*`) - MUST NOT BE ACCIDENTALLY DELETED when cleaning auth routes.

---

# 10. Risk Assessment

- **Critical Risk**: Accidentally removing FYERS broker token endpoints (`/fyers/auth/*`) during auth cleanup, causing live market data feed failure.
  - *Mitigation*: Explicitly isolate `/fyers/auth/*` in `routes/fyers.py` and preserve it during `routes/auth.py` deletion.
- **High Risk**: Accidentally deleting `MarketPermissionService` mistaking it for user authorization.
  - *Mitigation*: Maintain `MarketPermissionService` in `services/market_permission_service.py` and verify test suite coverage.
- **Medium Risk**: Database FK constraint errors when dropping `users` table while `paper_trading_accounts` or `broker_tokens` reference `users.id`.
  - *Mitigation*: Execute Alembic migration that drops FK constraints and updates existing rows to static owner UUID before dropping `users`.
- **Low Risk**: Frontend broken links to `/login` or `/profile`.
  - *Mitigation*: Cleanly refactor AppShell header and route table to redirect unknown routes to `/`.

---

# 11. Implementation Roadmap

- **Work Package 1: Database Migration**: Alembic script to drop FK constraints, assign owner UUID, and drop 6 multi-user tables.
- **Work Package 2: Backend Auth Cleanup**: Remove `routes/auth.py`, `services/auth_service.py`, `services/user_profile_service.py`, and auth schemas. Replace `deps.py` auth dependencies with static Application Owner Context.
- **Work Package 3: Trading & Broker Service Decoupling**: Update `broker_token_service.py` and `paper_trading_service.py` to operate directly with static owner context.
- **Work Package 4: Frontend Simplification**: Remove auth screens, auth hooks, `ProtectedRoute`, `AdminRoute`, and user profile pages. Simplify `AppShell` and header.
- **Work Package 5: System Verification**: Execute complete end-to-end regression test suite to confirm zero impact on trading algorithms, scans, and recommendations.

---

# 12. Testing Strategy

- **Regression Testing**: Execute `pytest backend/app/tests` to verify recommendation engine, scanner, indicators, and paper trading tests pass cleanly.
- **Integration Testing**: Verify FYERS broker token generation (`/fyers/auth/url`) and paper trade order execution endpoints.
- **Smoke Testing**: Open browser to `http://localhost:5173/`, verify immediate render of Central Command without login prompt.
- **Validation Checklist**:
  - [ ] App launches directly to Central Command (`/`).
  - [ ] Paper trading order submission succeeds.
  - [ ] FYERS broker token validation succeeds.
  - [ ] Recommendation scores and candidate tables render identically.
  - [ ] `GET /api/v1/governance/routes` returns registered governance routes.

---

# 13. Out of Scope

Phase 1 strictly prohibits altering or restructuring any of the following core trading modules:
- Recommendation Engine scoring matrices & signal logic.
- Market Scanner vectorization, indicators, & persistence.
- AI Trading Agents & Orchestrator state machines.
- `MarketPermissionService` (Market Regime & Permissiveness logic).
- Technical Analysis calculations (EMA, MACD, Supertrend, RSI).
- Backtesting Engine.
- Paper Trading position calculation algorithms.
- Market Data feed ingestion handlers.

---

# 14. Definition of Done

- [ ] Complete Phase 1 Specification Plan (`plan.md`) generated and ratified.
- [ ] Phase 0 Research (`research.md`), Data Model (`data-model.md`), API Contracts (`contracts/single_owner_api.md`), and Quickstart (`quickstart.md`) created.
- [ ] 100% of trading and AI subsystems verified as preserved and out of scope.
- [ ] Ready for task generation (`/speckit-tasks`).
