# DATABASE REQUIREMENTS

## PostgreSQL Infrastructure
- **Minimum Version**: 13+ (due to advanced `JSONB` indexing and CTE usages).
- **Recommended Version**: 15+ (as declared in `docker-compose.yml` via `postgres:15-alpine`).
- **Required Extensions**: None explicitly detected in `init.sql`, but `pg_stat_statements` is highly recommended for query tuning.
- **SSL Requirements**: Production instances on AWS RDS / GCP Cloud SQL must configure `sslmode=require` via the `DATABASE_URL`. The current default uses unencrypted `localhost` connections.

## Connection & Pool Requirements
- **Driver**: The application connects using `postgresql+asyncpg://`, meaning `asyncpg` manages the core async loop.
- **Max Connections**: The APScheduler processes 755 symbols in heavily asynchronous chunks. The database `max_connections` parameter should be at least `100+` to accommodate the SQLAlchemy Async Engine pooling bursts.

## Migration Requirements
- **Alembic**: Required for schema history execution (`alembic upgrade head`).
- **Superuser**: Standard `CREATE TABLE` and `CREATE INDEX` permissions are required. Superuser is not required during regular app runtime.
