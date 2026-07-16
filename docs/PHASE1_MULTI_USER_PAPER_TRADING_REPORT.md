# Phase 1 — Multi-User Paper Trading Architecture

**Status:** COMPLETE & VERIFIED  
**Date:** 2026-07-11  
**Phase 2 (Daily Analytics):** NOT STARTED (blocked until Phase 1 acceptance)

---

## Security finding (before)

Paper Trading used a **single shared account**:

```python
# OLD
query = select(PaperTradingAccount).order_by(PaperTradingAccount.id.asc())
account = self.db.scalar(query)  # first row for EVERY user
```

- No `user_id` on `paper_trading_accounts`
- Paper routes had **no authentication dependency**
- Market engine fills used `_get_or_create_account()` without user context  
→ **Horizontal privilege / shared portfolio** risk

---

## Architecture (after)

```
User (JWT cookie sub)
    └── PaperTradingAccount.user_id  (UNIQUE)
            ├── paper_trading_positions.account_id
            ├── paper_trading_orders.account_id
            ├── paper_trading_trade_history.account_id
            ├── paper_trading_transactions.account_id
            ├── paper_trading_alerts.account_id
            ├── paper_trading_notifications.account_id
            └── analytics derived from above
```

Child tables remain correctly scoped by `account_id`. Isolation root is **account ownership via `user_id`**.

---

## Database

| Change | Detail |
|--------|--------|
| Model | `PaperTradingAccount.user_id` → UUID FK `users.id`, unique |
| Default capital | ₹10,00,000 (`DEFAULT_PAPER_STARTING_BALANCE`) |
| Migration | `backend/alembic/versions/20260711_paper_account_user_isolation.py` |
| Revision | `paper_user_isolation_001` (revises `add_reset_password_fields`) |
| Backfill | Single orphan account bound to first user when safe |

**Apply migration:**

```bash
cd backend
alembic upgrade head
```

---

## Authentication

| Rule | Implementation |
|------|----------------|
| Never trust frontend `user_id` | Not accepted on any paper endpoint |
| Identity source | HttpOnly `access_token` cookie → JWT `sub` |
| Sync deps | `get_current_user_id_sync` in `core/deps.py` |
| Paper routes | `get_service(..., user_id=Depends(...))` → `PaperTradingService(db, user_id=)` |

Unauthenticated paper API calls → **401**.

---

## Account lifecycle

| Event | Behavior |
|-------|----------|
| Email signup | Auto `ensure_paper_account_for_user` (₹10L) |
| Google signup | Same |
| First paper API | `_get_or_create_account` if missing |
| Re-login | Existing account restored (never recreated) |
| Ensure | Idempotent on unique `user_id` |

---

## Queries / mutations

All user-facing paths:

1. Resolve `account = _get_or_create_account()` for `self.user_id`
2. Filter / write with `account_id == account.id`

Engine / background:

- Fill: `get_account_by_id(order.account_id)`
- Exit: load position → its `account_id`
- Alerts: all active alerts, trigger by alert’s own `account_id`
- Token-pause notifications: every **affected** account_id

---

## Cache isolation (frontend)

`appCache.setCacheUserScope(userId)` on login / session restore / logout.

Keys become: `paper_dashboard:u:<userId>`, etc.  
Different users never share sessionStorage entries for paper data.

---

## Tests (verified)

File: `backend/app/tests/test_multi_user_paper_isolation.py`

```
7 passed (+ 50-user provisioning)
✓ isolated ₹10L accounts
✓ ensure idempotent
✓ B cannot see A positions/orders/trades/analytics
✓ B cannot cancel A’s order; A can
✓ 10-user batch isolation
✓ never recreate after balance change
✓ engine fill debits order’s account only
✓ 50-user account provisioning
```

Run:

```bash
cd backend
.\venv\Scripts\python.exe -m pytest app/tests/test_multi_user_paper_isolation.py -v
```

---

## Files modified

### Backend
- `app/models/paper_trading.py` — `user_id`, default ₹10L
- `app/services/paper_trading_service.py` — user-scoped account, engine helpers, multi-user alerts/exits
- `app/routes/paper_trading.py` — auth-required service DI
- `app/core/deps.py` — sync JWT user id deps
- `app/services/auth_service.py` — provision paper account on register
- `app/services/market_engine_service.py` — fill/notify by order/position account
- `alembic/versions/20260711_paper_account_user_isolation.py`
- `app/tests/test_multi_user_paper_isolation.py`

### Frontend
- `src/utils/appCache.ts` — user-scoped keys
- `src/hooks/useAuth.tsx` — set/clear cache user scope

---

## Security verification checklist

| Check | Result |
|-------|--------|
| Separate balances | Pass (test) |
| Separate portfolios | Pass (test) |
| Separate orders | Pass (test) |
| Separate analytics | Pass (test) |
| Cross-user cancel blocked | Pass (test) |
| Engine no shared-account fill | Pass (test) |
| Frontend cache isolation | Implemented |
| JWT-only identity | Implemented |
| Auth required on paper APIs | Implemented |

---

## Performance notes

- Account lookup is indexed unique on `user_id` (single row)
- No cross-user scans on user API paths
- Registration provision is best-effort async thread (non-blocking for signup success)

---

## Phase 1 gate for Phase 2

Phase 2 (Daily Analytics tab) may begin only after:

1. `alembic upgrade head` applied on target DB  
2. Isolation tests green  
3. Manual smoke: User A trade → logout → User B empty ₹10L → logout → User A restored  

**Phase 2 has not been started.**
