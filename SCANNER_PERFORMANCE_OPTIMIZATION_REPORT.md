# Multi-Agent Scanner Performance Optimization Report

**Date:** 2026-07-14  
**Branch:** SAI_CHANDRA  
**Scope:** Full NIFTY500 (~755) scan path — data acquisition, indicators, scoring, multi-agent shortlist.  
**Constraint:** No trading-rule / strategy / signal-logic changes.

---

## 1. Observed problem

| Metric | Observed |
|--------|----------|
| Universe | NIFTY500 (~755 symbols) |
| UI stage stuck | `Fetching Historical OHLCV Data...` @ ~40% |
| Elapsed | **30+ minutes** (1800s+) |
| Target | **Full scan 2–5 minutes**; warm-cache OHLCV &lt; 10–20s |

Progress stayed at 40% because the orchestrator only advances past that stage after **`screen_symbols_swing` fully completes** (fetch + indicators + scoring). It was not a UI-only freeze.

---

## 2. Pipeline map

```
UI / Scheduler
  → ScanExecutionService (lock + progress queue)
    → RouterAgent.screener_full
      → OrchestratorAgent.run_screener
        → UniverseService (NIFTY500 …)
        → ScreenerService.screen_symbols_swing   ◀── bottleneck
            ├─ Batch meta / DB bulk load
            ├─ FYERS worker pool (incremental history)
            ├─ Vectorized indicators
            └─ Weighted scoring
        → run_full on shortlist (news / fundamental / backtest / rec)
        → Ranking + persist LatestScan
```

---

## 3. Bottlenecks identified

| # | Bottleneck | Why it was slow | Impact |
|---|------------|-----------------|--------|
| 1 | **FYERS history concurrency = 3** | `_FYERS_HISTORY_SEMAPHORE(3)` + asyncio sem ~3–4 | ~94% of prior 527s runs |
| 2 | **False “stale” full-year redownload** | If gap &gt; 5 days, code reset range to **365 days** even with partial cache | 10–50× larger responses |
| 3 | **Always hit FYERS** (pre-fix) | Even fresh DB rows still called incremental API | 755 network RTTs |
| 4 | **N+1 DB over Neon** | Per-symbol continuity + full history load + upsert | 50–150ms × 755 × many queries |
| 5 | **`asyncio.sleep(0.5)` per symbol** | Pure delay on every symbol | ~minutes wasted |
| 6 | **Per-symbol INFO logging** | STEP/CANDLE/FAIL lines × 755 | Heavy disk/CPU on hot path |
| 7 | **Progress only at stage gates** | UI frozen at 40% for entire screener | Looked hung |
| 8 | **Shortlist re-fetched OHLCV** | `run_full` ignored warm DB after screener | Extra FYERS/DB |
| 9 | **ffill DB upsert every scan** | Wrote synthetic bars for hundreds of symbols | Write amplification |

Trading strategy, weights, gates, and shortlist rules were **not** changed.

---

## 4. Optimizations implemented

### 4.1 Parallel FYERS worker pool (configurable)

- Env: **`MAX_CONCURRENT_REQUESTS=25`** (default)
- `asyncio.Semaphore(N)` worker pool
- Matching `threading.BoundedSemaphore(N)` for SDK history
- Thread pool sized to concurrency
- No artificial sleep on the hot path

### 4.2 True incremental OHLCV

- Empty cache → one 365d bootstrap window  
- Partial cache → **only** `(last_bar + 1 day) → today`  
- **Removed** “if stale &gt; 5 days, redownload 365 days”

### 4.3 Postgres cache-first path

- Batch meta with **symbol variant resolution** (`RELIANCE` / `RELIANCE-EQ` / `NSE:RELIANCE-EQ`)
- Bulk history load (chunked `IN` queries)
- Fresh complete symbols **skip FYERS**
- API path: merge deltas in memory → batch upsert → no per-symbol full reload

### 4.4 Progress + logging

- Progress every **10 symbols** or **2 seconds** during fetch  
- Progress also during scoring (every 50)  
- Per-symbol INFO spam reduced to debug / shortlist-only  
- `SCANNER_TIMING_REPORT` log with per-stage ms + %

### 4.5 Multi-agent shortlist

- Prefer DB history for swing OHLCV  
- Bounded concurrency for prefetch and agent stage  

### 4.6 Other

- Continuity validation skips full-history gap scan when already incomplete  
- In-memory ffill only (no per-scan ffill upsert)  
- Fundamental Yahoo symbols normalized (`RELIANCE-EQ` → `RELIANCE.NS`)

---

## 5. Files changed

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | `MAX_CONCURRENT_REQUESTS`, timeout/retry settings |
| `backend/app/services/fyers_service.py` | Concurrency 25, true incremental, quieter logs |
| `backend/app/services/market_data_service.py` | Batch meta/load, symbol variants, multi upsert |
| `backend/app/services/screener_service.py` | Worker pool, cache-first, progress, timing report |
| `backend/app/agents/orchestrator_agent.py` | Progress passthrough, DB OHLCV reuse, agent bounds |
| `backend/app/agents/fundamental_analysis_agent.py` | Symbol normalize |

---

## 6. Benchmark (before vs expected after)

### Before (measured / audited)

| Stage | Time | Share |
|-------|------|-------|
| Historical FYERS fetch | ~497s | **~94%** |
| Full analysis (shortlist) | ~27s | ~5% |
| Indicators / scoring | ~1–2s | ~0.5% |
| **Total** | **~527s+** (often 30min with rate limits / sleeps / N+1) | |

Cold path with concurrency 3 + full redownloads + 0.5s sleep ≈ **15–40+ minutes**.

### After (expected; strategy-identical)

| Scenario | OHLCV acquisition | Full scan (screener + shortlist agents) |
|----------|-------------------|----------------------------------------|
| **Warm DB** (most re-runs same day) | **5–20s** (batch meta + bulk load) | **1–3 min** |
| **Stale-complete** (1–3 day delta, 25 workers) | **30–90s** true incremental | **2–5 min** |
| **Cold empty DB** (first bootstrap 755×365d) | **2–8 min** (API-bound) | **3–10 min** |

### Expected timing report shape (warm)

```
Historical / data acquisition : ~60–80% of screener wall time (mostly DB)
Indicators                    : ~5–15%
Scoring                       : ~5–15%
Shortlist multi-agent         : dominates after screener if many BUY/WATCH
```

Look for log lines:

```
SCANNER_CACHE_PARTITION | cache_hits=... | needs_fetch=... | workers=25
SCANNER_CACHE_BULK_LOAD | load_ms=...
SCANNER_FYERS_FETCH | fetch_ms=...
SCANNER_TIMING_REPORT | total_ms=... | ...
```

---

## 7. Operator controls

```env
MAX_CONCURRENT_REQUESTS=25
SCANNER_FETCH_TIMEOUT_SEC=10
SCANNER_MAX_RETRIES=3
```

If FYERS returns rate-limit errors, lower concurrency to `10–15`. If clean, `25` is the default target.

---

## 8. Result integrity

Preserved:

- Broad-trend gate thresholds  
- Weighted screener score  
- Matched / shortlist selection (`top_n`)  
- Strict BUY gate  
- Ranking / recommendation formulas  

Changed only **I/O, concurrency, caching, logging, and progress** — not signal math.

---

## 9. Restart required

Backend must be **restarted** to load:

- New concurrency defaults  
- Screener worker pool  
- True incremental fetch  

Without restart, the old semaphore=3 path can still run for 30+ minutes.
