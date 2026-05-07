# Consultation Document — Trading System
*Generated: 2026-04-17*

---

## 1. Problem Statement

Retail traders in Indian equity markets (NSE/BSE, Nifty 500 universe) lack affordable, integrated tooling that can rapidly screen hundreds of stocks, surface technically valid setups, enrich them with news sentiment, back-test historical performance, and produce a coherent, explainable trade plan — all within a single workflow. Existing retail platforms either provide raw charts without synthesis, or offer black-box signals with no reasoning. Manual research across independent tools (charting, news, backtesting) is time-intensive, error-prone, and unauditable.

The system addresses this gap by automating the full analysis pipeline — from universe scanning through final recommendation — while keeping a human trader in the decision seat at every step.

---

## 2. Business Goals

| # | Goal | Success Metric |
|---|------|---------------|
| 1 | Reduce per-stock research time from hours to minutes | End-to-end screener + analysis completes for a shortlist within 60–90 seconds |
| 2 | Surface only high-conviction candidates from the Nifty 500 universe | Top-N shortlist with weighted screener score explains inclusion criteria |
| 3 | Provide traceable, auditable recommendations | Analysis and backtest history persisted; LLM reasoning stored with structured schema |
| 4 | Enable risk-free strategy validation via paper trading | Paper trading simulator mirrors realistic fill logic without hitting live markets |
| 5 | Support future production hardening without architectural rework | Modular agent/service architecture allows incremental addition of auth, background jobs, and managed DB |
| 6 | Stay advisory-only; avoid regulatory risk from auto-execution | System never submits a live order; all execution is a deliberate human action |

---

## 3. Target Users

### Primary — Independent Swing Traders
- Trade Indian equities (NSE/BSE) manually with 1–10 day holding periods.
- Comfortable with technical indicators (EMA, RSI, MACD, Supertrend) but want automated aggregation.
- Need actionable BUY / WATCH / REJECT signals with supporting rationale, not just raw charts.
- Want to validate ideas in a paper account before committing capital.

### Secondary — Intraday Traders
- Use the same analysis engine but with intraday candle modes.
- Higher urgency on latency; benefit from the screener's staged pipeline to avoid manually checking 500 symbols.

### Tertiary — Quantitatively Curious Retail Investors
- Less active; use backtest history and news sentiment to understand why a stock qualifies.
- Value the LLM-generated reasoning bullets and risk factors as a learning tool.

### Out of Scope (current phase)
- Institutional / algorithmic traders requiring co-location, FIX protocol, or sub-second execution.
- Users outside Indian equity markets.

---

## 4. High-Level System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React + Vite)                  │
│  Scanner UI → CandidateTable → StockDetailPanel → PaperTrading  │
└─────────────────────────┬───────────────────────────────────────┘
                           │  HTTP REST (JSON)
┌─────────────────────────▼───────────────────────────────────────┐
│                     FastAPI Backend                              │
│  Routes: /analysis/* | /stocks/* | /paper-trading/* | /health   │
│                           │                                      │
│               ┌───────────▼───────────┐                         │
│               │     Router Agent      │                         │
│               └───────────┬───────────┘                         │
│               ┌───────────▼───────────┐                         │
│               │  Orchestrator Agent   │  ← coordinates pipeline │
│               └──┬────┬────┬────┬────┘                         │
│                  │    │    │    │                               │
│       ┌──────────▼┐ ┌─▼──┐ ┌▼───────┐ ┌────────────────────┐ │
│       │ Technical │ │Back│ │  News  │ │ Recommendation     │ │
│       │ Analysis  │ │test│ │Analysis│ │ Agent → LLM Service│ │
│       │  Agent    │ │Agent│ │ Agent  │ │                    │ │
│       └──────────┘ └────┘ └────────┘ └────────────────────┘ │
│                                │                               │
│                    ┌───────────▼──────────┐                    │
│                    │    Ranking Agent      │                   │
│                    └───────────┬──────────┘                    │
│                                │                               │
│            ┌───────────────────▼──────────────────┐           │
│            │           Services Layer              │           │
│            │  FyersService | TechnicalAnalysis     │           │
│            │  BacktestService | NewsService        │           │
│            │  SentimentService | LLMService        │           │
│            │  PaperTradingService | Screener       │           │
│            └───────────────────┬──────────────────┘           │
│                                │                               │
│            ┌───────────────────▼──────────────────┐           │
│            │          Data Layer (SQLite)           │           │
│            │  analysis_history | backtest_history  │           │
│            │  paper_trading_accounts | positions   │           │
│            │  orders | trade_history               │           │
│            └──────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                    │                   │
          ┌─────────▼──────┐   ┌───────▼────────┐
          │  FYERS API      │   │   LLM (Groq)   │
          │  (live OHLCV)   │   │  + News API    │
          │  ↓ fallback:    │   │  ↓ fallbacks:  │
          │  mock OHLCV     │   │  deterministic │
          └────────────────┘   └────────────────┘
```

### Key Pipeline (Screener → Analysis → Recommendation)

1. **Universe Scan** — `ScreenerService` loads the Nifty 500 universe; fetches OHLCV for all symbols via `FyersService`.
2. **Data Quality Gate** — symbols failing minimum candle count or liquidity thresholds are dropped.
3. **Broad Trend Eligibility** — EMA/price-structure filter removes clearly downtrending names.
4. **Weighted Screener Score** — multi-factor composite score (momentum, volume, volatility) ranks the filtered universe.
5. **Top-N Shortlist** — configurable `top_n` candidates proceed to deep analysis.
6. **Deep Analysis (per symbol)** — `OrchestratorAgent` runs Technical → Backtest → News agents in sequence.
7. **LLM Reasoning** — `RecommendationAgent` calls `LLMService` (Groq) to generate structured bullets, risk factors, invalidation signals, and a summary.
8. **Final Recommendation** — `RecommendationService` integrates signals into a `FinalRecommendation` (BUY / WATCH / REJECT) with score and trade plan.
9. **Rankings** — `RankingAgent` sorts the shortlist and returns the ranked `ScreenerResponse` to the frontend.
10. **Paper Trading** — user optionally prefills a paper order from any recommendation; `PaperTradingService` handles simulated fill, position tracking, and P&L.

---

## 5. Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React 18 + TypeScript (Vite) | Dashboard, scanner, detail panel, paper trading UI |
| Backend | Python 3.x + FastAPI | REST API; synchronous workers (uvicorn) |
| Agent Layer | Custom agent classes | OrchestratorAgent, RouterAgent + 5 domain agents |
| Technical Analysis | pandas + `ta` library | EMA, SMA, MACD, RSI, VWAP, Supertrend, volume |
| Backtesting | `backtrader` library | Historical strategy replay |
| LLM | Groq API (deterministic fallback) | Structured JSON reasoning (temp 0.2, 20 s timeout) |
| Market Data | FYERS API | Live OHLCV; mock candle fallback when credentials absent |
| News & Sentiment | Marketaux API + custom sentiment | Mock article fallback present |
| Database | SQLite + SQLAlchemy ORM | Local file; Alembic migrations not yet added |
| Environment | Python venv / uv | `backend/requirements.txt` |
| Logging | Python `logging` + file handler | `logs/trading_system.log` |

---

## 6. Current State & Known Gaps

### What Is Working (Phase 1)
- Full screener pipeline (universe → shortlist → deep analysis → ranked results).
- Technical analysis with 7+ indicators and composite scoring.
- Backtest execution with history persistence.
- LLM-generated reasoning with deterministic fallback.
- Paper trading simulator (orders, positions, P&L, reset).
- React dashboard with scan history (localStorage), sample data toggle, and detail panel.
- Mock fallback for all three external providers (FYERS, news, LLM).

### Priority Gaps (Pre-Production)
1. **No authentication or authorization** — all endpoints are publicly accessible.
2. **Synchronous request blocking** — heavy analysis (screener/full) blocks HTTP workers; no background job queue.
3. **SQLite only** — not suitable for multi-worker or cloud deployments.
4. **No circuit breakers or retry logic** for FYERS, LLM, or news providers.
5. **No DB migrations** — schema changes require manual intervention.
6. **No observability** — no metrics, traces, or alerting beyond file logs.

---

## 7. Recommended Next Steps

| Phase | Timeline | Key Deliverables |
|-------|----------|-----------------|
| A — Stabilize | 0–2 weeks | Auth middleware, structured logging, request size limits |
| B — Reliability | 2–6 weeks | Background job queue (Celery/RQ), circuit breakers, Alembic + managed DB |
| C — Observability | 4–8 weeks | Prometheus metrics, OpenTelemetry traces, LLM governance logging |
| D — Production | Ongoing | Containerization (Docker), CI/CD, load testing, security audit |

---

*This document reflects the state of the codebase as of 2026-04-17. All recommendations are advisory and intended to inform engineering planning decisions.*
