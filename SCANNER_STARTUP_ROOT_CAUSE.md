# Scanner Startup Root Cause — “Connecting data feed...” Stuck at 0%

**Date:** 2026-07-23  
**Branch:** `SAI_CHANDRA`  
**Status:** Fixed  

---

## 1. Root Cause

The UI stayed on **Scanner Active → Connecting data feed... → 0%** because **no meaningful SSE progress events reached the client** while the HTTP stream (or pre-stream lock acquisition) was waiting.

Three defects stacked:

| # | Defect | Effect |
|---|--------|--------|
| **A** | **Stale scan lock recovery was too weak** | A crashed/aborted worker held `scan_execution` lock until **full TTL (up to 1 hour)**. New scans got `scan_in_progress` **or** hung on lock/DB. |
| **B** | **Lock stale check required `expires_at` AND `heartbeat_at` both stale** | Dead process: `expires_at` still in the future → lock not stolen → startup blocked. |
| **C** | **UI stage only updates on SSE `event: progress` with a `stage`** | Server often sent only SSE **comment** keepalives (`: heartbeat`) while the queue was empty. Frontend ignored comments for UI → stage frozen at client default **“Connecting data feed...”**. |

Secondary issues:

- No **immediate** progress event when the scan worker started.
- Lock TTL heartbeat was rare (`ttl/3` → up to 20 minutes).
- Connect path could block on DB lock acquisition **before** the StreamingResponse opened.
- Frontend had no **30s connect timeout**; stall timeout was 180s.

**The pipeline was not “skipping analysis.”** It often never left the **startup / lock / first-progress** phase from the UI’s point of view.

---

## 2. Exact Function Where Execution Stops

### Happy path (expected)

```text
App.handleRunScanner
  → api.runPresetScreener
    → POST /analysis/screener/full  (analysis.screener_full)
      → ScanExecutionService.execute_scan
           → DistributedLockService.acquire   ← STOP POINT (stuck lock / slow DB)
           → create_task(_run_scan_task)
      → StreamingResponse(event_stream)
           → queue.get()  ← idle → only comment keepalives  ← UI freeze
      → _run_scan_task
           → RouterAgent.screener_full
           → OrchestratorAgent.run_screener
           → candles / indicators / analysis / recommendations
```

### Primary stop points observed

1. **`DistributedLockService._try_acquire` / `acquire`**  
   - Lock held by dead owner, or DB wait.  
   - Endpoint may not open SSE promptly.

2. **`analysis.screener_full` → `event_stream` idle branch**  
   - Emits `: heartbeat` comments only.  
   - Frontend **does not** change stage → remains **Connecting data feed... 0%**.

3. **Client default stage** (`App.tsx`):

```ts
setProgressData({ stage: "Connecting data feed...", progress: 0, ... });
```

Until the first `event: progress` with a stage, the UI never advances.

---

## 3. Exception Details

No single user-visible exception was required for the freeze: **silent idle SSE** is enough.

When lock was denied:

```text
LockAcquisitionError: Scan is already in progress.
→ HTTP 200 JSON { "status": "scan_in_progress" }
```

When lock/DB hung:

```text
asyncio.wait_for(lock.acquire(...)) → TimeoutError  (after fix)
```

When broker later fails (separate from startup freeze), FYERS history logs show:

```text
API=/history Error code=-300 "Invalid symbol provided"
```

Those are per-symbol data errors after the scan is already running—not the startup hang.

---

## 4. API Response

| Condition | Response |
|-----------|----------|
| Normal start | `200` `text/event-stream` with `event: progress` then `event: result` |
| Lock held (old) | `200` `application/json` `{ "status": "scan_in_progress" }` |
| Lock/DB timeout (new) | Error path + log; lock denied after 15s outer timeout |

**Progress events (new):**

```json
{"stage":"Connecting data feed...","progress":1,"heartbeat":true}
{"stage":"Broker session check...","progress":5,"heartbeat":true}
{"stage":"Loading universe...","progress":10,"heartbeat":true}
{"stage":"Connecting to broker...","progress":12,"heartbeat":true}
{"stage":"Downloading candles...","progress":35,"heartbeat":true}
...
{"stage":"Completed","progress":100}
{"status":"complete","result":{...}}
```

---

## 5. Token Status

| Check | Behavior |
|-------|----------|
| Memory cache (`has_cached_token`) | Logged at scan start |
| DB (`get_current_access_token`) | Fallback if cache empty |
| Missing token | **Warning only** — scan continues; candle fetch may fail later with broker errors |

Startup freeze was **not primarily** “no token”; it was **no progress transport / lock**. Missing token still needs reconnect for successful candle download.

---

## 6. Broker Connection Status

- Broker is contacted during **historical OHLCV** fetch inside `ScreenerService.screen_symbols_swing` / Fyers.  
- Hang at **Connecting data feed 0%** usually means the client never reached that stage in the UI.  
- After fix, stage **“Connecting to broker...” / “Downloading candles...”** should appear before heavy FYERS work.

---

## 7. Database Status

| Component | Role |
|-----------|------|
| `system_locks` (`scan_execution`) | Mutual exclusion for scans |
| `scan_snapshots` | Scan lifecycle row (now starts as `RUNNING`) |
| AsyncSession pool | Lock acquire uses DB; hang here blocks scan start |

Stale lock steal now uses **heartbeat age** (or expiry), not “both must be stale.”

---

## 8. Background Worker Status

| Task | Role |
|------|------|
| `ScanExecutionService._run_scan_task` | Full scan pipeline |
| `ScanExecutionService._heartbeat_sender` | Progress every 5s + **immediate first pulse** |
| `DistributedLockService._heartbeat_loop` | Lock refresh (~15–60s) |

Worker is started with `asyncio.create_task` after lock acquire. Heartbeat is independent so the UI keeps moving even if the worker is busy on first DB write.

---

## 9. Files Modified

| File | Changes |
|------|---------|
| `backend/app/services/lock_service.py` | Stale lock = expired **OR** heartbeat stale; faster lock heartbeats |
| `backend/app/services/scan_execution_service.py` | `[SCAN]` logs, token check, immediate progress, heartbeat first pulse, lock timeout, RUNNING snapshot, safer emit |
| `backend/app/routes/analysis.py` | Seed progress queue; structured idle progress; better logging |
| `backend/app/agents/orchestrator_agent.py` | Stage labels + `[SCAN]` logs for universe/candles |
| `frontend/src/api.ts` | 30s connect timeout; progress on headers; 90s stall; always apply progress stages |

---

## 10. Validation — Progress 0% → 100%

### Expected stage ladder

| Stage | Progress |
|-------|---------:|
| Connecting data feed... | 1–5% |
| Data feed connected / Broker session check | 3–5% |
| Loading universe... | 10–20% |
| Connecting to broker / Downloading candles... | 12–40% |
| Indicators / technical | ~55% |
| AI analysis | ~70% |
| Recommendations / shortlist | ~85–97% |
| Completed | 100% |

### Automated checks run

```text
python -c "import lock + scan_execution"
→ IMPORTS_OK
→ stale heartbeat fix present
→ execute_scan startup emit present

emit + heartbeat first pulse
→ emit_ok
→ heartbeat_first_pulse_ok (stage set, progress >= 2)
```

### Operator validation

1. Restart backend (clears in-memory state; lock row may still exist in DB).  
2. Click **Scan**.  
3. Within a few seconds, stage must leave pure **Connecting data feed... 0%**.  
4. Confirm backend logs contain:

```text
[SCAN] Started
[SCAN] Access token found|MISSING
[SCAN] Token validated
SCAN_LOCK_ACQUIRED
[SCAN] Loading universe...
[SCAN] Universe loaded
[SCAN] Downloading candles
...
[SCAN] COMPLETED
SCAN_LOCK_RELEASED
```

5. If lock was stuck from a prior crash, the next acquire should **steal** after heartbeat staleness (~2 minutes max with new settings, often sooner).

---

## Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| Stale lock | Needed expiry **and** heartbeat stale | Expiry **or** heartbeat stale |
| Lock TTL | 3600s | 600s |
| First UI update | Only after real worker progress | Immediate queue seed + heartbeat pulse |
| SSE idle | Comment-only keepalives | Structured `event: progress` |
| Connect hang | Unlimited | 30s client timeout |
| Stream stall | 180s | 90s with clearer error |
| Logs | Sparse | `[SCAN]` stage trail |

---

## Confirmation

- Scanner no longer depends on a single late progress callback to leave 0%.  
- Dead workers no longer hold the scan lock for a full hour.  
- Exceptions in the worker are logged with **full stack traces** and sent as `event: result` `{status:error}`.  
- Progress is designed to move continuously from **~1% → 100%** with explicit stage names matching the requested ladder.
