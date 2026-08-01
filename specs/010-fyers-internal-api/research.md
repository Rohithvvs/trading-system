# Research & Technical Decisions: Sprint 5 – Internal API Endpoint

## Decisions

### 1. Security Protection Mechanism
* **Decision**: Reuse the existing `SCHEDULER_SECRET` environment variable and `X-Scheduler-Secret` HTTP header.
* **Rationale**: Reuses the helper function `_require_scheduler_secret()` already defined in `backend/app/routes/token.py`. This avoids code duplication, simplifies configuration management by not introducing new environment variables, and ensures alignment with standard system scheduler authentication patterns.
* **Alternatives Considered**: 
  * *Dedicated API Key*: Introduce `INTERNAL_API_KEY` (header `X-Internal-API-Key`). Rejected to prevent configuration sprawl and duplicate validation code.
  * *IP/Network Restriction*: Restricting requests to localhost/known IPs. Rejected because deployment environments (like Render or containerized environments) use dynamic ingress routing, making IP-based filtering brittle or overly complex.

### 2. Route Definition Placement
* **Decision**: Define the `/internal/refresh-fyers-token` route in the existing file `backend/app/routes/token.py` using a secondary, unprefixed `APIRouter` instance.
* **Rationale**: The route directly relates to token automation and generation, which is the domain of `backend/app/routes/token.py`. Storing all token-related endpoints in one file maintains logical cohesion. Since the file's primary router prefix is `/api/token`, we can define a secondary `APIRouter()` without a prefix to register the `/internal/refresh-fyers-token` route cleanly.
* **Alternatives Considered**:
  * *New Dedicated File (`backend/app/routes/internal.py`)*: Rejected because the project does not currently have other internal endpoints, and a new module would add unnecessary file overhead.
  * *Directly in `backend/app/main.py`*: Rejected to keep `main.py` clean and focused solely on app startup and middleware configuration.

### 3. Integration with Token Generation & Persistence
* **Decision**: Directly invoke `token_service.generate_and_persist_fyers_token(db)`.
* **Rationale**: This service function was created in Sprint 4. It already handles calling the core token generator, manages the retry logic up to 3 attempts, performs the database transaction to upsert the active token, writes history records, and manages encryption/caching.
* **Alternatives Considered**: Calling the raw `generate_fyers_access_token()` and manual db insert. Rejected because it would duplicate the transaction management, encryption, caching, and error persistence logic.

### 4. Error Mapping & Responses
* **Decision**: Explicitly catch any exception raised by `generate_and_persist_fyers_token()`, log it, and return a clean HTTP 500 error response with a JSON body matching the specification.
* **Rationale**: The specification demands exact success and failure JSON payloads. Since `generate_and_persist_fyers_token()` re-raises underlying exceptions on ultimate failure, we must catch all exceptions to prevent raw tracebacks from leaking to the caller and to return the correct HTTP status code (500) and response schema (`{"status": "error", "message": "Failed to generate access token after retries"}`).
