# Phase 1 Data Model: Single-User Database Schema & Entity Simplification

**Feature Branch**: `026-remove-multi-user`  
**Date**: 2026-07-31  

---

## 1. Entity Classification & Lifecycle

### Tables Removed Completely
- `users`: Removed. Multi-user accounts no longer exist.
- `user_sessions`: Removed. JWT refresh tokens and active sessions removed.
- `devices`: Removed. Device fingerprinting removed.
- `audit_logs`: Removed. Administrative login/auth audit logging removed.
- `otps`: Removed. One-time password verification removed.
- `user_profiles`: Removed. Extended retail user preferences and personal metadata removed.

### Tables Retained & Modified
- `broker_tokens`:
  - **Change**: Drop FK `users.id` constraint.
  - **Attributes**: `id`, `user_id` (UUID default `'00000000-0000-0000-0000-000000000001'`), `broker` (`FYERS`), `encrypted_token`, `encrypted_api_key`, `encrypted_api_secret`, `status`, `is_active`, `updated_at`.
- `paper_trading_accounts`:
  - **Change**: Drop FK `users.id` constraint.
  - **Attributes**: `id`, `user_id` (UUID default `'00000000-0000-0000-0000-000000000001'`), `name`, `base_currency`, `starting_balance`, `cash_balance`, `max_risk_per_trade`.

### Tables Preserved Unchanged (Trading Engine Core)
- `paper_trading_positions`
- `paper_trading_orders`
- `stock_analyses`
- `stock_technical_summaries`
- `stock_news_sentiments`
- `latest_scan_snapshots`
- `scan_results`
- `fyers_tokens`
- `fyers_token_histories`
- `experiments`
- `event_calendar_events`

---

## 2. Migration Schema Plan

```sql
-- Migration: Decouple foreign keys and remove multi-user tables

BEGIN;

-- 1. Drop constraints
ALTER TABLE IF EXISTS broker_tokens DROP CONSTRAINT IF EXISTS uq_broker_tokens_user_broker;
ALTER TABLE IF EXISTS paper_trading_accounts DROP CONSTRAINT IF EXISTS fk_paper_trading_accounts_user_id;

-- 2. Update existing rows to static application owner ID
UPDATE broker_tokens SET user_id = '00000000-0000-0000-0000-000000000001' WHERE user_id IS NOT NULL;
UPDATE paper_trading_accounts SET user_id = '00000000-0000-0000-0000-000000000001' WHERE user_id IS NOT NULL;

-- 3. Drop multi-user tables
DROP TABLE IF EXISTS user_profiles CASCADE;
DROP TABLE IF EXISTS otps CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS user_sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

COMMIT;
```
