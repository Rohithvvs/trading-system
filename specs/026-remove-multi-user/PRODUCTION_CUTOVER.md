# Production Cutover Checklist — 026-remove-multi-user

**Status**: Required before production hardening / go-live  
**Revision**: `026_remove_multi_user`

---

## 1. Database backup (mandatory)

- [ ] Take a full PostgreSQL snapshot / logical dump **before** `alembic upgrade head`.
- [ ] Store the snapshot outside the application host.
- [ ] Confirm restore procedure (this migration’s `downgrade()` is intentionally empty).

```bash
# Example (adjust connection)
pg_dump "$DATABASE_URL" -Fc -f "backup_pre_026_$(date +%Y%m%d).dump"
```

---

## 2. Environment secrets (production fail-closed)

Set in the production environment:

| Variable | Purpose |
|----------|---------|
| `APP_ENV=production` | Enables fail-closed gates |
| `TOKEN_ENCRYPTION_KEY` | Fernet key material for broker tokens (required) |
| `API_KEY` | Bearer key for diagnostics/operator routes (required) |
| `SCHEDULER_SECRET` | Existing cron / scheduler gate |

Application startup **raises** if production is missing `TOKEN_ENCRYPTION_KEY` or `API_KEY`.

---

## 3. Trusted network only

User JWT auth is removed. Before exposing the API:

- [ ] Bind to private interface / private VPC **or**
- [ ] Place behind reverse proxy with IP allowlist / VPN **or**
- [ ] Local workstation only (no public 0.0.0.0 without firewall)

Do **not** publish the single-owner API to the open internet without network controls.

---

## 4. Run migration

```bash
cd backend
alembic upgrade head
```

Migration behaviour (multi-row safe):

1. Drops FKs from paper/broker → `users`.
2. Binds **one** paper account (`MIN(id)`) to static owner UUID; others get `user_id = NULL`.
3. Keeps **one** broker token row per broker (active preferred); assigns owner UUID.
4. Drops multi-user tables: `user_profiles`, `otps`, `audit_logs`, `devices`, `user_sessions`, `users`.

Static owner UUID: `00000000-0000-0000-0000-000000000001`.

---

## 5. Deploy order

1. Backup DB  
2. Set production secrets  
3. Deploy backend with this branch  
4. `alembic upgrade head`  
5. Deploy frontend (opens directly to scanner / trading shell)  
6. Smoke tests below  

---

## 6. Smoke tests

- [ ] `GET /health` → not 401  
- [ ] Open frontend `/` → no `/login` redirect  
- [ ] `GET /paper-trading/dashboard` without cookies → not 401  
- [ ] `GET /api/broker-tokens/list` without cookies → not 401  
- [ ] `GET /fyers/auth/url` → 200  
- [ ] `GET /api/v1/governance/routes` → 200  
- [ ] Diagnostics with missing API key in production → 401/503 (not open)  

---

## 7. Rollback

1. Restore DB from the pre-upgrade snapshot.  
2. Redeploy previous git revision (`git checkout` prior multi-user commit).  
3. Do **not** rely on `alembic downgrade` for `026_remove_multi_user`.
