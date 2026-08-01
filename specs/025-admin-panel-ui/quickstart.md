# Quickstart Validation: Sprint 4 – Admin Panel UI

Manual smoke after implementation. Sprint 2–3 APIs must be running.

## Prerequisites

- Backend up; migrations applied (users RBAC + feature_permissions).  
- Default admin credentials available.  
- Frontend: `cd frontend && npm run dev`.

---

## 1. Admin opens panel

1. Log in as admin.  
2. **Admin** appears in nav.  
3. Open Admin → Users + Features tabs.  
4. URL includes `?tab=users` (or equivalent default).  
5. Switch to Features → URL `?tab=features`; refresh keeps Features.

---

## 2. Trader blocked

1. Log in as trader.  
2. No Admin / logs / command in nav.  
3. Visit `/admin`, `/admin/logs`, `/admin/command` → forbidden; no admin tables.

---

## 3. Developer mode cannot elevate

1. As trader, if Developer mode toggle still exists, enable it.  
2. `/admin*` still forbidden.  
3. As admin with Developer mode **off**, `/admin`, logs, and command still work.

---

## 4. Users: search + role change

1. Search for a known email fragment → list filters.  
2. Promote trader → admin (confirm modal) → success; row updates.  
3. With only one admin, demote → error (last-admin); role unchanged.

---

## 5. Features: allowed_roles only

1. Set `watchlist` to admin-only → Save → success.  
2. Confirm `is_active` has no toggle (display only).  
3. Try remove admin from `admin_panel` → blocked in UI and/or 400; roles restored.

---

## 6. Retail regression

Trader can open Scanner / Markets / Paper normally.

---

## Automated

```bash
cd frontend
npm test
# or targeted:
npx vitest run src/components/__tests__/AdminRoute.test.tsx
```
