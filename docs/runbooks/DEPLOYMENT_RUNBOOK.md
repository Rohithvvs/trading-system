# DEPLOYMENT RUNBOOK

## Pre-Requisites (Target Node)
1. Fresh VPS (Ubuntu 22.04 LTS or equivalent).
2. Install Docker (`apt-get install docker.io`) & Docker Compose.
3. Network inbound open on `80`, `443`.

## 1. Environment Injection
Create a secure `.env` file at the root. You must manually map:
- `DATABASE_URL` (Point to persistent DB)
- `REDIS_URL`
- `CORS_ORIGINS`
- `GROQ_API_KEY`
- `FYERS_APP_ID` & `FYERS_SECRET_ID`

## 2. Infrastructure Boot
Start PostgreSQL and Redis.
```bash
docker-compose up -d db
# Note: Manually boot a redis instance as it's missing from compose.
docker run -d --name trading_redis -p 6379:6379 redis:alpine
```

## 3. Database Migration
Before starting the backend, you must apply the Alembic schema.
```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt alembic psycopg2-binary
cd backend
alembic upgrade head
```

## 4. Backend Spin-Up
Modify `app_host` inside settings or bind explicitly via `uvicorn`.
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 5. Frontend Build
Ensure API URLs are compiled into the static assets.
```bash
cd frontend
npm ci
VITE_API_URL="https://api.yourdomain.com" npm run build
```
Deploy the resulting `dist/` folder to Nginx, Vercel, or AWS S3/CloudFront.

## 6. Daily Operator Checklist
- Navigate to the UI Dashboard before **08:50 AM** daily.
- Authorize the FYERS integration.
- Ensure `/system/shadow-run/health/ready` returns `True`.
