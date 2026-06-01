# DEPLOYMENT BLOCKERS

## CRITICAL 

**1. HARDCODED LOCALHOST FALLBACKS IN SETTINGS (Backend)**
If the target production environment (Docker Swarm/K8s) fails to inject `DATABASE_URL` or `REDIS_URL`, the `Pydantic BaseSettings` schema masks the failure by silently falling back to `127.0.0.1:5432` and `localhost:6379`. The container will boot successfully but immediately fail internal connections.
- **Location:** `backend/app/config/settings.py`

**2. HARDCODED NETWORK BIND (Backend)**
The API enforces binding strictly to the local loopback adapter (`app_host: str = "127.0.0.1"`). In any Docker container configuration, traffic hitting the port externally via Reverse Proxies (Nginx, Traefik) will be instantly rejected.
- **Location:** `backend/app/config/settings.py`

**3. HARDCODED FALLBACKS IN FRONTEND REACT LOGIC (Frontend)**
Vite uses string-replacement at compile time. However, multiple hooks and UI modules possess hardcoded raw strings that trigger if environment strings are absent. A production CI/CD build missing `VITE_API_URL` will compile a frontend that attempts to contact `127.0.0.1` from the customer's browser.
- **Location:** `frontend/src/api.ts`, `Dashboard.tsx`, `SystemLogs.tsx`

**4. PUBLICLY EXPOSED DIAGNOSTIC ENDPOINTS (Backend)**
The new Phase S system endpoints return unrestricted JSON containing process memory signatures, database connection matrices, and internal scheduling errors without JWT / Auth middleware.
- **Location:** `backend/app/routes/system.py`

## HIGH

**5. HARDCODED CORS ALLOW-LIST (Backend)**
While `CORS_ORIGINS` exists, `main.py` explicitly whitelists raw developer strings (e.g., `http://localhost:3000`) and regex expressions bypassing the env validation structure.
- **Location:** `backend/app/main.py`

**6. VITE PROXY LEAKAGE (Frontend)**
`vite.config.ts` forces local proxy binding (`target: "http://127.0.0.1:8000"`). While Vite drops proxies for `build`, any attempt to run a staging node via `npm run dev` mapping external interfaces will fail.
- **Location:** `frontend/vite.config.ts`

## MEDIUM

**7. WEBSOCKET URI DEDUCTION**
The frontend implicitly assumes that the WebSocket server is located on the identical FQDN and Path format as the REST API (`http -> ws`). In advanced deployments where WSS is routed through an isolated API gateway port, the frontend will fail to connect.
- **Location:** `frontend/src/Dashboard.tsx`

**8. FYERS REDIRECT URI**
The OAuth flow has a hardcoded redirect testing snippet `https://trade.fyers.in/api-login/redirect-uri/index.html` bypassing domain registration validation.
- **Location:** `test.py` / Configurations

## LOW

**9. ORPHANED VARIABLES**
`mongo_url` and `mongo_db_name` still exist inside `settings.py` despite full architectural migration to PostgreSQL.

---

### FINAL STATUS: DEPLOYMENT_BLOCKERS_FOUND
The current configuration natively prevents a seamless CI/CD Docker build. Hardcoded IPs must be stripped from both Frontend and Backend architectures immediately.
