# Implementation Plan: Fyers Refresh Token Auto-Renewal

## 1. OVERVIEW
This feature replaces the manual daily access-token workflow with a scheduled automated renewal mechanism using a 15-day refresh token. A scheduler job will run at 08:30 IST to exchange the stored refresh token for a new access token via FYERS API, ensuring the system is ready before market open. A UI banner/badge will provide expiry warnings to the user, and failures will automatically pause the trading engine to prevent invalid state operations. 

**Files to be created:**
- `backend/alembic/versions/[timestamp]_add_refresh_token_fields.py`

**Files to be modified:**
- `backend/app/models/fyers_token.py`
- `backend/app/schemas/fyers_token.py`
- `backend/app/routes/fyers.py`
- `backend/app/services/fyers_service.py`
- `backend/app/main.py`
- `frontend/src/api.ts`
- `frontend/src/pages/WorkstationPage.tsx` (or the equivalent component where tokens are managed)

**Files that must NOT be touched:**
- Any file outside this list. Specifically, the manual manual access-token generation flow, SDK configuration files, and unrelated frontend components.

## 2. DATABASE LAYER
**Alembic Migration Steps:**
- Create a new migration file matching the naming convention: `[timestamp]_add_refresh_token_fields.py`
- **Columns to add** to `fyers_tokens`:
  - `refresh_token = sa.Column(sa.Text(), nullable=True)`
  - `refresh_token_expires_at = sa.Column(sa.DateTime(timezone=True), nullable=True)`
  - `last_auto_renewal_at = sa.Column(sa.DateTime(timezone=True), nullable=True)`
  - `last_auto_renewal_status = sa.Column(sa.String(length=32), nullable=True)`
- **Downgrade Steps**: 
  - `op.drop_column('fyers_tokens', 'last_auto_renewal_status')`
  - `op.drop_column('fyers_tokens', 'last_auto_renewal_at')`
  - `op.drop_column('fyers_tokens', 'refresh_token_expires_at')`
  - `op.drop_column('fyers_tokens', 'refresh_token')`
- **Impact on Existing Rows**: 
  - All existing rows will simply have `NULL` for these new columns. The system will continue to work gracefully without refresh tokens until a user inputs one.

## 3. BACKEND SERVICE LAYER
**Modifications to `backend/app/services/fyers_service.py`:**
- **New Method**: `async def auto_refresh_access_token(self, db: AsyncSession) -> bool:`
  - **Inputs**: AsyncSession.
  - **Logic**: Reads the active refresh token. If missing, returns False. Otherwise, constructs the `appIdHash` and uses `httpx.AsyncClient` with a 30-second timeout to `POST https://api-t1.fyers.in/api/v3/validate-refresh-token`.
  - **Output**: Returns `True` if successful, `False` on failure.
  - **Error Handling**: On failure (network error, timeout, 401), triggers engine state transition to `TOKEN_EXPIRED_PAUSED` and logs the error safely.

- **New Method**: `encrypt_token(self, token: str) -> str:` and `decrypt_token(self, token: str) -> str:`
  - **Logic**: Implements Python Fernet symmetric encryption using `settings.fyers_token_encryption_key`. These pure-logic operations live strictly in the service layer or `backend/app/utils/crypto.py`. The route handler MUST NOT perform encryption itself.

- **New Method**: `def _compute_app_id_hash(self) -> str:`
  - **Logic**: Computes `SHA256(FYERS_CLIENT_ID + ":" + FYERS_SECRET_KEY)`.

- **New Method**: `async def get_token_status_with_refresh_info(self, db: AsyncSession) -> dict[str, Any]:`
  - **Logic**: Fetches the active row. Computes `refresh_token_days_remaining` based on `refresh_token_expires_at - now()`. Returns the extended schema mapping.

**Modifications to `token_service.py` (if applicable) or `fyers_service.py`:**
- **Engine Transition Trigger**:
  - `await market_engine.request_stop("TOKEN_EXPIRED_PAUSED")` will be called upon failure, along with dispatching an error notification using `PaperTradingService(db).add_notification`.
- Existing `fetch_ltp`, `get_candles_cached`, etc., remain untouched.

## 4. SCHEDULER LAYER
**Modifications to `backend/app/main.py` (Scheduler configuration):**
- **Job Definition**: 
  - `async def job_auto_token_refresh():`
  - Acquires distributed lock: `await acquire_singleton_lease("trading-system:fyers-token-refresh")` with TTL of 60s.
  - Starts with `logger.info("JOB_STARTED | auto_token_refresh | lock_acquired")`
  - Instantiates `FyersService` and calls `await fyers_service.auto_refresh_access_token(db)`
  - Ends with `logger.info("JOB_COMPLETED | auto_token_refresh | status=...")`
- **Registration**: 
  - `scheduler.add_job(job_auto_token_refresh, CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone="Asia/Kolkata"), id="auto_token_refresh", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)`
- Existing jobs (`job_market_engine_spin_up`, `job_intraday_heartbeat`, etc.) are preserved.

## 5. API LAYER
**Modifications to `backend/app/schemas/fyers_token.py`:**
- Add `refresh_token: Optional[str] = None` to `FyersTokenCreate` (already present).
- Add to `FyersTokenResponse`:
  - `refresh_token_present: bool = False`
  - `refresh_token_expires_at: Optional[datetime] = None`
  - `refresh_token_days_remaining: Optional[int] = None`
  - `refresh_token_status: str = "expired"`
  - `last_auto_renewal_at: Optional[datetime] = None`
  - `last_auto_renewal_status: Optional[str] = None`

**Modifications to `backend/app/routes/fyers.py`:**
- **POST `/fyers/token`**:
  - Extract `refresh_token`. Call `fyers_service.save_tokens()` or similar to perform encryption and DB write. The route MUST NOT import or call `encrypt_token()` directly. If present, compute `refresh_token_expires_at` = `datetime.utcnow() + timedelta(days=15)` and save it via the service.
- **GET `/fyers/token/status`**:
  - Map the DB row to the new Pydantic schema using the method defined in `FyersService`. Derive `refresh_token_days_remaining`. Determine `refresh_token_status` (`valid`, `expiring_soon`, `critical`, `expired`). Raw refresh token is excluded.

## 6. FRONTEND LAYER
**Modifications to `frontend/src/api.ts`:**
- Update `getTokenStatus` to type the new response properties.
- Ensure `saveAccessToken` accepts `refresh_token` as an optional parameter.
- Confirm `fetchWithDiagnostics` is used exclusively.

**Modifications to UI Component (`frontend/src/components/TokenStatus.tsx`):**
- Add `Refresh Token (Optional)` input field alongside the `Access Token` field.
- **Expiry Badge/Banner Logic**:
  - `refresh_token_days_remaining > 5`: Green badge "Refresh Token Valid — {N} days left".
  - `3 <= refresh_token_days_remaining <= 5`: Amber badge "Expiring Soon — {N} days left".
  - `0 < refresh_token_days_remaining < 3`: Red badge and persistent banner (non-dismissable) "Refresh Token Expiring in {N} days — Insert new token now".
  - `refresh_token_days_remaining <= 0` or status `expired`: Persistent red banner "Refresh Token Expired — Auto-renewal disabled. Insert new token."
- CSS will use standard inline styles or global stylesheet (no Tailwind). No `window.alert`. No polling interval < 5s.

## 7. SECURITY CHECKPOINTS
- **FYERS_PIN**: Read strictly from `settings.fyers_pin` environment variable. It is NEVER written to the database. FYERS_PIN must be validated as non-empty and exactly 4 numeric digits before being used in any refresh call. If invalid, log ERROR with message "FYERS_PIN is missing or invalid" (do not log the PIN value) and abort the renewal — do not send the request to FYERS.
- **AppIdHash**: Computed on the fly using `settings.fyers_app_id` and `settings.fyers_secret_key`. Excluded from logs.
- **Token Masking**: Log statements referencing tokens will mask the value using `hash_token_prefix(token)` or similar.
- **PIN Masking**: The PIN is never logged.

## 8. ERROR HANDLING PLAN
- **`httpx` Timeout (30s exceeded)**: Job catches `httpx.TimeoutException`, logs "Refresh token API timed out", pauses engine (`TOKEN_EXPIRED_PAUSED`), sends UI notification.
- **401 Unauthorized**: Job catches exception, updates `last_auto_renewal_status` to `"failed"`, sets `is_active=False`, pauses engine, sends UI notification "Refresh token expired or invalid."
- **Missing `FYERS_PIN`**: Before calling HTTPX, check if `settings.fyers_pin` exists. If None, abort silently with warning log, or transition to paused if an access token is desperately needed.
- **DB Write Failure**: Attempt rollback, log critical DB error, leave engine as-is (graceful degradation).
- **Frontend Receives `TOKEN_EXPIRED_PAUSED`**: The market engine status polling loop detects the state, UI disables trading controls and forces a red banner indicating action is needed.

## 9. MIGRATION AND ROLLBACK PLAN
- **Roll Forward**: Run `alembic upgrade head`. The new columns are appended with `nullable=True`. Existing `fyers_tokens` rows remain valid and behave as if no refresh token was provided.
- **Roll Back**: Run `alembic downgrade -1`. Dropping columns is non-destructive to the original schema. The active access token remains. **Downgrade warning:** if `refresh_token` column contains encrypted values at the time of downgrade, those values will be lost as the column is dropped. This is acceptable — the user must re-enter their refresh token after re-upgrading. Add a comment to the migration `downgrade()` function documenting this explicitly.

## 10. SOURCE TREE
- `backend/alembic/versions/*_add_refresh_token_fields.py`: Creates DB migration for refresh token tracking.
- `backend/app/models/fyers_token.py`: Maps new DB columns to SQLAlchemy.
- `backend/app/schemas/fyers_token.py`: Expands schemas for API request/response.
- `backend/app/routes/fyers.py`: Updates `/fyers/token` and `/fyers/token/status` endpoints to process refresh tokens.
- `backend/app/services/fyers_service.py`: Implements `auto_refresh_access_token()` and logic to build AppIdHash.
- `backend/app/main.py`: Registers the 08:30 IST `auto_token_refresh` cron job in APScheduler.
- `frontend/src/api.ts`: Modifies token save and status payload types.
- `frontend/src/components/TokenStatus.tsx`: Renders the new refresh token input, conditional badges, and banners based on status.

---

OPEN DECISIONS:
- **[DECISION-001] Encryption:** [RESOLVED: Option B] The `refresh_token` will be encrypted at rest using Python Fernet symmetric encryption. The key will be read from `FYERS_TOKEN_ENCRYPTION_KEY`. `cryptography` library will be flagged for addition.
