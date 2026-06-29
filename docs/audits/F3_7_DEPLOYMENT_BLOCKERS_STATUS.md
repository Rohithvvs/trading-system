# F3.7 DEPLOYMENT BLOCKERS STATUS

## AUDIT OF KNOWN BLOCKERS

1. **Localhost URLs in Pydantic Settings (`backend/app/config/settings.py`)**
   - *Status*: **OPEN**
   - *Evidence*: `database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"` is still hardcoded in `settings.py`.

2. **Hardcoded IP Binds (`app_host = 127.0.0.1`)**
   - *Status*: **OPEN**
   - *Evidence*: `app_host` remains `127.0.0.1`, breaking Docker bridging networks natively.

3. **Missing Critical Requirements (`requirements.txt`)**
   - *Status*: **OPEN**
   - *Evidence*: Neither `alembic` nor `redis` have been appended to the backend lock file.

4. **Unauthenticated Diagnostics Endpoints**
   - *Status*: **OPEN**
   - *Evidence*: Routes in `/system/shadow-run/*` continue to lack JWT/Auth middlewares, exposing global state anonymously.

5. **Hardcoded Frontend Configuration (`vite.config.ts`, `api.ts`)**
   - *Status*: **OPEN**
   - *Evidence*: Vite proxy commands and React API resolvers still prioritize `127.0.0.1`.

6. **FYERS Token Handling (Manual Cycle)**
   - *Status*: **PARTIALLY RESOLVED / ACCEPTED RISK**
   - *Evidence*: Automated refresh was explicitly disabled, meaning manual UI logins are strictly required to bridge the OAuth system daily.

## CLASSIFICATION
Deployment Configuration remains entirely rooted in Localhost Development Mode. The logic executes flawlessly, but the infrastructure mappings are statically fractured.
