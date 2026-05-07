# Feature Specification: Trading System — Full Module

**Feature Branch**: `001-trading-system`
**Created**: 2026-04-17
**Status**: Draft
**Input**: Advisory-only stock analysis and recommendation system for Indian equity markets (Nifty 500 universe), covering screener, technical analysis, news sentiment, backtesting, LLM reasoning, and paper trading simulation.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Run Nifty 500 Screener and Receive Ranked Candidates (Priority: P1)

A swing trader opens the dashboard and triggers the preset screener. The system scans the full Nifty 500 universe, applies data quality and trend eligibility filters, scores remaining stocks using a weighted composite, shortlists the top candidates, runs deep analysis on the shortlist, and returns a ranked table of BUY / WATCH / REJECT signals with reasoning.

**Why this priority**: This is the primary workflow. Without a working screener pipeline the product delivers no value.

**Independent Test**: Trigger `POST /analysis/screener/full` with default configuration and verify that a ranked list of candidates is returned with signal labels, scores, and reasoning bullets — even when FYERS credentials are absent (mock fallback must activate).

**Acceptance Scenarios**:

1. **Given** the system is running with no FYERS credentials, **When** the user triggers a screener run, **Then** the system uses mock OHLCV data, completes the full pipeline, and returns a `ScreenerResponse` containing at least one `StockAnalysisResult` with a `FinalRecommendation`.
2. **Given** valid FYERS credentials are configured, **When** the user triggers a screener run for `top_n = 10`, **Then** the response contains exactly 10 (or fewer if universe filtered) results ranked in descending composite score order.
3. **Given** the screener runs successfully, **When** the user inspects any candidate, **Then** each result includes: `signal` (BUY/WATCH/REJECT), `score`, technical indicators, backtest summary, news sentiment, and LLM reasoning bullets.
4. **Given** all 500 symbols fail data quality checks, **When** the screener runs, **Then** the system returns an empty shortlist with a descriptive message and HTTP 200 (not an error).

---

### User Story 2 — Analyze Specific Stocks with Full Pipeline (Priority: P1)

A trader identifies a symbol of interest and requests a full analysis through the dashboard or API. The system fetches candles, runs technical + backtest + news agents, generates LLM reasoning, and returns a structured recommendation.

**Why this priority**: Single-symbol deep analysis is the secondary entry point after the screener and must work independently.

**Independent Test**: Call `POST /analysis/full` with `{ "symbols": ["RELIANCE"] }` and verify a `FullAnalysisResponse` is returned with all sub-components populated.

**Acceptance Scenarios**:

1. **Given** a valid symbol, **When** `POST /analysis/full` is called, **Then** the response contains `TechnicalAnalysisResult`, `BacktestResult`, news sentiment, and `FinalRecommendation` for that symbol.
2. **Given** an unsupported or delisted symbol, **When** `POST /analysis/full` is called, **Then** the system returns a graceful error (HTTP 422 or a result with `data_warning` flag) — not an unhandled exception.
3. **Given** the LLM provider is unavailable, **When** full analysis runs, **Then** deterministic reasoning fallback activates and the recommendation is still returned with a `data_warning` indicating LLM was unavailable.
4. **Given** more than 25 symbols are provided, **When** the request is submitted, **Then** the system rejects it with HTTP 422 and a validation message (input size limit enforced).

---

### User Story 3 — Paper Trade from a Recommendation (Priority: P2)

After receiving a BUY recommendation, a trader initiates a paper trade. The system accepts the order, simulates a fill, tracks the position, and allows the trader to close it or update stop/target levels — all without touching live markets.

**Why this priority**: Paper trading is the "act on recommendation" step that completes the workflow loop. Users validate trade plans risk-free.

**Independent Test**: Call `POST /paper-trading/from-recommendation` with a valid `FinalRecommendation` payload, then call `GET /paper-trading/dashboard` and verify the position appears with correct entry price and quantity.

**Acceptance Scenarios**:

1. **Given** a BUY recommendation, **When** the user sends it to paper trading, **Then** a paper order is created, filled at the recommended price, and a position appears on the dashboard.
2. **Given** an open position, **When** the user updates stop-loss and target via `PATCH /paper-trading/positions/{id}`, **Then** the position reflects updated values on the next dashboard fetch.
3. **Given** an open position, **When** the user closes it via `POST /paper-trading/positions/{id}/close`, **Then** realised P&L is computed and a trade history entry is recorded.
4. **Given** the paper account, **When** the user resets via `POST /paper-trading/account/reset`, **Then** all positions, orders, and trade history are cleared and the account balance reverts to the configured starting capital.

---

### User Story 4 — View Technical and Backtest Analysis Per Symbol (Priority: P2)

A more technical trader wants to inspect raw signals and backtest statistics for a stock before forming a view, without necessarily running the full LLM recommendation.

**Why this priority**: Supports users who prefer signal transparency and independent validation over LLM summaries.

**Independent Test**: Call `POST /analysis/technical` and `POST /analysis/backtest` independently for the same symbol and verify the responses match the sub-components of a full analysis for that symbol.

**Acceptance Scenarios**:

1. **Given** a symbol and mode (`intraday` or `swing`), **When** `POST /analysis/technical` is called, **Then** indicators (EMA, RSI, MACD, Supertrend, VWAP, SMA, volume) and a composite `score` are returned.
2. **Given** a symbol with sufficient candle history, **When** `POST /analysis/backtest` is called, **Then** backtest stats (win rate, profit factor, max drawdown, trade count) are returned.
3. **Given** fewer candles than the minimum required for a backtest, **When** `POST /analysis/backtest` is called, **Then** the system returns a result with a `data_warning` flag rather than an exception.

---

### User Story 5 — Monitor System Health (Priority: P3)

An operator needs to confirm the system is live and correctly wired before presenting it to users.

**Why this priority**: Foundational operational check. Low complexity but required for any deployment validation.

**Independent Test**: Call `GET /health` and confirm HTTP 200 with a disclaimer payload and environment summary.

**Acceptance Scenarios**:

1. **Given** the backend is running, **When** `GET /health` is called, **Then** HTTP 200 is returned with a JSON body containing a disclaimer and environment status.

---

### Edge Cases

- **FYERS session expiry mid-run**: `FyersService` fails partway through a screener. System logs the failure, falls back to mock OHLCV for remaining symbols, and includes a `data_warning` in the response.
- **LLM schema mismatch**: Groq returns a JSON object missing required fields (`bullets`, `risk_factors`, `invalidation_signals`, `summary`). System activates deterministic fallback and marks `data_warning`.
- **LLM timeout (>20 s)**: Request times out. Same deterministic fallback path triggered.
- **All screener candidates filtered out**: Data quality or trend eligibility removes every symbol. System returns HTTP 200 with an empty shortlist and an informative message.
- **Symbol appears twice in request**: Input deduplication applied; symbol analyzed once and result returned once.
- **`top_n` exceeds universe size**: System returns all surviving symbols without error.
- **Paper order with zero quantity**: Validation rejects at schema level with HTTP 422.
- **Paper position close with no open market price**: Service uses last known price with a `data_warning`.
- **Concurrent screener runs**: Without background jobs, second request blocks behind first (synchronous workers). System must not corrupt shared DB state.
- **DB file locked or unwritable**: Analysis history write fails; pipeline still returns the analysis result to the caller (write failure must not cause HTTP 500).

---

## Requirements *(mandatory)*

### Functional Requirements

#### Screener & Universe Management
- **FR-001**: System MUST scan the configured Nifty 500 universe and fetch OHLCV data for all symbols via the market data provider.
- **FR-002**: System MUST apply a data quality gate (minimum candle count, liquidity threshold) and silently drop symbols that fail.
- **FR-003**: System MUST apply a broad trend eligibility filter (EMA/price-structure) to the quality-passed universe before scoring.
- **FR-004**: System MUST compute a weighted composite screener score (momentum, volume, volatility factors) for eligible symbols.
- **FR-005**: System MUST return only the top-N shortlisted symbols for deep analysis, where `top_n` is configurable in the request.
- **FR-006**: System MUST fall back to generated mock OHLCV data when market data provider credentials are absent or the provider returns an error.

#### Technical Analysis
- **FR-007**: System MUST compute the following indicators per symbol per mode: EMA (multi-period), SMA, MACD, RSI, VWAP, Supertrend, and volume statistics.
- **FR-008**: System MUST produce a numeric composite technical score and a categorical signal (`bullish` / `neutral` / `bearish`) from indicator outputs.
- **FR-009**: System MUST support two analysis modes: `intraday` and `swing`, each using the appropriate candle timeframe.

#### Backtesting
- **FR-010**: System MUST run a historical backtest for each symbol in the analysis pipeline using configured strategy parameters.
- **FR-011**: Backtest output MUST include: win rate, profit factor, maximum drawdown, and total trade count.
- **FR-012**: System MUST persist each backtest result to `backtest_history` for post-hoc audit.

#### News & Sentiment
- **FR-013**: System MUST fetch recent news articles for each symbol from the configured news provider.
- **FR-014**: System MUST compute a sentiment score and categorical label per symbol from fetched articles.
- **FR-015**: System MUST fall back to generated mock articles when the news provider is unavailable.

#### LLM Reasoning & Recommendation
- **FR-016**: System MUST invoke an LLM to produce structured reasoning containing: `bullets`, `risk_factors`, `invalidation_signals`, and `summary` for each symbol.
- **FR-017**: LLM calls MUST use low randomness (temperature ≤ 0.3) and enforce a maximum timeout of 20 seconds.
- **FR-018**: System MUST activate a deterministic fallback reasoning generator if the LLM is unavailable or returns a schema-invalid response.
- **FR-019**: System MUST produce a `FinalRecommendation` per symbol with: signal label (BUY / WATCH / REJECT), composite score, trade plan (entry, stop-loss, target), and LLM reasoning.
- **FR-020**: System MUST persist each analysis result (including recommendation) to `analysis_history`.

#### Rankings
- **FR-021**: System MUST rank all results in descending composite score order and return them in the ranked `ScreenerResponse` / `AnalysisResponse`.

#### Paper Trading
- **FR-022**: System MUST accept paper orders (symbol, direction, quantity, price, stop-loss, target) and simulate an immediate fill at the submitted price.
- **FR-023**: System MUST track open paper positions with entry price, current unrealised P&L (using last known quote), stop-loss, and target.
- **FR-024**: System MUST allow users to update stop-loss, target, and notes on an open position.
- **FR-025**: System MUST allow users to close a position and record the realised P&L in `paper_trading_trade_history`.
- **FR-026**: System MUST allow cancellation of pending (unfilled) paper orders.
- **FR-027**: System MUST prefill a paper order from a `FinalRecommendation` (entry, stop-loss, target pre-populated).
- **FR-028**: System MUST allow resetting the paper account to initial capital, clearing all positions, orders, and trade history.

#### API & Input Validation
- **FR-029**: System MUST reject analysis requests specifying more than 25 symbols with HTTP 422.
- **FR-030**: System MUST reject paper orders with zero or negative quantity with HTTP 422.
- **FR-031**: All API endpoints MUST return structured JSON error responses (not raw exception text).

### Non-Functional Requirements

- **NFR-001 — Response time**: The screener pipeline for 10 shortlisted symbols MUST complete within 90 seconds under normal operating conditions (mock or live data).
- **NFR-002 — Advisory-only**: The system MUST NOT submit any order to a live brokerage. All execution paths lead to the paper trading simulator only.
- **NFR-003 — Fail-safe by default**: External provider failures (market data, news, LLM) MUST degrade gracefully to mock/deterministic fallbacks without returning HTTP 5xx to the caller.
- **NFR-004 — Auditability**: All analysis and backtest results MUST be persisted to the database before the API response is returned.
- **NFR-005 — Explainability**: Every `FinalRecommendation` MUST include human-readable reasoning (LLM or deterministic fallback) traceable to input signals.
- **NFR-006 — Input size limits**: All list-type inputs MUST have enforced maximum lengths at the schema layer (enforced before execution).
- **NFR-007 — Logging**: All external provider calls, agent pipeline steps, and exception events MUST be written to the application log with sufficient context to diagnose failures post-hoc.
- **NFR-008 — Security (pre-production)**: Before any public deployment, endpoints MUST be protected by authentication and authorization. Secrets MUST NOT appear in logs.
- **NFR-009 — Portability**: The system MUST operate correctly in a local development environment with no external credentials by activating all mock fallback paths.

### Key Entities

- **AnalysisRequest**: Symbols (1–25), mode (`intraday`/`swing`/`both`), optional timeframe overrides.
- **ScreenerRequest**: Universe config, `top_n`, mode — drives screener pipeline.
- **OHLCVPoint**: Timestamp, open, high, low, close, volume — raw candle data per symbol.
- **TechnicalAnalysisResult**: Mode, signal, composite score, indicators dictionary, summary text.
- **BacktestResult**: Win rate, profit factor, max drawdown, trade count, strategy parameters used.
- **ArticleItem**: Headline, source, published timestamp, sentiment label, sentiment score.
- **FinalRecommendation**: Symbol, signal, composite score, entry price, stop-loss, target, LLM reasoning fields.
- **StockAnalysisResult**: Aggregates `TechnicalAnalysisResult`, `BacktestResult`, news items, `FinalRecommendation` for one symbol.
- **AnalysisHistory** (DB): Persisted snapshot of `StockAnalysisResult` — symbol, timestamp, scores, recommendation.
- **BacktestHistory** (DB): Persisted backtest result — symbol, strategy, stats, timestamp.
- **PaperTradingAccount**: Account ID, starting capital, current equity, unrealised P&L.
- **PaperOrder**: Order ID, symbol, direction, quantity, requested price, status (pending/filled/cancelled).
- **PaperPosition**: Position ID, symbol, entry price, quantity, stop-loss, target, notes, unrealised P&L.
- **PaperTradeHistory**: Closed trade record — entry price, exit price, P&L, timestamps.

---

## API Contracts

### Health
| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/health` | — | `{ status, disclaimer, environment }` |

### Analysis
| Method | Path | Request Schema | Response Schema |
|--------|------|---------------|----------------|
| POST | `/analysis/full` | `AnalysisRequest` | `FullAnalysisResponse` |
| POST | `/analysis/technical` | `AnalysisRequest` | `TechnicalAnalysisResult` |
| POST | `/analysis/news` | `AnalysisRequest` | news + sentiment per symbol |
| POST | `/analysis/backtest` | `AnalysisRequest` | `BacktestResult` per symbol |
| POST | `/analysis/final-recommendation` | `AnalysisRequest` | `FinalRecommendation` per symbol |
| POST | `/analysis/rankings` | `AnalysisRequest` | `RankingsResponse` (ranked list) |
| POST | `/analysis/screener/full` | `ScreenerRequest` | `ScreenerResponse` (ranked shortlist) |

### Stocks
| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/stocks/analyze` | `AnalysisRequest` (single symbol) | `AnalysisResponse` |

### Paper Trading
| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/paper-trading/dashboard` | — | `PaperTradingDashboardResponse` |
| GET | `/paper-trading/account` | — | Account summary |
| POST | `/paper-trading/account/reset` | — | `{ success: true }` |
| POST | `/paper-trading/orders` | `PaperOrderCreateRequest` | Created order |
| POST | `/paper-trading/orders/{order_id}/cancel` | — | Updated order (status: cancelled) |
| POST | `/paper-trading/positions/{position_id}/close` | — | Closed position + P&L |
| PATCH | `/paper-trading/positions/{position_id}` | Stop/target/notes fields | Updated position |
| POST | `/paper-trading/from-recommendation` | `FinalRecommendation` | Pre-filled paper order |
| GET | `/paper-trading/symbols` | — | Available symbol list |

**Common error responses** (all endpoints):
- `422 Unprocessable Entity` — validation failure (malformed input, out-of-range values).
- `500 Internal Server Error` — unhandled exception (logged; must include `detail` in response body).

---

## Data Flow

```
[User / Frontend]
      │
      ▼  POST /analysis/screener/full  (ScreenerRequest)
[FastAPI Route → RouterAgent]
      │
      ▼
[OrchestratorAgent.run_screener()]
      │
      ├─► [ScreenerService]
      │       │ 1. Load Nifty 500 universe
      │       │ 2. FyersService.fetch_ohlcv() → OHLCVPoint[]
      │       │    (fallback: generate_mock_ohlcv)
      │       │ 3. Data quality gate (drop failing symbols)
      │       │ 4. Broad trend eligibility filter
      │       │ 5. Compute weighted screener score
      │       │ 6. Return top_n symbols
      │       ▼
      │   [Symbol Shortlist]
      │
      ├─► Per-symbol loop (sequential):
      │       │
      │       ├─► [TechnicalAnalysisAgent → TechnicalAnalysisService]
      │       │       Computes indicators + score → TechnicalAnalysisResult
      │       │
      │       ├─► [BacktestAgent → BacktestService]
      │       │       Runs backtrader strategy → BacktestResult
      │       │       Persists → backtest_history (DB)
      │       │
      │       ├─► [NewsAnalysisAgent → NewsService + SentimentService]
      │       │       Fetches articles + scores sentiment → ArticleItem[]
      │       │
      │       └─► [RecommendationAgent → LLMService + RecommendationService]
      │               Builds prompt → Groq API (20 s timeout)
      │               (fallback: deterministic reasoning)
      │               Produces → FinalRecommendation
      │               Persists → analysis_history (DB)
      │
      ├─► [RankingAgent → RankingService]
      │       Ranks StockAnalysisResult[] by composite score → descending
      │
      ▼
[ScreenerResponse]  →  Frontend CandidateTable / StockDetailPanel

[Optional paper trade path]
      User selects BUY candidate
      │
      ▼  POST /paper-trading/from-recommendation
[PaperTradingService]
      │ Creates PaperOrder (status: filled)
      │ Creates PaperPosition (entry, stop, target)
      │ Persists to paper_trading_accounts / positions
      ▼
[PaperTradingDashboardResponse]
```

---

## Error Handling

| Scenario | Detection Point | System Behaviour | User-Facing Output |
|----------|----------------|-----------------|-------------------|
| FYERS credentials absent | `FyersService.fetch_ohlcv()` startup | Activate mock OHLCV generator | `data_warning: "Using mock market data"` in response |
| FYERS API error mid-run | `FyersService` HTTP exception | Log error; skip symbol or use mock | Symbol result includes `data_warning` |
| News provider unavailable | `NewsService.fetch()` exception | Generate mock articles | `data_warning: "Using mock news"` |
| LLM unavailable / timeout | `LLMService` request timeout (20 s) | Activate deterministic reasoning | `data_warning: "LLM unavailable; using fallback reasoning"` |
| LLM schema mismatch | Response JSON validation | Reject and activate fallback | Same as LLM unavailable |
| Symbol not found / delisted | OHLCV returns empty candles | Mark symbol as failed quality gate; skip | Symbol omitted or returned with `signal: REJECT` |
| Input validation failure | Pydantic schema layer | Raise `RequestValidationError` | HTTP 422 with field-level error detail |
| DB write failure | SQLAlchemy commit | Log error; pipeline continues | Analysis result still returned; `data_warning` in response |
| All symbols filtered out | Post-screener shortlist | Return empty `results: []` | HTTP 200 with empty list and informative `message` field |
| Unhandled exception | FastAPI exception handler | Log full traceback | HTTP 500 with `{ detail: "Internal server error" }` |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A full screener run over the Nifty 500 universe returning 10 shortlisted and fully analyzed candidates completes within 90 seconds in mock-data mode.
- **SC-002**: 100% of analysis requests for 1–25 symbols return a structured response (never a raw exception) regardless of external provider availability.
- **SC-003**: Every `FinalRecommendation` in a response contains human-readable reasoning — either LLM-generated or deterministic fallback — with no empty fields.
- **SC-004**: Paper trading positions opened from a recommendation reflect the correct entry price, stop-loss, and target from the source recommendation without manual re-entry.
- **SC-005**: The system operates fully (with mock data) from a clean environment with no external API credentials configured.
- **SC-006**: All analysis and backtest results are retrievable from the database after the request completes (verified by querying `analysis_history` and `backtest_history`).
- **SC-007**: Invalid inputs (>25 symbols, negative quantities) are rejected before any external call is made, and the error response identifies the offending field.

---

## Assumptions

- FYERS is the primary market data provider for Indian equities; no other live data source is in scope for Phase 1.
- Users are assumed to operate the system locally or in a trusted private network; no public-facing authentication is required for Phase 1 (but is required before any production exposure).
- SQLite is sufficient for single-user / local deployments; migration to a managed database is a Phase 2 concern.
- The Nifty 500 symbol universe is configured statically in the application; dynamic universe management is out of scope.
- Groq is the LLM provider; all LLM governance rules (temperature, timeout, deterministic fallback) apply to Groq's API behaviour.
- All external provider failures in Phase 1 are handled by mock/deterministic fallback — no circuit breakers or retry logic is in scope for this phase.
- Mobile support is out of scope; the React frontend is desktop-browser-only.
- Real-time streaming (WebSockets, server-sent events) is out of scope; all data is fetched on request.
