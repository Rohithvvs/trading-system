# API Inventory

> Complete inventory of every HTTP/WS endpoint exposed by the FastAPI app.
> Cross-references: [SystemOverview](./SystemOverview.md) · [BackendArchitecture](./BackendArchitecture.md) · [DatabaseSchema](./DatabaseSchema.md)
>
> Router assembly reference (`backend/app/routes/__init__.py`): `api_router = APIRouter()` (no shared prefix) includes all `routes/*` routers, each declaring its own `prefix=`. `backend/app/main.py` mounts: `api_router`, `fyers_router`, `scheduler_router.router`, `walk_forward_router`, `event_calendar_router`. Two endpoints are mounted directly on `app` (not via routers).

## Table of Contents

1. [Summary by File](#1-summary-by-file)
2. [Health](#2-health)
3. [Analysis](#3-analysis)
4. [Paper Trading](#4-paper-trading)
5. [Stocks](#5-stocks)
6. [Scanner](#6-scanner)
7. [System / Shadow Run](#7-system--shadow-run)
8. [Auth](#8-auth)
9. [Token](#9-token)
10. [Broker Tokens](#10-broker-tokens)
11. [Settings](#11-settings)
12. [Workstation](#12-workstation)
13. [Logs (incl. WebSocket)](#13-logs-incl-websocket)
14. [FYERS](#14-fyers)
15. [Scheduler](#15-scheduler)
16. [Walk-Forward](#16-walk-forward)
17. [Event Calendar](#17-event-calendar)
18. [App-mounted endpoints](#18-app-mounted-endpoints)
19. [Authentication key](#19-authentication-key)

---

## 1. Summary by File

| File | Prefix | Endpoints |
|------|--------|-----------|
| `routes/health.py` | (root) | 3 |
| `routes/analysis.py` | `/analysis` | 12 |
| `routes/paper_trading.py` | `/paper-trading` | 38 |
| `routes/stocks.py` | `/stocks` | 1 |
| `routes/scanner.py` | `/scanner` | 1 |
| `routes/system.py` | `/system/shadow-run` | 4 |
| `routes/auth.py` | `/auth` | 13 |
| `routes/token.py` | `/api/token` | 4 |
| `routes/broker_tokens.py` | `/api/broker-tokens` | 7 |
| `routes/settings.py` | `/settings` | 1 |
| `routes/workstation.py` | `/workstation` | 13 |
| `routes/logs.py` | `/api/logs` | 5 (incl. 1 WebSocket) |
| `routes/fyers.py` | `/fyers` | 5 |
| `routes/scheduler.py` | `/scheduler` | 2 |
| `routers/walk_forward.py` | `/api/walk-forward` | 3 |
| `routers/event_calendar.py` | `/api/events` | 3 |
| `app` (direct) | — | 2 (`/scanner/health`, `/metrics`) |
| **TOTAL** | | **117 endpoints** |

---

## 2. Health

Router: `routes/health.py`, no prefix.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB access | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|-----------|--------------|
| GET | `/health` | Liveness probe | none | `HealthResponse` | no | `settings`, `advisory_payload` | none | none |
| GET | `/health/heartbeat` | Heartbeat ping | none | `dict` | no | `market_engine.heartbeat`, `market_engine.status` | none | in-memory engine heartbeat update |
| GET | `/market-status` | Public market status | none | `dict` | no | `trading_hours.get_market_status`; `response_cache` | none | writes response_cache (TTL 60s) |

---

## 3. Analysis

Router: `routes/analysis.py`, prefix `/analysis`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB access | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|-----------|--------------|
| POST | `/analysis/technical` | Technical analysis only | `AnalysisRequest` | `AnalysisResponse` | no | `RouterAgent.technical_only` | indirect (agent→Fyers/candle_store) | none direct |
| POST | `/analysis/news` | News analysis only | `AnalysisRequest` | `AnalysisResponse` | no | `RouterAgent.news_only` | indirect | none direct |
| POST | `/analysis/backtest` | Backtest only | `AnalysisRequest` | `AnalysisResponse` | no | `RouterAgent.backtest_only` | indirect | none direct |
| POST | `/analysis/final-recommendation` | Final recommendation only | `AnalysisRequest` | `AnalysisResponse` | no | `RouterAgent.final_recommendation` | indirect | none direct |
| POST | `/analysis/full` | Full analysis pipeline | `AnalysisRequest` | `FullAnalysisResponse` | no | `RouterAgent.full_analysis` | indirect (AnalysisHistory/BacktestHistory insert) | logs ENTRY/EXIT |
| POST | `/analysis/rankings` | Rankings only | `AnalysisRequest` | `RankingsResponse` | no | `RouterAgent.rankings` | indirect | none direct |
| POST | `/analysis/screener/full` | Streaming screener run (SSE) | `ScreenerRequest` | `StreamingResponse` (text/event-stream) | no | `ScanExecutionService.execute_scan` (+`LockAcquisitionError`) | upsert HistoricalCandle; insert ScannedCandidate + ScanSnapshot + ScanSnapshotRecord | SSE progress frames; 409 if scan already running |
| GET | `/analysis/symbol/{symbol}/detail` | Per-symbol full detail | (path) | `JSONResponse` (dict) | no | `RouterAgent.full_analysis`; `MarketInfoService.get_company_profile`; `FyersService.fetch_quote_profile`; `ResearchService.build`; helpers (`_calculate_52_week_range`, `_build_technical_extras`, `_build_backtest_extras`) | DB read (candles) + AnalysisHistory write | external Fyers/MarketInfo calls |
| GET | `/analysis/scan/latest` | Latest scan payload (ScreenerResponse + `available`) | none | `dict` | no | `LatestScanService.get_latest_scan("analysis")` → `scan_store.load_latest_scan` (when `SCANNER_UNIFIED_LATEST_ENABLED=true`); else direct `load_latest_scan` | DB read (`market_data.scan_results` JSONB) | Redis `analysis:scan:latest:v1`; unified fallback metric |
| GET | `/analysis/symbol/{symbol}/light` | Light symbol detail | (path) | `JSONResponse` (dict) | no | `RouterAgent.full_analysis`; `FyersService.fetch_quote`; `MarketInfoService.get_company_profile` | DB read | Fyers API call |
| POST | `/analysis/symbol/batch-light` | Batch light details | inline `{"symbols":[...]}` (max 20) | `JSONResponse` (dict) | no | `FyersService.fetch_quote`; `MarketInfoService.get_company_profile` | none | external Fyers API calls |
| GET | `/analysis/candidates/today` | Today's scan candidates | none | `JSONResponse` (list) | no | raw `select(ScannedCandidate)` | DB read | none |

---

## 4. Paper Trading

Router: `routes/paper_trading.py`, prefix `/paper-trading`. User-authenticated endpoints use session cookie via `get_current_user_id_sync`; some engine endpoints are unauthenticated.

### Dashboard / Account

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB access | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|-----------|--------------|
| GET | `/paper-trading/dashboard` | Full dashboard | `selected_symbol?` query | `PaperTradingDashboardResponse` | yes | `PaperTradingService.get_dashboard` | read | Fyers LTP/quote lookups |
| GET | `/paper-trading/account` | Account | none | `PaperTradingDashboardResponse` | yes | `PaperTradingService.get_dashboard` | read | — |
| GET | `/paper-trading/account/summary` | Daily summary | none | `JSONResponse` (dict) | yes | `PaperTradingService.get_dashboard`; `trading_hours.get_market_status` | read | computes daily PnL in IST |
| POST | `/paper-trading/account/reset` | Reset account | `PaperTradingAccountResetRequest` | `PaperTradingDashboardResponse` | yes | `PaperTradingService.reset_account` | write | — |
| PUT | `/paper-trading/account/capital` | Update starting capital | `PaperAccountCapitalUpdateRequest` | `JSONResponse` (dict) | yes | `PaperTradingService.update_starting_capital` | write | — |

### Orders / Positions

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/paper-trading/orders` | Place order | `PaperOrderCreateRequest` + `Idempotency-Key` header | `PaperOrderActionResponse` | yes | `PaperTradingService.place_order` | write | idempotency enforcement; Fyers quote fetch possible |
| GET | `/paper-trading/orders/pending` | Pending | none | `list[PaperOrderResponse]` | yes | `get_pending_orders` | read | — |
| GET | `/paper-trading/orders/history` | History | none | `list[PaperOrderResponse]` | yes | `get_order_history` | read | — |
| GET | `/paper-trading/trades` | Trades | none | `list[PaperTradeHistoryItem]` | yes | `get_trades` | read | — |
| GET | `/paper-trading/positions` | Positions | none | `list[PaperPositionResponse]` | yes | `get_positions` | read | live price snapshot |
| PUT | `/paper-trading/orders/{order_id}` | Modify | `PaperOrderUpdateRequest` | `PaperOrderActionResponse` | yes | `modify_order` | write | — |
| DELETE | `/paper-trading/orders/{order_id}` | Delete | (path) | `PaperOrderActionResponse` | yes | `cancel_order` | write | — |
| POST | `/paper-trading/orders/{order_id}/cancel` | Cancel alias | (path) | `PaperOrderActionResponse` | yes | `cancel_order` | write | — |
| POST | `/paper-trading/positions/{position_id}/close` | Close manually | (path) | `PaperOrderActionResponse` | yes | `close_position` | write | inserts filled SELL order + trade |
| PATCH | `/paper-trading/positions/{position_id}` | Update SL/TP | `PaperPositionUpdateRequest` | `PaperOrderActionResponse` | yes | `update_position` | write | — |
| POST | `/paper-trading/positions/squareoff-all` | Square off | none | `PaperTradingDashboardResponse` | yes | `square_off_all` | write | generates orders/trades |
| GET | `/paper-trading/account/transactions` | Transactions | `page`, `per_page` query | `TransactionPageResponse` | yes | `get_transactions` | read | — |

### Market engine

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/paper-trading/engine/start` | Start engine | none | `MarketEngineStatusResponse` | no | `market_engine.request_start`, `status` | write (MarketEngineSession) | starts background loop |
| POST | `/paper-trading/engine/stop` | Stop engine | none | `MarketEngineStatusResponse` | no | `market_engine.request_stop`, `status` | write | stops engine |
| GET | `/paper-trading/engine/status` | Engine status | none | `MarketEngineStatusResponse` | no | `market_engine.status` | read | — |
| POST | `/paper-trading/engine/heartbeat` | Engine heartbeat (BackgroundTasks) | none | `MarketEngineStatusResponse` | no | `market_engine.heartbeat`; `db.scan_store.get_last_scan_time` | read | (background auto-scan triggering currently disabled) |
| GET | `/paper-trading/engine-status` | Legacy engine status | none | `JSONResponse` (dict) | yes | `PaperTradingService.get_engine_status` | read | logs response durations |

### Symbols / Workspace / Quote

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/paper-trading/symbols` | Symbols list | none | `list[str]` | yes | `get_dashboard` | read | — |
| GET | `/paper-trading/symbols/{symbol}/workspace` | Workspace snapshot | (path) | `PaperWorkspaceSnapshot` | yes | `get_workspace` | read | — |
| GET | `/paper-trading/symbols/{symbol}/quote` | Live quote | (path) | `PaperQuoteResponse` | yes | `get_quote` | read + Fyers LTP/quote | — |

### Notifications / Alerts / Prefill / Analytics / Journal / Gap-Replay

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/paper-trading/from-recommendation` | Prefill from recommendation | `RecommendationPrefillRequest` | `RecommendationPrefillResponse` | yes | `recommendation_prefill` | read | no write |
| GET | `/paper-trading/notifications/unread` | Unread notifications | none | `list[NotificationItem]` | yes | `get_unread_notifications` | read | — |
| POST | `/paper-trading/notifications/mark-read` | Mark read | `NotificationMarkReadRequest` | `JSONResponse` (dict) | yes | `mark_notifications_read` | write | — |
| GET | `/paper-trading/notifications` | List | `unread`, `limit` query | `list[NotificationItem]` | yes | `get_notifications` | read | — |
| POST | `/paper-trading/notifications/read-all` | Mark all read | none | `JSONResponse` (dict) | yes | `mark_all_notifications_read` | write | — |
| GET | `/paper-trading/gap-replay-summary` | Gap replay result | none | `JSONResponse` (dict) | no | `request.app.state.last_gap_replay` | none | in-memory only |
| GET | `/paper-trading/alerts` | List alerts | none | `list[AlertItem]` | yes | `get_alerts` | read | — |
| POST | `/paper-trading/alerts` | Create alert | `AlertCreateRequest` | `AlertItem` | yes | `create_alert` | write | — |
| DELETE | `/paper-trading/alerts/{alert_id}` | Delete alert | (path) | `JSONResponse` (dict) | yes | `delete_alert` | write | — |
| GET | `/paper-trading/analytics` | Analytics | `period` query | `JSONResponse` (dict) | yes | `PaperTradingService.get_analytics` | read | — |
| GET | `/paper-trading/daily-analytics` | Daily analytics | `period`, `start_date`, `end_date`, `include_ai` query | `JSONResponse` (dict) | yes | `DailyAnalyticsService.build` | read | may invoke AI services |
| GET | `/paper-trading/daily-journal` | Get journal | `journal_date` query | `JSONResponse` (dict) | yes | `DailyAnalyticsService._get_journal`; `PaperTradingService._get_or_create_account` | read | — |
| PUT | `/paper-trading/daily-journal` | Save journal | inline dict payload | `JSONResponse` (dict) | yes | `DailyAnalyticsService.save_journal` | write | — |

---

## 5. Stocks

Router: `routes/stocks.py`, prefix `/stocks`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/stocks/analyze` | Analyze stocks | `AnalysisRequest` | `AnalysisResponse` | no | `RouterAgent.analyze_stocks` | indirect | agent may call Fyers/candle_store |

---

## 6. Scanner

Router: `routes/scanner.py`, prefix `/scanner`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/scanner/latest` | Latest completed scan | none | `dict` | no | `LatestScanService.get_latest_scan` (when `SCANNER_UNIFIED_LATEST_ENABLED=true`); fallback `LatestScanService.get_latest_completed_scan`; `diagnostics.record_dashboard_snapshot`; `scan_diagnostics.log_dashboard_request` | read | in-memory diagnostics update; Redis cache lookup |

---

## 7. System / Shadow Run

Router: `routes/system.py`, prefix `/system/shadow-run`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/system/shadow-run/status` | Shadow run status | none | `dict` | no | `diagnostics.get_db_health`, `get_memory_metrics`; in-memory scanner_runs/scheduler_runs/fyers_metrics | read (`pg_stat_activity`) | — |
| GET | `/system/shadow-run/report` | Full shadow report | none | `dict` | no | `diagnostics.get_shadow_run_report` | read (scan_snapshots count) | — |
| GET | `/system/shadow-run/health/ready` | Readiness probe | none | `dict` (checks) | no | `SELECT 1`; `scheduler.running`; `SELECT 1 FROM scan_snapshots`; `token_service.get_current_access_token` | read | reads scheduler state |
| GET | `/system/shadow-run/market-status` | Market status | none | `dict` | no | `trading_hours.get_market_status` | none | — |

---

## 8. Auth

Router: `routes/auth.py`, prefix applied at include `/auth`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/auth/signup` | Register | `UserCreate` | `UserResponse` (201) | no | `auth_service.create_user` | write | logs IP/UA |
| POST | `/auth/login` | Login | `LoginRequest` | `JSONResponse` (dict) | no | `auth_service.authenticate_user`, `auth_service.create_user_session` | write (session) | sets HttpOnly cookies |
| POST | `/auth/google` | Google login | `GoogleLoginRequest` | `JSONResponse` (dict) | no | `auth_service.google_auth`, `auth_service.create_user_session` | write (user/session) | sets cookies |
| POST | `/auth/logout` | Logout | none (uses Request/Response) | `JSONResponse` (dict) | no | clears auth cookies via `_clear_auth_cookies` | none (no session invalidation in current code) | — |
| POST | `/auth/refresh` | Refresh | none (refresh_token cookie) | `JSONResponse` (dict) | refresh cookie | `decode_refresh_token`, `auth_service.create_user_session` | write (new session) | refreshes cookies |
| GET | `/auth/sessions` | Active sessions | none | `dict` (sessions list) | access cookie | `decode_access_token`, `auth_service.get_active_sessions` | read | — |
| POST | `/auth/sessions/{session_id}/revoke` | Revoke session | (path) | `dict` | access cookie | `decode_access_token`, `auth_service.revoke_session` | write | — |
| POST | `/auth/forgot-password` | Request reset | `ForgotPasswordRequest` | `dict` | no | `auth_service.request_password_reset` | write (reset token) | likely email send |
| POST | `/auth/reset-password` | Confirm reset | `ResetPasswordRequest` | `dict` | no | `auth_service.confirm_password_reset` | write (password update) | — |
| GET | `/auth/me` | Current user | none | `UserResponse` | yes (`get_current_active_user`) | returns `current_user` | none | — |
| GET | `/auth/profile` | Get profile | none | `UserProfileResponse` | yes | `user_profile_service.get_or_create_profile`, `profile_to_dict` | read/write (creates if missing) | — |
| PUT | `/auth/profile` | Replace profile | `UserProfileUpdate` | `UserProfileResponse` | yes | `user_profile_service.update_profile (partial=False)` | write | — |
| PATCH | `/auth/profile` | Patch profile | `UserProfilePatch` | `UserProfileResponse` | yes | `user_profile_service.update_profile (partial=True)` | write (deep-merge preferences) | — |

---

## 9. Token

Router: `routes/token.py`, prefix `/api/token`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/api/token/save-access-token` | Save FYERS token | `FyersTokenCreate` (BackgroundTasks) | `dict` | no | `token_service.save_access_token`; `LatestScanService.get_latest_completed_scan`; `diagnostics_service.diagnostics` | write (FyersToken + FyersTokenHistory) | in-memory token cache set; external Fyers validation; (auto-scan trigger currently disabled) |
| GET | `/api/token/status` | Token status | none | `JSONResponse` (dict) | no | `token_service.get_token_status` | read | response_cache set (300s) |
| GET | `/api/token/history` | History | `limit` query | `JSONResponse` (dict) | no | `token_service.get_token_history` | read | — |
| GET | `/api/token/diagnostic` | Diagnostic | none | `dict` | no | raw `select(FyersToken)`; reads `engine.url` | read | — |

---

## 10. Broker Tokens

Router: `routes/broker_tokens.py`, prefix `/api/broker-tokens`. All endpoints require `Depends(get_current_user)`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/api/broker-tokens` | Get token (default FYERS) | `broker` query | `JSONResponse` | yes | `broker_token_service.get_token` (via `_with_db_retry`) | read | — |
| GET | `/api/broker-tokens/list` | List tokens | none | `JSONResponse` | yes | `broker_token_service.list_tokens` | read | — |
| POST | `/api/broker-tokens` | Create | `BrokerTokenPayload` | `JSONResponse` | yes | `broker_token_service.save_token` (validate optional) | write | optional external broker validation; encryption at rest |
| PUT | `/api/broker-tokens` | Update | `BrokerTokenUpdatePayload` | `JSONResponse` | yes | `broker_token_service.update_token` | write | optional validation |
| DELETE | `/api/broker-tokens` | Delete | `broker` query | `JSONResponse` | yes | `broker_token_service.delete_token` | write | — |
| POST | `/api/broker-tokens/validate` | Validate | `broker` query | `JSONResponse` | yes | `broker_token_service.validate_token` | read | external broker API call |
| POST | `/api/broker-tokens/test-connection` | Test connection | `BrokerTestPayload \| None` | `JSONResponse` | yes | `broker_token_service._validate_fyers` (if token), `validate_token` | read | external broker API call |

---

## 11. Settings

Router: `routes/settings.py`, prefix `/settings`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/settings/token` | Validate + save FYERS token | `TokenValidateRequest` | `dict` | no | direct `httpx.AsyncClient` POST to FYERS v3 profile (`_validate_token_with_fyers`); `token_service._mask_token`, `_decode_jwt_expiry`, `_encrypt_for_storage`, `_set_token_cache`; `response_cache.cache_invalidate`; `logger_service.log_info/error` | write (deactivate old FyersToken; insert new; insert FyersTokenHistory) | in-memory token cache set; cache invalidate; external FYERS call |

---

## 12. Workstation

Router: `routes/workstation.py`, prefix `/workstation`. Only `Depends(get_db)` (no user auth).

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/workstation/universes` | List universes | none | `JSONResponse` (list) | no | `WorkstationService.list_universes` | read | — |
| GET | `/workstation/market-overview` | Market overview | none | `MarketOverviewResponse` | no | `WorkstationService.market_overview` | read + Fyers quotes | — |
| GET | `/workstation/saved-scans` | List saved scans | none | `JSONResponse` (list) | no | `list_saved_scans` | read | — |
| POST | `/workstation/saved-scans` | Save scan | `SavedScanCreate` | `JSONResponse` | no | `save_scan` | write | — |
| DELETE | `/workstation/saved-scans/{scan_id}` | Delete scan | (path) | `JSONResponse` (dict) | no | `delete_saved_scan` | write | — |
| GET | `/workstation/scan-history` | Scan history | `limit` query | `JSONResponse` (list) | no | `list_scan_history` | read | — |
| GET | `/workstation/scan-history/{scan_id}/compare` | Compare scan | (path) | `JSONResponse` (dict) | no | `compare_scan` | read | — |
| GET | `/workstation/alerts` | List alerts | none | `JSONResponse` (list) | no | `list_alerts` | read | — |
| POST | `/workstation/alerts` | Create alert | `AlertCreate` | `JSONResponse` | no | `create_alert` | write | — |
| DELETE | `/workstation/alerts/{alert_id}` | Delete alert | (path) | `JSONResponse` (dict) | no | `delete_alert` | write | — |
| GET | `/workstation/risk-settings` | Get risk settings | none | `JSONResponse` | no | `get_risk_settings` | read | — |
| PUT | `/workstation/risk-settings` | Update risk settings | `RiskSettingsRequest` | `JSONResponse` | no | `update_risk_settings` | write | — |
| GET | `/workstation/api-health` | API health | none | `JSONResponse` (health) | no | `api_health` | read | may ping Fyers |

---

## 13. Logs (incl. WebSocket)

Router: `routes/logs.py`, prefix `/api/logs`. No user auth.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/api/logs` | Query logs | many filters (`limit`, `offset`, `level`, `source`, `symbol`, `correlationId`, `error_hash`, `environment`, `dateFrom`, `dateTo`, `search`) | `JSONResponse` (list) | no | raw `select(SystemLog)` | read | — |
| DELETE | `/api/logs` | Clear (legacy) | `confirm`, `days_old` query | `JSONResponse` or `dict` | no | raw `delete(SystemLog)` | write | requires `?confirm=WIPE_ALL` if `days_old=0` |
| DELETE | `/api/logs/clear` | Clear (alias) | `confirm`, `days_old` query | `JSONResponse` | no | raw `delete(SystemLog)` | write | — |
| GET | `/api/logs/export` | Export logs | `format=csv\|json` + filters | `Response` (file) | no | raw `select(SystemLog)`; `csv.DictWriter` | read | file attachment |
| WS | `/api/logs/stream` | Log stream | none | WebSocket stream | no (any client) | `logger_service.register_ws_client` / `unregister_ws_client` | none | server pushes masked log entries broadcast by `logger_service` |

---

## 14. FYERS

Router: `routes/fyers.py`, prefix `/fyers`. Included directly via `app.include_router(fyers_router)`. No user auth.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/fyers/token` | Save FYERS token (legacy) | `FyersTokenCreate` | `dict` | no | `token_service.save_access_token` | write (deactivate old, insert new FyersToken) | — |
| GET | `/fyers/token/status` | Token status | none | `JSONResponse` (has_token, created_at, expires_at, is_active) | no | raw `select(FyersToken)` | read | — |
| DELETE | `/fyers/token` | Clear all tokens | none | `JSONResponse` (message) | no | raw `update(FyersToken).where(active=True).values(is_active=False)` | write | — |
| GET | `/fyers/auth/url` | Build OAuth URL | none | `JSONResponse` (oauth_available, auth_url, callback_url) | no | reads `settings.fyers_app_id`/`fyers_secret_id`/`fyers_redirect_uri`; `urlencode` | none | — |
| POST | `/fyers/auth/exchange` | Exchange auth_code | inline `{"auth_code":"..."}` | `JSONResponse` (result) | no | `token_service.exchange_auth_code` | write (persists token) | external FYERS OAuth exchange API call |

---

## 15. Scheduler

Router: `routes/scheduler.py`, prefix `/scheduler`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/scheduler/daily-scan` | Cron-triggered scan | `ScreenerRequest` (requires `X-Scheduler-Secret` header == env `SCHEDULER_SECRET`) | `JSONResponse` (status) | custom secret | `ScanExecutionService.execute_scan (trigger_source="cron")`; `LockAcquisitionError` handling | write (scan snapshot + candidates); Fyers calls | returns 202 "ignored" if scan already running |
| GET | `/scheduler/status` | Last scan summary | none | `JSONResponse` / `dict` (last_scan_started/completed/status/duration_sec/candidates_generated) | no | raw `select(ScanSnapshot)` (latest) | read | — |

---

## 16. Walk-Forward

Router: `routers/walk_forward.py`, prefix `/api/walk-forward`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/api/walk-forward/evaluate` | Walk-forward evaluation | `symbol`, `min_windows` query | `dict` | no | `WalkForwardService.run_walk_forward_evaluation` | write (WalkForwardSummary, VetoHistory) | external Fyers candle fetch |
| GET | `/api/walk-forward/results` | History | `symbol` query | `list` (dict) | no | raw `select(WalkForwardSummary)` | read | — |
| GET | `/api/walk-forward/vetoes` | Veto statistics | `symbol` query | `list` (dict) | no | raw `select(VetoHistory)` | read | — |

---

## 17. Event Calendar

Router: `routers/event_calendar.py`, prefix `/api/events`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| POST | `/api/events/ingest/mock` | Mock ingestion feed | none | `dict` | no | `EventCalendarService.run_mock_ingestion_feed` | write (event_calendar + event_calendar_coverage) | idempotent ingestion |
| GET | `/api/events/upcoming` | Upcoming events | `symbol`, `scan_date`, `days_ahead` query | `list` (dict) | no | `EventCalendarService.get_upcoming_events` | read | look-ahead bias protected |
| GET | `/api/events/coverage` | Coverage audit | `source` query | `list` (dict) | no | `EventCalendarService.get_latest_coverage` | read | — |

---

## 18. App-mounted endpoints

Not registered via `api_router`; defined directly on the FastAPI `app` in `backend/app/main.py`.

| Method | Route | Purpose | Request model | Response model | Auth | Service(s) called | DB | Side effects |
|--------|-------|---------|----------------|-----------------|------|-------------------|----|--------------|
| GET | `/scanner/health` | Scanner metrics | none | `dict` | no | `ScreenerService().get_metrics()` | none | in-memory metrics |
| GET | `/metrics` | Prometheus exposition | none | `Response` (Prometheus format) | no | `observability.render_metrics` | none | none |

---

## 19. Authentication key

The "Auth" column in tables above uses three categories:

| Auth | Meaning |
|------|---------|
| **no** | Public — no injected dependency |
| **yes** | Requires an authenticated user via the HttpOnly `access_token` cookie (`get_current_user` / `get_current_user_id_sync`) |
| **yes (`get_current_active_user`)** | Requires `User.is_active == True` in addition to `get_current_user` |
| **custom secret** | Requires header `X-Scheduler-Secret` equal to env `SCHEDULER_SECRET` |
| **refresh cookie** | Requires the `refresh_token` cookie decoded by `decode_refresh_token` |
| **access cookie** | Endpoint reads `request.cookies["access_token"]` manually (rather than via `Depends`) |
| **no (any client)** | WebSocket with no auth — any client may subscribe to log broadcasts on `/api/logs/stream` |

Cross-cutting side effect: the global HTTP middleware in `main.py` (`log_http_requests`) logs all `POST`/`PUT`/`DELETE` responses (status code logged) to `SystemLog` via `log_to_db` in addition to per-endpoint side effects listed; unhandled exceptions are logged to DB and converted to a generic 500 response.