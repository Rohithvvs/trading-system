# Phase 2 — Daily Analytics Module

**Status:** COMPLETE  
**Depends on:** Phase 1 multi-user paper isolation  

---

## Summary

Added a production-style **Daily Analytics** tab to Paper Trading (after Analytics, before Alerts):

**Tab order:** Positions → Open Orders → History → Analytics → **Daily Analytics** → Alerts → Account

Every query is scoped to the authenticated user’s paper account (`user_id` → account_id). No cross-user aggregation.

---

## Backend

| Item | Detail |
|------|--------|
| Service | `backend/app/services/daily_analytics_service.py` |
| Journal model | `PaperDailyJournal` on `paper_trading_daily_journals` |
| Migration | `paper_daily_journal_001` (revises `paper_user_isolation_001`) |
| APIs | `GET /paper-trading/daily-analytics` |
|  | `GET /paper-trading/daily-journal` |
|  | `PUT /paper-trading/daily-journal` |

### Metrics computed (user-scoped)

- Overview cards (profit/loss, return %, realized/unrealized, wins/losses, capital, cash, largest win/loss, averages)
- Daily Trading Score 0–100 + label (Excellent/Good/Average/Poor)
- Trade summary (executed/pending/cancelled/rejected, avg hold, avg size)
- Performance (net/gross, PF, win rate, R:R, expectancy, recovery, Sharpe/Sortino, max DD)
- Portfolio (value, cash, invested, allocation %, utilization %)
- Sector analysis (Banking/IT/Auto/Energy/Finance/Pharma/FMCG/Others)
- Symbol performance table
- Best / worst trade
- Risk (largest/smallest, risk %, exposure, concentration)
- Time slots (09:15–15:00)
- Emotional scores (discipline, patience, risk control, execution, consistency)
- AI insights (LLM when configured, else heuristic coach)
- Chart series (equity, hourly P&L, win/loss, sector, capital)
- Market context placeholder (non-blocking)
- Daily journal auto-save fields

### Filters

`period=today|yesterday|week|month|custom` + optional `start_date` / `end_date`

---

## Frontend

| Item | Detail |
|------|--------|
| Component | `frontend/src/components/DailyAnalyticsPanel.tsx` (lazy chunk) |
| Wiring | `PaperTradingPage` tab + Suspense skeleton |
| API | `fetchDailyAnalytics`, `fetchDailyJournal`, `saveDailyJournal` in `api.ts` |
| Cache | User-scoped keys via `appCache` (`paper_daily_analytics:…`) |
| Export | CSV download; Excel uses CSV path; PDF via print stylesheet |
| UX | Shell + skeletons; charts after data; journal debounce auto-save 800ms |

Build emits `DailyAnalyticsPanel-*.js` (~24 kB / 5 kB gzip).

---

## Security

| Check | Status |
|-------|--------|
| Auth required on daily analytics routes | Yes (`get_service` → JWT user) |
| Account via `service.user_id` only | Yes |
| Journal unique per (account_id, date) | Yes |
| Isolation tests | `test_daily_analytics_isolation.py` |
| Frontend cache scoped by user | Yes |

---

## Migrations to apply

```bash
cd backend
alembic upgrade head
# applies paper_user_isolation_001 then paper_daily_journal_001
```

---

## Tests

```bash
cd backend
.\venv\Scripts\python.exe -m pytest app/tests/test_daily_analytics_isolation.py app/tests/test_multi_user_paper_isolation.py -q
```

---

## Files modified / added

**Added**
- `backend/app/services/daily_analytics_service.py`
- `backend/alembic/versions/20260711_paper_daily_journal.py`
- `backend/app/tests/test_daily_analytics_isolation.py`
- `frontend/src/components/DailyAnalyticsPanel.tsx`
- `docs/PHASE2_DAILY_ANALYTICS_REPORT.md`

**Updated**
- `backend/app/models/paper_trading.py` — `PaperDailyJournal`
- `backend/app/models/__init__.py`
- `backend/app/routes/paper_trading.py` — daily endpoints
- `frontend/src/components/PaperTradingPage.tsx` — tab + lazy load
- `frontend/src/api.ts` — client helpers
- `frontend/src/utils/appCache.ts` — cache keys
- `frontend/src/styles.css` — score colors, journal, print
