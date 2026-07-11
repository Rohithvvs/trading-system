# Trading System — Performance Optimization Report

**Date:** 2026-07-11  
**Branch:** SAI_CHANDRA  
**Scope:** Loading speed, API architecture, rendering strategy, caching — **no UI redesign, no business-logic / calculation / auth removal changes**.

---

## 1. Performance audit (before)

### Architecture snapshot

| Layer | Stack |
|--------|--------|
| Frontend | React 18 + Vite + React Router |
| Backend | FastAPI on Render |
| DB | Neon Postgres (async SQLAlchemy + large sync pool) |
| Broker | FYERS API |
| Auth | Cookie session + `/auth/me` |

### Measured / observed bottlenecks

| Area | Finding | Impact |
|------|---------|--------|
| **Auth gate** | `ProtectedRoute` blocked entire app on spinner until `/auth/me` completed | Cold open: multi-second blank screen |
| **Eager bundles** | `App.tsx` statically imported Paper Trading, Profile, Workstation, Logs, Charts | Large main JS; slow first navigation |
| **Paper Trading mount** | 5+ separate `useEffect`s → sequential/redundant APIs (token, account, engine×2, dashboard) + 10s poll each | Waterfall; duplicate work; UI stuck on “Loading…” |
| **Token status** | Status then scan **sequentially**; polled every 60s; also called from paper mount | Extra latency; no client cache |
| **Token validation myth** | Status endpoint is DB-only (good), but front-end treated it as heavy and re-fetched constantly | Unnecessary network |
| **Global loading text** | Positions / Orders / History / Analytics / Account / Alerts returned full-page “Loading…” | Felt frozen even when shell could paint |
| **No keep-alive** | Render free tier sleeps → first API after idle can take 30s+ | “Loading…” forever perception |
| **No request dedup** | Profile had cache; rest of app did not | Duplicate parallel GETs |
| **DB session module** | `session.py` was **duplicated** (double engine init); no `pool_recycle` | Wasteful; Neon idle disconnects |
| **Fyers client** | New `FyersModel` on every validate; many `FyersService()` constructions | Extra object/SDK churn |
| **Payloads** | No GZip middleware | Larger JSON over WAN |

### Blocking patterns found

- `await authMe()` before any protected UI  
- Sequential `await getTokenStatus(); await getLatestScan()`  
- Paper tabs gated on `dashboard === null` with text loaders  
- Heavy components not lazy-loaded  
- Soft cold-start not handled (no stale cache / keep-alive)

---

## 2. Bottlenecks addressed

1. Auth blocking shell  
2. Sequential API waterfalls  
3. Full-page loading states  
4. Missing cache / dedup outside profile  
5. Render cold starts  
6. Token status re-fetch on every tab  
7. Fyers client recreation  
8. DB pool recycle / duplicated session module  
9. Large monolithic frontend chunks  
10. Missing performance timing headers  

---

## 3. Files modified

### Frontend (new)

- `frontend/src/utils/appCache.ts` — TTL cache, dedup, SWR, 3s soft-timeout → stale  
- `frontend/src/utils/keepAlive.ts` — `/health` every 10 minutes  
- `frontend/src/utils/prefetchAppData.ts` — post-login background prefetch  
- `frontend/src/components/Skeleton.tsx` — shared skeletons  

### Frontend (updated)

- `frontend/src/utils/profileDataCache.ts` — re-export of app cache  
- `frontend/src/utils/prefetchProfile.ts` — delegates to app prefetch  
- `frontend/src/hooks/useAuth.tsx` — optimistic localStorage session, background revalidate  
- `frontend/src/components/ProtectedRoute.tsx` — no spinner when cached user  
- `frontend/src/main.tsx` — lazy auth pages, start keep-alive  
- `frontend/src/App.tsx` — lazy Paper/Profile/Workstation/Logs/Detail/Command  
- `frontend/src/api.ts` — cached GET wrappers, invalidate on token save / paper refresh  
- `frontend/src/components/PaperTradingPage.tsx` — parallel load, cache seed, skeletons  
- `frontend/src/components/TokenStatus.tsx` — parallel + cache; force only on save  
- `frontend/src/components/WorkstationPage.tsx` — progressive waves + cache seed  
- `frontend/src/components/ResearchDashboard.tsx` — skeleton instead of text  
- `frontend/src/styles.css` — `.app-skel` shimmer  

### Backend

- `backend/app/core/response_cache.py` — in-process TTL cache  
- `backend/app/services/token_service.py` — 5 min token status cache; invalidate on save/clear  
- `backend/app/services/fyers_service.py` — `shared()`, client cache for token validate  
- `backend/app/routes/health.py` — market-status 60s cache  
- `backend/app/main.py` — GZip; `X-Response-Time-Ms` / `Server-Timing`; slow-request warn  
- `backend/app/db/session.py` — **deduplicated**, `pool_recycle=240`  

---

## 4. API optimizations

| Change | Detail |
|--------|--------|
| Client GET cache | Dashboard, account, analytics, alerts, token, market, workstation, engines |
| Dedup | Identical in-flight keys share one Promise |
| Soft timeout 3s | Return stale cache; continue revalidate in background |
| SWR | Serve cache immediately; refresh idle |
| Parallel paper boot | `Promise.all([dashboard, account, engine, health])` |
| Workstation waves | Status wave → market/saved/alerts/risk wave |
| GZip | Responses ≥ 500 bytes compressed |
| Timing headers | `X-Response-Time-Ms`, `Server-Timing` |

---

## 5. Database optimizations

| Change | Detail |
|--------|--------|
| Fixed duplicate `session.py` | Single engine/session factory |
| `pool_pre_ping` | Already present — retained |
| `pool_recycle=240` | Avoids Neon idle kill / reconnect storms |
| Pool size | Async 20+10; sync 80+20 (unchanged) |
| Token status | In-process cache → fewer status SELECTs |
| Connection forensics | Checkout/invalidate logs retained |

---

## 6. React optimizations

| Change | Detail |
|--------|--------|
| Code splitting | Lazy: Paper, Profile, Workstation, Logs, Stock Detail, Central Command, auth pages |
| Instant shell | Header/nav always from App; views Suspense with skeleton |
| Per-widget loading | Metrics / tables / charts / lists own skeletons |
| Memo/cache seed | `useState(() => getCached(...))` for zero-flash tabs |
| Auth context | `useMemo` / `useCallback` on auth value |

**Build evidence (chunks):**  
`PaperTradingPage ~62kB`, `UserProfilePage ~37kB`, `StockDetailPanel ~109kB`, `WorkstationPage ~14kB` separate from main bundle.

---

## 7. Token validation improvements

| Rule | Implementation |
|------|----------------|
| **Not on every navigation** | 8 min client cache + 5 min server cache |
| **Status = DB only** | Unchanged; still no FYERS on GET status |
| **FYERS validate only on save** | `saveAccessToken` → backend validate; caches cleared |
| **Background after login** | Prefetch warms status once |
| **401 / invalid** | Auth clear + cache wipe; FYERS errors clear token memory |

---

## 8. Cache implementation

```
appCache (memory + sessionStorage)
  TTL default 8 min
  inflight Map (dedup)
  softTimeout 3s → stale fallback
  SWR revalidate

Backend response_cache
  token_status 5 min
  market_status 60s
```

Cached keys include: auth me, paper dashboard/account/analytics/alerts, FYERS token/history, market status/overview, engines, API health, latest scan, universes, risk, workstation alerts.

---

## 9. Lazy loading

- Auth routes (Login/Signup/Forgot/Reset)  
- Paper Trading, User Profile, Workstation, System Logs  
- Stock Detail Panel, Central Command  
- Profile charts / sessions (pre-existing)  

---

## 10. Keep-alive

- Client: `startKeepAlive()` pings **`GET /health` only**, every **10 minutes**  
- Idle warm on boot via `requestIdleCallback`  
- Does **not** hit scanner / paper / FYERS  

---

## 11. Before vs after (estimated)

| Metric | Before | After (target / expected) |
|--------|--------|---------------------------|
| Dashboard / shell visible | 2–8s (auth + bundle) | **&lt;300ms** with cached session |
| Tab switch (UI chrome) | Blocked on data | **&lt;100ms** (local state + Suspense) |
| Profile / Account shell | Full wait | **&lt;300ms** shell + skeleton metrics |
| Analytics first paint | “Loading analytics…” | Shell + chart skeletons; data SWR |
| Token status on navigation | Network every time | Memory/session hit |
| Paper mount API calls | 5+ serial-ish effects | 1 parallel batch + cache |
| Render cold start | UI freezes on first API | Keep-alive + stale cache + soft timeout |
| Main bundle | Monolithic heavy | Split heavy routes |

*Network still bound by Render/Neon cold wake; UI no longer blocks on that.*

---

## 12. Testing performed

- `npm run build` — success; code-split chunks emitted  
- `npm test` — 25/25 passed (incl. TokenStatus)  
- Backend import: `response_cache` + `session.engine` OK  

Manual checklist (recommended in browser):

- [ ] Dashboard opens instantly with cached session  
- [ ] Scanner / Paper / Analytics / Account / Profile never full-page block  
- [ ] Token save still validates with FYERS  
- [ ] After 10 min idle, keep-alive keeps API warm  
- [ ] Duplicate GETs not doubled in Network tab (dedup)  

---

## Constraints respected

- No UI redesign  
- No business logic / trading calculation changes  
- Authentication retained  
- Existing functionality retained  
- Progressive, non-blocking data loading only  

---

## Goal alignment

The app now aims for a production trading UX (Kite / Groww / TradingView-style): **shell first, data second**, per-widget loading, background prefetch, and resilient cold starts — without changing how trades or scans are computed.
