# FRONTEND DEPLOYMENT AUDIT

## 1. Localhost API URLs & Hardcoded Backend URLs
The frontend currently hardcodes API endpoints directly into multiple services, often bypassing environment variable injection, making production deployments impossible without source code changes.

**Files Affected:**
- `frontend/src/api.ts` (Line 19)
  - `const BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';`
- `frontend/src/Dashboard.tsx` (Line 133)
  - `const baseHttpUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";`
- `frontend/src/pages/SystemLogs.tsx` (Line 29)
  - `const API_BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";`
- `frontend/src/hooks/useInfrastructureHealth.ts` (Line 37)
  - `const baseUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";`

**Severity:** CRITICAL
**Remediation:** Remove all hardcoded `127.0.0.1` fallbacks from the React components. Consolidate API URL resolution into a single `config.ts` module that strictly reads `import.meta.env.VITE_API_URL` and throws a fatal boot error if missing.

## 2. Vite Configuration
The Vite bundler is strictly configured to only host and proxy over local interfaces.

**Files Affected:**
- `frontend/vite.config.ts`
  - `host: "127.0.0.1"` (Line 8)
  - `target: "http://127.0.0.1:8000"` (Line 12)

**Severity:** HIGH
**Remediation:** Change `host` to `0.0.0.0` or inject dynamically for docker deployments.

## 3. WebSocket Endpoints
Websockets are not hardcoded but instead rely on a string-replacement protocol over the HTTP base URL. 
- `Dashboard.tsx` (Line 134): `const wsUrl = baseHttpUrl.replace(/^http/, "ws") + "/ws";`
- **Compatibility Risk:** If the frontend is hosted on HTTPS, this correctly upgrades to WSS, but if the backend uses an API Gateway (like AWS API Gateway v2 or Nginx) that routes `/ws` differently than `/api`, this implicit assumption will fail.

**Severity:** MEDIUM
**Remediation:** Introduce a dedicated `VITE_WS_URL` environment variable to decouple the WebSocket routing from REST routing.
