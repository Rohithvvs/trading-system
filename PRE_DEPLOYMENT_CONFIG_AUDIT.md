# PRE-DEPLOYMENT CONFIGURATION AUDIT

## OVERVIEW
This document maps every configuration node that MUST shift between Local Development and Staging/Production environments.

### 1. Database Connectivity (PostgreSQL)
- **Local State:** Hardcoded default to `postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system` in Pydantic BaseSettings.
- **Production Requirement:** MUST use `DATABASE_URL` via OS environment variables. Pool sizing must be set. SSL requirements (`?sslmode=require`) must be manually appended to the URI if using managed services like AWS RDS or Supabase.

### 2. Cache Connectivity (Redis)
- **Local State:** Hardcoded `redis://localhost:6379/0`
- **Production Requirement:** `REDIS_URL` must be injected. Timeouts must be validated. Singleton locks and rate limiters share Database 0, so dedicated deployment cache clustering requires mapping multiple instances if scaled horizontally.

### 3. Application Security (CORS)
- **Local State:** Open endpoints (`localhost:3000`, `127.0.0.1:5173`) hardcoded in `main.py` explicitly alongside regex patterns for Vercel/Render.
- **Production Requirement:** Must strictly rely ONLY on the `CORS_ORIGINS` environment variable string.

### 4. Scheduler Instance Concurrency
- **Local State:** `AsyncIOScheduler` boots per FastAPI lifespan. Singleton `worker_lease` is acquired on boot.
- **Production Requirement:** The leader election logic in `main.py` (`trading-system:singleton-workers`) technically prevents multiple schedulers from running simultaneously. However, Docker Swarm or Kubernetes rolling updates might briefly pause jobs if the lock TTL hangs on an ungracefully terminated pod.

### 5. Frontend Build Configuration
- **Local State:** Vite acts as a local proxy (`vite.config.ts`) explicitly targeting `http://127.0.0.1:8000`. API URLs fall back to `http://127.0.0.1:8000` inside React components.
- **Production Requirement:** Proxy logic MUST be disabled during static builds (`npm run build`). API resolution MUST bind exclusively to `VITE_API_URL` allowing CDN (Cloudflare/Vercel) hosting.

### 6. Diagnostic Footprints
- **Local State:** Endpoints `/system/shadow-run/status` are open without authentication.
- **Production Requirement:** Extremely high risk of data leakage. Must be shielded behind JWT authorization or strict Private VPC Network ACLs.

## MIGRATION STRATEGY
1. Strip all `.env` defaults from `.py` and `.ts` core logic.
2. Force fast-failure / fatal boot sequence if `DATABASE_URL`, `REDIS_URL`, or `VITE_API_URL` are missing.
3. Decouple Websocket URLs into discrete configuration rather than relying on `HTTP.replace()`.
