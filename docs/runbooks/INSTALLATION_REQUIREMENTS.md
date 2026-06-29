# INSTALLATION REQUIREMENTS (MASTER OVERVIEW)

## Objective
To successfully migrate this trading system from Localhost to an isolated Production VPS.

## Core Prerequisites
- **Operating System:** Ubuntu 22.04 LTS (Highly Recommended) or Windows Server 2022.
- **Runtime Engines:** 
  - Python 3.10+
  - Node.js v18+ 
  - Docker v24+
- **Database Subsystems:**
  - PostgreSQL 15+ 
  - Redis 7+

## Missing Structural Requirements (Blockers)
1. **No Complete Dockerfile:** The project lacks a monolithic `Dockerfile` for the backend. `docker-compose.yml` only provisions the database.
2. **Missing `alembic` & `redis` in `requirements.txt`:** The backend will physically fail to `pip install` and run on a fresh machine without manual injection of these two libraries.
3. **Hardcoded PowerShell scripts in Node:** CI/CD runners using `npm run e2e` will crash instantly on Linux nodes due to `.ps1` hooks.
4. **Hardcoded `127.0.0.1` Network Binds:** The system refuses external traffic natively.

## Final Action Plan
Before attempting a staging deployment, a developer **must**:
1. Clean `requirements.txt` and include `redis` + `alembic`.
2. Rewrite `settings.py` and `vite.config.ts` to strictly obey Environment Variable overrides without asserting localhost priorities.
3. Draft a proper Backend `Dockerfile` to guarantee symmetric deployment between testing and production.
