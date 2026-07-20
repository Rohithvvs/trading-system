# Research & Technical Decisions: Sprint 4 – Database Storage + Basic Monitoring

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/spec.md)
**Created**: 2026-07-20

---

## 1. Database Table Selection

### Decision
We will reuse the existing `fyers_tokens` table mapped to the `FyersToken` model in [backend/app/models/fyers_token.py](file:///D:/Work_Space/trading-system/backend/app/models/fyers_token.py#L10) instead of creating a new `broker_tokens` table.

### Rationale
The application already has a system-wide `fyers_tokens` table designed specifically for system-wide headless/API-driven authentication tokens. The table is structured with `id=1` as the active singleton token. It already includes columns for monitoring: `status`, `access_token_saved_at` (representing `updated_at`), and `last_error`. Creating a new `broker_tokens` table for the same token automation would introduce redundant schemas and duplicate data access layers.

### Alternatives Considered
- **Creating `broker_tokens` table**: This was suggested in the user's requirements. However, in the existing codebase, the `broker_tokens` table is user-scoped (requires a `user_id` uuid column and tracks individual user credentials). The headless token automation is a system-wide utility that serves all services globally, making the user-independent `fyers_tokens` table a more appropriate fit.

---

## 2. Database Connection and ORM Integration

### Decision
We will use the existing SQLAlchemy ORM with the asynchronous database engine and session `AsyncSessionLocal` defined in [backend/app/db/session.py](file:///D:/Work_Space/trading-system/backend/app/db/session.py#L113) for the integration.

### Rationale
The project is standardized on SQLAlchemy. Standardizing on `AsyncSessionLocal` ensures compatibility with the existing connection pooling limits, SSL configurations, and asyncpg settings in both Development and Production environments.

### Alternatives Considered
- **Synchronous `SessionLocal` connection**: While the CLI runner script could use a synchronous session, mixing synchronous and asynchronous database connections could lead to connection pool exhaustion (as audited in `B_C_E_FINAL_AUDIT_REPORT.md` and `E4_CONCURRENCY_HARDENING_PLAN.md`). Using `AsyncSessionLocal` preserves database safety.
- **Raw `sqlite3` or `psycopg2` SQL queries**: Rejected because it bypasses the ORM models, ignores the database schema state managed by Alembic, and does not automatically support Fernet decryption/encryption logic that is tied to the `FyersToken` model methods.

---

## 3. Storage Security and Encryption

### Decision
All stored access tokens must be Fernet-encrypted at rest before database insertion using the existing `encrypt_secret` utility.

### Rationale
Storing plaintext authentication credentials in the database presents security vulnerabilities in the event of database backups leaking or database server compromises. Fernet encryption provides symmetric, authenticated encryption of the secrets.

---

## 4. Failure Isolation

### Decision
When token generation fails, the system will update the monitoring fields (`status = "Failed"`, `last_error = error_message`, `access_token_saved_at = now`) in the database, but it will NOT delete or nullify the existing `access_token` value.

### Rationale
A failure to generate a new token could be caused by temporary broker outages or transient API failures. If we delete the old token on failure, any background trading services currently running will immediately fail because they cannot retrieve any token. Keeping the old token in the database allows the trading service to continue using it for its remaining lifetime (tokens typically last 24 hours), while still notifying operators of the generation failure.
