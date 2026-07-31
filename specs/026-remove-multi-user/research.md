# Phase 0 Research: Single-User Simplification Architecture

**Feature Branch**: `026-remove-multi-user`  
**Date**: 2026-07-31  

---

## 1. Single Application Owner Context Pattern

### Decision
Implement a global, static application owner context (`SYSTEM_OWNER_ID = UUID('00000000-0000-0000-0000-000000000001')`) across the backend and frontend.

### Rationale
- Replaces dynamic HTTP request user extraction (`get_current_user`, JWT cookies) without breaking existing database column structures (`user_id`).
- Avoids complex refactoring of existing query filters in paper trading and broker token services.
- Eliminates 401 Unauthorized errors and login redirect flows while ensuring deterministic data scoping for single-user operation.

### Alternatives Considered
- **Option A (Remove `user_id` column entirely)**: Rejected because existing paper trading tables (`paper_trading_accounts`) and broker token tables (`broker_tokens`) rely on `user_id` columns. Dropping columns would require massive schema and query refactoring.
- **Option B (Dynamic local IP binding)**: Rejected because IP addresses change across local networks and introduce unnecessary complexity.

---

## 2. Foreign Key Decoupling Strategy

### Decision
Drop Foreign Key constraints on `broker_tokens.user_id` and `paper_trading_accounts.user_id` pointing to `users.id`, while retaining the `user_id` column as a plain UUID.

### Rationale
- Allows safely dropping the `users` table without causing cascading constraint failures or breaking dependent services.
- Simplifies database schema without altering trading models or position calculation queries.

### Migration Step
- Execute Alembic migration:
  1. `ALTER TABLE broker_tokens DROP CONSTRAINT IF EXISTS uq_broker_tokens_user_broker;`
  2. `ALTER TABLE paper_trading_accounts DROP CONSTRAINT IF EXISTS fk_paper_trading_accounts_user_id;`
  3. `UPDATE broker_tokens SET user_id = '00000000-0000-0000-0000-000000000001';`
  4. `UPDATE paper_trading_accounts SET user_id = '00000000-0000-0000-0000-000000000001';`
  5. `DROP TABLE IF EXISTS user_profiles, otps, audit_logs, devices, user_sessions, users CASCADE;`

---

## 3. FYERS Broker API OAuth vs. End-User Auth Disambiguation

### Decision
Retain FYERS OAuth token management routes (`/fyers/auth/url`, `/fyers/auth/exchange`, `fyers_token.py`) while removing end-user authentication (`/api/v1/auth/*`).

### Rationale
- FYERS broker OAuth generates access tokens required by the Market Data Feed and Scanner to query real-time market quotes and historical candles.
- User authentication (`/api/v1/auth/login`, `/signup`) was strictly for multi-tenant retail platform access control.
- Keeping FYERS broker token workflows ensures zero interruption to live scanner ingestion.

---

## 4. MarketPermissionService Retention

### Decision
Preserve `backend/app/services/market_permission_service.py` intact.

### Rationale
- `MarketPermissionService` evaluates market permissiveness / market regime (e.g. trend strength, volatility thresholds) to determine whether AI Trading Agents are permitted to execute trades in the current market environment.
- It has no relationship with user roles or administrative authorization.

---

## 5. Summary of Architecture Decisions

| Domain | Decision | Impact |
|---|---|---|
| **Identity** | Static Owner UUID (`00000000-0000-0000-0000-000000000001`) | Eliminates auth cookies & headers |
| **Database** | Decouple FKs & drop 6 auth tables | Reduces DB complexity |
| **Frontend** | Direct load to Central Command (`/`) | Removes login/signup/profile UI |
| **Trading Engine** | 100% logic preservation | Zero risk to recommendations/scans |
