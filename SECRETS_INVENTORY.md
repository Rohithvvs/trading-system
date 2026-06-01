# SECRETS INVENTORY

## Critical Secrets
*(These must NEVER be hardcoded in Git. Must be injected via AWS Secrets Manager, GitHub Secrets, or `.env`)*

- `DATABASE_URL`: Connection string mapping PostgreSQL credentials.
- `REDIS_URL`: Connection string.
- `FYERS_SECRET_ID`: Used exclusively by the backend to securely sign OAuth tokens.
- `GROQ_API_KEY`: API token required for the `OrchestratorAgent`.
- `NEWS_API_KEY`: API token required for fetching latest catalyst news streams.

## Security Posture
**Missing Secrets Detected:**
1. **JWT Secret / Encryption Keys**: The system's HTTP Middleware and diagnostic routes lack a unified encryption signature key. There is no `JWT_SECRET` found.
2. **Postgres Default Expiry**: The `docker-compose.yml` mounts Postgres using `trading_user:trading_password`. If pushed to production without modification, this presents a severe vulnerability.

## Token Lifecycle
The Fyers App access token operates as a temporary volatile secret, stored actively inside the PostgreSQL `fyers_tokens` table. It must be manually rotated every morning by an authorized operator through the UI dashboard.
