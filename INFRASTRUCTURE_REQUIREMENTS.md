# INFRASTRUCTURE REQUIREMENTS

## Server Sizing Profiles (Ubuntu / Windows Server)

### Backend Fast API Node (Standalone)
- **CPU Minimum**: 2 Cores
- **CPU Recommended**: 4 Cores (due to heavy concurrency pooling and TA/Numpy matrix calculations for 755 symbols)
- **RAM Minimum**: 2 GB
- **RAM Recommended**: 4 GB (Heavy OHLCV in-memory arrays during pre-market deep scan)
- **Disk Space**: 10 GB minimum (Standard OS + Virtual Environment + Logging output)

### Postgres + Redis + Backend (Monolithic Server)
- **CPU Minimum**: 4 Cores
- **CPU Recommended**: 8 Cores (To balance DB indexing alongside Application TA processing)
- **RAM Minimum**: 4 GB
- **RAM Recommended**: 8 GB
- **Disk Space**: 30 GB minimum (Database volume growth over 1 year of snapshot arrays)

## Docker & Kubernetes Requirements
- **Docker Version**: 24.0+
- **Docker Compose**: v2.20+
- **Kubernetes Minimum**: 1.25+
- **Required Build Capabilities**: Multi-stage docker builds, access to `npm ci` and `pip install --no-cache-dir`.
- **Persistent Volumes (PV)**:
  - `postgres_data` (Must be bound to host storage for DB survival on container restart)
  - `redis_data` (Optional, if persistent queues are required)

## OS-Specific Requirements
- **Ubuntu/Linux**: Must provide `build-essential`, `gcc`, and `libpq-dev` for `psycopg2-binary` compilation if not using pre-compiled wheels.
- **Windows Server**: PowerShell is natively assumed by local E2E run scripts (`package.json`), but for deployment, standard CMD/NSSM or Docker Desktop WSL2 must be actively configured.
