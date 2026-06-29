# Debugging Guide

If the Scanner Engine fails or produces unexpected results, follow this step-by-step workflow.

## Step 1: Check the Scanner API Response
Use the dashboard or directly curl the endpoint:
`GET http://localhost:8000/scanner/latest`

- If it returns `No completed scans found`, the scanner has never successfully completed.
- Check `data_warning` and `data_source` in the response payload.

## Step 2: Check the Logs
1. **Latest Scan Log**: `logs/latest_scan.log`. This file contains structured, step-by-step logs of the most recent execution. Look for:
   - `SCAN START`
   - `SCAN COMPLETE`
   - Memory Audits: `MEMORY_AUDIT stage=... rss_mb=...`
   - Symbol failures: `SYMBOL ERROR symbol=...`
2. **Scheduler Log**: Check console output or application logs for `SCHEDULER_JOB_FAILED`.

## Step 3: Verify the Token
If FYERS data is failing:
1. Connect to PostgreSQL.
2. Query the token table (usually `auth_tokens` or similar, handled by `token_service`).
3. Check `access_token_saved_at`. Is it older than 24 hours? If so, authenticate via the UI.

## Step 4: Verify Database Cache Continuity
If a specific symbol is not showing up:
1. Check the `daily_candles` table for that symbol.
   ```sql
   SELECT count(*), min(timestamp), max(timestamp) FROM daily_candles WHERE symbol = 'RELIANCE';
   ```
2. Is the count < 240? If so, it fails the `data_quality_failed` check.
3. Check `latest_scan.log` for `SKIP data_quality_failed | symbol=RELIANCE`.

## Step 5: Enable Determinism Debugging
To see exactly why a symbol got the score it did:
1. Set the environment variable: `SCANNER_DETERMINISM_DEBUG=true`
2. Restart the backend.
3. Trigger a scan.
4. The logs will now dump large JSON payloads showing the exact mathematical breakdown of every scored symbol (`SCANNER_DETERMINISM {"event": "symbol_scored", ...}`).

## Step 6: Specific Code Files to Inspect
- **Data fetching issues**: `backend/app/services/screener_service.py` (look at `fetch_all_symbols`).
- **Math/Indicator issues**: `backend/app/services/technical_analysis_service.py` (look at `analyze_bulk_from_frame`).
- **Persistence issues**: `backend/app/services/latest_scan_service.py`.
- **Final LLM/Agent decisions**: `backend/app/agents/recommendation_agent.py`.
