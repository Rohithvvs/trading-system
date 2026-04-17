# API Contracts

Generated from the FastAPI route definitions in the codebase. Sources: [backend/app/routes/analysis.py](backend/app/routes/analysis.py), [backend/app/routes/stocks.py](backend/app/routes/stocks.py), [backend/app/routes/paper_trading.py](backend/app/routes/paper_trading.py), [backend/app/routes/health.py](backend/app/routes/health.py)

Note: endpoints grouped per requested feature headings. If a heading has no matching endpoints in this codebase it's noted below.

---

**AI Processing**

- POST /analysis/technical

Request:
```json
{
  "symbols": ["RELIANCE", "TCS"],
  "mode": "both",           
  "timeframe": { "intraday": "5m", "swing": "1d", "lookback_window": 90 }
}
```

Response (200): `AnalysisResponse` (JSON):
```json
{
  "items": [ /* list of StockAnalysisResult */ ],
  "rankings": { /* RankingsResponse */ },
  "disclaimer": "string"
}
```

Status codes: 200, 422 (validation), 500

Description: Run technical-only analysis for requested symbols/timeframe. (See [backend/app/routes/analysis.py](backend/app/routes/analysis.py))

- POST /analysis/news

Same request/response shapes as `/analysis/technical`. Runs news-only analysis.

- POST /analysis/backtest

Same request/response shapes as `/analysis/technical`. Runs backtesting-only analysis.

- POST /analysis/final-recommendation

Same request/response shapes as `/analysis/technical`. Returns final recommendation only.

- POST /analysis/full

Request: `AnalysisRequest` (same shape as above)

Response (200): `FullAnalysisResponse` — same as `AnalysisResponse` plus `generated_at` timestamp.

Status codes: 200, 422, 500

- POST /analysis/rankings

Request: `AnalysisRequest`

Response (200): `RankingsResponse` (see schemas for structure: `rankings`, `buy_rankings`, `watch_rankings`, `best_intraday_candidate`, `best_swing_candidate`, `disclaimer`)

Status codes: 200, 422, 500

- POST /analysis/screener/full

Request: `ScreenerRequest` example:
```json
{
  "mode": "swing",
  "timeframe": { "intraday": "5m", "swing": "1d", "lookback_window": 90 },
  "symbols": [],
  "top_n": 20
}
```

Response (200): `ScreenerResponse` (summary of matched symbols, matches array, optional `analysis`)

Status codes: 200, 422, 500

- POST /stocks/analyze

Request: `AnalysisRequest` (same as above)

Response (200): `AnalysisResponse`

Status codes: 200, 422, 500

Description: Entrypoint for stock analysis that funnels to the agent logic. (See [backend/app/routes/stocks.py](backend/app/routes/stocks.py))

---

**Reporting**

- GET /health

Request: none

Response (200): `HealthResponse`
```json
{
  "status": "ok",
  "environment": "development",
  "disclaimer": "string"
}
```

Status codes: 200

Description: Basic health/status and environment. (See [backend/app/routes/health.py](backend/app/routes/health.py))

- GET /paper-trading/dashboard

Query params:
- `selected_symbol` (optional) — string

Request: none (query only)

Response (200): `PaperTradingDashboardResponse` (account summary, positions, open_orders, order_history, trades, symbols, selected_workspace)

Example (truncated):
```json
{
  "account": { "account_id": 1, "account_name": "Demo", "starting_balance": 100000.0, "balance": 99900.0, "equity": 99900.0, "updated_at": "2026-04-13T12:00:00Z" },
  "positions": [ /* PaperPositionResponse */ ],
  "open_orders": [ /* PaperOrderResponse */ ],
  "order_history": [],
  "trades": [],
  "symbols": ["RELIANCE", "TCS"],
  "selected_workspace": null
}
```

Status codes: 200, 422

Description: Returns the paper-trading dashboard and optionally a selected symbol snapshot.

- GET /paper-trading/account

Same response as `/paper-trading/dashboard`.

- POST /paper-trading/account/reset

Request body: `PaperTradingAccountResetRequest`
```json
{ "starting_balance": 100000.0 }
```

Response (200): `PaperTradingDashboardResponse` — new account/dashboard snapshot.

Status codes: 200, 422

- POST /paper-trading/orders

Request body: `PaperOrderCreateRequest`
```json
{
  "symbol": "RELIANCE",
  "side": "BUY",
  "type": "MARKET",
  "qty": 1,
  "limit_price": null,
  "stop_price": null,
  "stop_loss": null,
  "target": null,
  "notes": "string",
  "source_signal": "MA_CROSS",
  "source_score": 0.8,
  "source_confidence": 0.7
}
```

Response (200): `PaperOrderActionResponse` (contains `account`, optional `order`, `position`, `trade`, and `message`)

Status codes: 200, 400 (bad request, e.g. ValueError thrown by service -> returned as HTTP 400), 422

Description: Place a paper order. Service may raise HTTP 400 with `{ "detail": "..." }` for invalid business rules.

- POST /paper-trading/orders/{order_id}/cancel

Path param: `order_id` (int)

Response (200): `PaperOrderActionResponse`

Status codes: 200, 404 (if order not found; service raises ValueError -> HTTP 404), 422

- POST /paper-trading/positions/{position_id}/close

Path param: `position_id` (int)

Response (200): `PaperOrderActionResponse`

Status codes: 200, 404, 422

- PATCH /paper-trading/positions/{position_id}

Path param: `position_id` (int)

Request body: `PaperPositionUpdateRequest`
```json
{ "stop_loss": 100.0, "target": 120.0, "notes": "trim position" }
```

Response (200): `PaperOrderActionResponse`

Status codes: 200, 404, 422

- POST /paper-trading/from-recommendation

Request body: `RecommendationPrefillRequest`
```json
{
  "symbol": "RELIANCE",
  "suggested_entry": 2350.0,
  "suggested_stop": 2250.0,
  "suggested_targets": [2450.0],
  "recommendation_meta": { "score": 0.9 }
}
```

Response (200): `RecommendationPrefillResponse` — pre-filled order fields (symbol, side, type, qty, limit_price, stop_loss, target, note)

Status codes: 200, 422

- GET /paper-trading/symbols

Response (200): Array of symbols (list[string])

- GET /paper-trading/symbols/{symbol}/workspace

Path param: `symbol` (string)

Response (200): `PaperWorkspaceSnapshot` (current price, candles, ema, supertrend, source signals)

Status codes: 200, 400 (bad symbol), 422

- GET /paper-trading/symbols/{symbol}/quote

Path param: `symbol` (string)

Response (200): `PaperQuoteResponse`:
```json
{ "symbol": "RELIANCE", "current_price": 2345.0, "source": "FYERS_QUOTE", "updated_at": "2026-04-13T12:00:00Z" }
```

Status codes: 200, 400, 422

---

**Proposal**

No endpoints found in the codebase matching a `proposal` or `proposals` feature.

**Upload**

No multipart/file upload endpoints found in the codebase.

**Team Management**

No endpoints found for team or user management in the codebase.

**Chatbot**

No chatbot endpoints discovered.

---

**Common error responses**

- Validation errors (FastAPI/Pydantic) — 422 Unprocessable Entity

Example 422 body (truncated):
```json
{
  "detail": [ { "loc": ["body","symbols"], "msg": "ensure this value has at least 1 items", "type": "value_error.list.min_items" } ]
}
```

- Application errors returned via `HTTPException` — shape: `{ "detail": "<message>" }`.

Examples from routes:
- 400 Bad Request for invalid orders or bad symbol input.
- 404 Not Found for missing order/position when cancelling/closing.

---

**Validation rules (key fields)**

- `AnalysisRequest.symbols`: list[str], min_length=1, max_length=25; cleaned (trimmed, uppercased); duplicates removed.
- `ScreenerRequest.symbols`: optional list[str], cleaned similarly, max_length=200.
- `ScreenerRequest.top_n`: int, default=20, ge=1, le=50.
- `PaperOrderCreateRequest.qty`: int, ge=1, le=100000.
- `PaperOrderCreateRequest.limit_price`, `stop_price`, `stop_loss`, `target`: floats, if provided must be `> 0`.
- `PaperOrderCreateRequest.notes`: optional str, max_length=1000.
- `PaperOrderCreateRequest.symbol`: validated (non-empty, trimmed, uppercased).
- `PaperPositionUpdateRequest.stop_loss` / `target`: if provided `> 0`.
- `PaperTradingAccountResetRequest.starting_balance`: float, default=100000.0, ge=1000.0.

---

Sources: route definitions and Pydantic schemas in the backend (see top of this document). If you want, I can:
- Add example curl commands for each endpoint.
- Expand sample response bodies for nested models (e.g., full `AnalysisResponse` example).

Generated on 2026-04-13.
