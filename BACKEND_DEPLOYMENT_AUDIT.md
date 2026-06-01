# BACKEND DEPLOYMENT AUDIT

## 1. Localhost Database & Redis Connections
The Pydantic Settings explicitly default core persistent storage to local network interfaces, masking missing environment variables during container orchestration.

**Files Affected:**
- `backend/app/config/settings.py`
  - Line 25: `database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"`
  - Line 26: `redis_url: str = "redis://localhost:6379/0"`
  - Line 71 (Validator): `return "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"`

**Severity:** CRITICAL
**Remediation:** Remove local fallbacks for infrastructure URIs. Use Pydantic's `Field(..., description="Required DB URL")` to forcefully crash the container on boot if `DATABASE_URL` or `REDIS_URL` are missing.

## 2. Hardcoded CORS Origins
Cross-Origin requests are explicitly limited to local development ports, preventing Staging or Production UI domains from authenticating or accessing APIs.

**Files Affected:**
- `backend/app/main.py`
  - Line 511-512: `http://localhost:3000`, `http://localhost:5173`
  - Line 515: `allow_origin_regex=r"(http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app|https://.*\.onrender\.com)"`
- `backend/app/config/settings.py`
  - Line 27: `cors_origins_raw` defaults to `http://localhost:5173,http://127.0.0.1:5173`

**Severity:** HIGH
**Remediation:** Remove hardcoded vercel/onrender regexes and localhosts from `main.py`. Map origins purely to the `CORS_ORIGINS` environment variable.

## 3. FYERS Hardcoded Callbacks
The broker redirect URI is currently empty or manually synced via UI, but local test files hardcode `https://trade.fyers.in/api-login/redirect-uri/index.html` bypassing domain ownership requirements.

**Files Affected:**
- `backend/app/config/settings.py` (Line 33)

**Severity:** HIGH
**Remediation:** Enforce `FYERS_REDIRECT_URI` natively matching the exact production backend domain (e.g. `https://api.my-domain.com/fyers/callback`).

## 4. Unauthenticated Diagnostic Endpoints
The Phase S shadow-run status pipelines were implemented without user authorization bindings. 

**Files Affected:**
- `backend/app/routes/system.py`

**Severity:** CRITICAL
**Remediation:** Add `Depends(get_current_user)` to all `/system/shadow-run/*` endpoints before porting to a public IP.

## 5. Hardcoded Network Bindings
The main server boot forces `127.0.0.1` binding, effectively blocking Docker bridged network access.

**Files Affected:**
- `backend/app/config/settings.py`
  - Line 23: `app_host: str = "127.0.0.1"`

**Severity:** CRITICAL
**Remediation:** Set `app_host` to `0.0.0.0`.
