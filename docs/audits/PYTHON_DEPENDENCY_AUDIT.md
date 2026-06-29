# PYTHON DEPENDENCY AUDIT

## Overall Requirements
- **Python Version Required**: Python 3.10+ (Specifically 3.10.x or 3.11.x recommended due to `anyio`, `asyncio`, and `pandas` compatibility signatures)
- **Virtual Environment**: Highly recommended (`venv` or `poetry`) due to tightly pinned dependencies.
- **Requirements File Completeness**: `requirements.txt` contains explicitly locked versions for 77 packages. No missing core execution dependencies detected for Windows/Linux.

## Core Packages Identified
### Frameworks & Server
- `fastapi==0.116.1`
- `uvicorn==0.35.0`
- `starlette==0.47.3`
- `websockets==16.0`
- `websocket-client==1.6.1`

### Concurrency & Scheduling
- `asyncio==3.4.3`
- `anyio==4.13.0`
- `APScheduler==3.11.2`
- `greenlet==3.5.0`

### Database & ORM
- `SQLAlchemy==2.0.43`
- `asyncpg` (Implied via `postgresql+asyncpg` usage, though `psycopg2-binary==2.9.9` is present)
- `alembic` (NOT EXPLICITLY LISTED in `requirements.txt`. **MISSING DEPENDENCY** - The code relies on Alembic for DB migrations `alembic_head` checks).
- `redis` (NOT EXPLICITLY LISTED in `requirements.txt`. **MISSING DEPENDENCY** - Required by Redis Lock logic).

### Data Science & Quant
- `pandas==2.2.3`
- `numpy==2.4.4`
- `ta==0.11.0` (Technical Analysis library)
- `yfinance==1.4.0`
- `backtrader==1.9.78.123`

### External Integrations
- `fyers_apiv3==3.1.12` (FYERS SDK)
- `boto3==1.43.2`, `botocore==1.43.2` (AWS/S3)
- `requests==2.31.0`, `httpx==0.28.1`, `aiohttp==3.9.3`

### Utility & Validation
- `pydantic==2.11.7`, `pydantic-settings==2.14.1`
- `PyYAML==6.0.3`

## Findings
- **Missing Dependencies**: `alembic` and `redis` are actively imported (`import alembic`, `import redis`) in the codebase (e.g., `redis_lock.py`, `check_alembic_head`) but are missing from `requirements.txt`.
- **OS-Specific**: `psycopg2-binary` might require `libpq-dev` and `gcc` on bare Ubuntu servers during pip install. 

## Severity: HIGH
The backend will fail to start on a fresh machine because `redis` and `alembic` will throw `ModuleNotFoundError`.
