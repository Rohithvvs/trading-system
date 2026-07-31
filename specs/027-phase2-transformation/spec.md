# Feature Specification: Phase 2 Product Architecture & Modernization Transformation

**Feature Branch**: `027-phase2-transformation`  
**Created**: 2026-07-31  
**Status**: Approved Specification  
**Input**: Transformation prompt: "Phase 2 Transformation Specification — Transform Multi-user Trading Platform into Personal AI Trading Research Platform"

---

## 1. Executive Summary

This Specification defines the Phase 2 Product Architecture and Modernization Transformation for the trading system. Phase 1 established a single-owner foundation by removing multi-tenant user authentication, session overhead, and generic SaaS user management. Phase 2 defines the complete structural evolution of the product from a multi-user retail trading portal into a unified **Personal AI Trading Research Platform**.

This transformation refactors the product surface, user navigation, frontend layout, API classification, database usage, backend services, and configuration paradigms while strictly maintaining the core engines: the Recommendation Engine, Market Scanner, AI Agents, Technical Indicators, Scoring algorithms, Backtesting engines, Paper Trading Execution models, Market Data Pipelines, and Scheduler logic.

---

## 2. Current vs Future Product

### 2.1 Identity & Purpose
* **Current Product Identity**: Hybrid retail trading application with leftover multi-tenant admin/retail tab splits, disconnected scanner components, separate paper desk views, and fragmented diagnostic screens.
* **Future Product Identity**: **Personal AI Trading Research Platform** — an integrated, single-operator workstation designed for quantitative research, algorithmic recommendation evaluation, automated opportunity scanning, and disciplined paper portfolio execution.

### 2.2 Product Comparison Matrix

| Dimension | Current Product (Phase 1 Baseline) | Target Product (Phase 2 Master Spec) |
|---|---|---|
| **Primary User** | Generic retail user / system admin split | Single Quant Trader / Research Operator |
| **Primary Workflow** | Disjointed tab clicking (Markets → Scanner → Paper → Logs) | End-to-end continuous lifecycle (Overview → Scan → Research → Trade → Analytics) |
| **Core Capabilities** | Basic market scanning, isolated recommendation cards, manual paper order page | Real-time market health tracking, deep research workstation, structured recommendation review, unified paper trading desk, institutional analytics |
| **Removed Capabilities** | Legacy retail vs admin navigation splits, manual user session controls, redundant mock authentication routes | Clean single-operator experience, zero multi-tenant UI artifacts |
| **Architectural Focus** | Modular SaaS UI with separate admin toggles | High-density quantitative research environment with instant data-to-execution pathways |

---

## 3. Transformation Principles

1. **Zero Core Logic Alteration**: Recommendation algorithms, scanner vectorization, indicator math (EMA, Supertrend, MACD), signal scoring, backtesting models, and paper execution rules MUST remain 100% bit-for-bit identical.
2. **Unified Product Surface**: Merge scattered admin/retail interfaces into a cohesive single-operator control deck.
3. **Research-Driven Workflow**: Every stock recommendation must provide an immediate path from high-level signal down to granular technical indicators, AI agent rationale, and paper trade execution.
4. **Data Continuity & Zero Downtime**: Schema and API transformations must preserve all existing historical candles, scan snapshots, paper trading positions, and broker token states.
5. **Technical Debt Elimination**: Eliminate unused frontend pages, deprecated backend services, obsolete schemas, and legacy configuration properties identified during baseline analysis.

---

## 4. Frontend Transformation

### 4.1 Page-by-Page Transformation Matrix

| Current Page | Future Page | Decision | Rationale |
|---|---|---|---|
| `/admin/command` (Central Command) | `/` (Unified Dashboard) | **MERGE / RENAME** | Promoted to root dashboard; merges market status, scanner summary, and top recommendations. |
| `/markets` (Markets Page) | `/markets` (Market Watch & Sector Health) | **MODIFY** | Replaced basic grid with sector relative strength, market regime overlays, and breadth indicators. |
| `/scanner` (Scanner View) | `/research/scanner` (Opportunity Scanner) | **MODIFY / RENAME** | Relocated under Research domain; adds live filter control and instant candidate drawer. |
| `/paper` (Paper Desk) | `/trading/paper-desk` (Paper Trading Desk) | **MODIFY / RENAME** | Merges PaperOrderPage into a single drawer-based execution and portfolio management workstation. |
| `/performance` (Performance Page) | `/analytics/performance` (Quant Analytics) | **MODIFY / RENAME** | Expanded with win-rate analytics, holding period metrics, and scanner signal efficiency charts. |
| `/diagnostics` (Diagnostics) | `/system/diagnostics` (System Health) | **MODIFY / RENAME** | Relocated under System domain; integrates broker status, scheduler state, and DB storage. |
| `/admin/logs` (System Logs) | `/system/logs` (Platform Audit & Logs) | **MODIFY / RENAME** | Relocated under System domain; simplified single-operator live log streaming. |
| N/A | `/research/workstation` (Stock Workstation) | **NEW** | Deep-dive technical view merging chart overlays, AI rationale, and backtest history for any symbol. |

### 4.2 Detailed Page Layout Transformations

#### A. Unified Dashboard (`/`)
* **Current Layout**: Disconnected cards for scanner summary, simple candidate table, and developer mode toggle.
* **Future Layout**: Modern 4-quadrant layout:
  1. Top Banner: Market Health & Regime Permissiveness (MarketPermissionService output).
  2. Main Left: Today's High-Conviction AI Recommendations.
  3. Main Right: Scanner Operating Status & FYERS Broker Data Stream Health.
  4. Bottom Full: Open Paper Portfolio Summary & Daily Equity Curve.
* **New Components**: `MarketRegimeBanner`, `TopRecommendationsWidget`, `PaperPortfolioSummaryCard`.
* **User Flow**: Single-glance status review; click any recommendation card to open the Stock Workstation or execute a paper order.

#### B. Paper Trading Desk (`/trading/paper-desk`)
* **Current Layout**: Standalone `PaperTradingPage.tsx` and separate `PaperOrderPage.tsx` causing fragmented order entry.
* **Future Layout**: Split-screen workstation:
  1. Left Panel: Active Orders, Open Positions, Closed Trades Table.
  2. Right Drawer: Slide-out Order Execution & Risk Management Drawer (`OrderDrawer.tsx`).
* **Removed Components**: Standalone `PaperOrderPage.tsx` full-screen page.
* **Navigation Changes**: Accessible directly from sidebar or via "Trade" triggers on recommendation cards.

---

## 5. Navigation Transformation

### 5.1 Navigation Architecture
The legacy split between `RETAIL_NAV` and `ADMIN_NAV` is completely replaced by a structured, domain-grouped sidebar and unified header header.

```
[ SIDEBAR NAVIGATION ]
├── 1. Overview
│   └── Dashboard (`/`)
├── 2. Research & Discovery
│   ├── Opportunity Scanner (`/research/scanner`)
│   ├── Stock Workstation (`/research/workstation`)
│   └── Market Regime & Sectors (`/research/markets`)
├── 3. Execution & Portfolio
│   ├── Paper Trading Desk (`/trading/paper-desk`)
│   └── Watchlist (`/trading/watchlist`)
├── 4. Quantitative Analytics
│   └── Performance & Win-Rate (`/analytics/performance`)
└── 5. Platform Control
    ├── FYERS Broker Integration (`/system/broker`)
    ├── Diagnostics & Health (`/system/diagnostics`)
    └── System Logs (`/system/logs`)
```

### 5.2 Menu Rationale
* **Overview**: Instant situational awareness for the operator upon opening the platform.
* **Research & Discovery**: Groups all scanning, technical analysis, and symbol research into a single workflow domain.
* **Execution & Portfolio**: Dedicated domain for paper trade management, position tracking, and target watchlists.
* **Quantitative Analytics**: Isolates portfolio performance, signal quality analytics, and strategy verification metrics.
* **Platform Control**: Consolidates broker OAuth status, background scheduler health, database storage, and system logs.

---

## 6. Dashboard Transformation

The future dashboard (`/`) acts as the nerve center for the Personal AI Trading Research Platform.

### Widget Specifications

1. **Market Health & Permissiveness Widget**: Displays real-time Nifty regime (Bullish/Bearish/Sideways) and `MarketPermissionService` state (Permissive vs Restricted).
2. **Scanner Live Status Widget**: Shows active scan cycle, last execution timestamp, total symbols evaluated (e.g., Nifty 500), and candle processing latency.
3. **Today's Top AI Recommendations**: Displays highest-scoring stocks filtered by minimum conviction score, showing symbol, signal (BUY/SELL), entry target, stop-loss, and AI agent rationale summary.
4. **Paper Portfolio Summary**: Displays real-time paper account balance, total equity, open P&L, day P&L, and margin utilization.
5. **Quick Execution Bar**: One-click action to run an on-demand market scan or initiate a paper trade.
6. **System Alerts & Notifications**: Real-time toast notifications for FYERS token expiration, scan completion, or stop-loss hits.

---

## 7. User Workflow Transformation

### 7.1 Recommendation Workflow
```
[ Dashboard ] 
      │
      ▼
[ Run Market Scan ] ──► (Scanner executes over Nifty 500)
      │
      ▼
[ Recommendation List ] ──► (Filter by Score > 75, Regime Permissive)
      │
      ▼
[ Stock Workstation ] ──► (Inspect Indicators, Supertrend, AI Rationale)
      │
      ▼
[ Order Execution Drawer ] ──► (Pre-filled Target, Stop-Loss, Quantity)
      │
      ▼
[ Paper Trade Placed ] ──► (Position appears in Paper Desk & Dashboard)
```

### 7.2 Paper Trading Execution Workflow
1. **Selection**: User selects a recommendation from the Dashboard or Scanner table.
2. **Review**: System opens `OrderDrawer` pre-populated with symbol, signal type, calculated risk-reward ratio, entry price, and default stop-loss.
3. **Order Placement**: User clicks "Submit Paper Order". Request hits `POST /api/v1/paper-trading/orders` under default single-owner context (`00000000-0000-0000-0000-000000000001`).
4. **Position Tracking**: Order transitions from `PENDING` to `FILLED`. Position appears live in `/trading/paper-desk`.
5. **Trade Management**: User can modify trailing stop-loss, take-profit levels, or trigger a manual market exit.
6. **Trade Exit & Analytics**: On exit (stop hit or manual), P&L is realized, position closes, and analytics update automatically in `/analytics/performance`.

---

## 8. Backend Transformation

### Service Classification

| Backend Service | Classification | Future Responsibilities | Dependencies | Risk |
|---|---|---|---|---|
| `scanner_service.py` | **KEEP** | Unchanged market scanning, candle fetch, vectorization. | FYERS API, PostgreSQL | Low |
| `analysis_service.py` | **KEEP** | Unchanged scoring, recommendation generation, signal filters. | `scanner_service` | Low |
| `paper_trading_service.py` | **MODIFY** | Simplified order matching and position tracking hardcoded to single owner context. | PostgreSQL | Low |
| `broker_token_service.py` | **MODIFY** | Encrypted storage & refresh of FYERS tokens under single owner context. | Fernet Cryptography | Low |
| `market_permission_service.py` | **KEEP** | Unchanged market permissiveness calculation. | Market Data | Low |
| `scheduler_service.py` | **KEEP** | Automated cron scheduling for market scans and daily candle updates. | APScheduler | Low |
| `governance_service.py` | **KEEP** | In-process command routing for experiment management. | CLI Handlers | Low |
| `auth_service.py` | **REMOVE** | Completely removed in Phase 1; clean up residual imports. | None | Low |
| `user_profile_service.py` | **REMOVE** | Completely removed in Phase 1; clean up residual imports. | None | Low |

---

## 9. API Transformation

### Endpoint Classification & Mapping

| Path | Verb | Classification | Future Purpose & Changes |
|---|---|---|---|
| `/api/v1/scanner/scan` | POST | **KEEP** | Trigger manual market scan cycle. Unchanged. |
| `/api/v1/scanner/latest` | GET | **KEEP** | Fetch latest scan results. Unchanged. |
| `/api/v1/analysis/recommendations` | GET | **KEEP** | Fetch active AI recommendations. Unchanged. |
| `/api/v1/paper-trading/accounts` | GET | **MODIFY** | Returns single owner paper account without requiring auth headers. |
| `/api/v1/paper-trading/orders` | POST | **MODIFY** | Places paper order for single owner account. |
| `/api/v1/broker-tokens/fyers` | GET/POST | **MODIFY** | Manages FYERS API credentials under single owner context. |
| `/fyers/auth/url` | GET | **KEEP** | Initiates FYERS OAuth login URL generation. |
| `/fyers/auth/exchange` | POST | **KEEP** | Exchanges FYERS auth code for access token. |
| `/api/v1/governance/routes` | GET | **KEEP** | Exposes CLI command routing table. |
| `/api/v1/auth/*` | ALL | **REMOVE** | Permanently deleted. Return 404 if called. |

---

## 10. Database Transformation

### Table Classification

| Table Name | Classification | Migration Action | Impact |
|---|---|---|---|
| `stock_candles` | **KEEP** | None. Preserved completely. | Zero |
| `scan_snapshots` | **KEEP** | None. Preserved completely. | Zero |
| `recommendation_records` | **KEEP** | None. Preserved completely. | Zero |
| `paper_trading_accounts` | **MODIFY** | Drop FK constraint to `users.id`. Set default `user_id = '00000000-0000-0000-0000-000000000001'`. | High (migration required) |
| `paper_positions` | **KEEP** | Linked to `paper_trading_accounts`. | Zero |
| `paper_orders` | **KEEP** | Linked to `paper_trading_accounts`. | Zero |
| `broker_tokens` | **MODIFY** | Drop FK constraint to `users.id`. Set default `user_id = '00000000-0000-0000-0000-000000000001'`. | High (migration required) |
| `fyers_tokens` | **KEEP** | Preserved for broker OAuth token state. | Zero |
| `users`, `user_sessions`, `user_profiles`, `otps`, `devices`, `audit_logs` | **REMOVE** | Dropped via Alembic migration in Phase 1. Clean up lingering model schemas. | High |

---

## 11. Infrastructure & Configuration Transformation

### 11.1 Configuration Simplification
* **Environment Variables**:
  * **Removed**: `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`.
  * **Retained**: `DATABASE_URL`, `FYERS_CLIENT_ID`, `FYERS_SECRET_KEY`, `FYERS_REDIRECT_URI`, `SECRET_KEY` (Fernet encryption), `LOG_LEVEL`.
* **Logging**: Single operator stream logging outputting to stdout and persistent system log files (`logs/app.log`).
* **Monitoring**: Integrated in-app `/system/diagnostics` endpoint tracking DB connection pool size, memory utilization, and background scheduler tasks.

---

## 12. Technical Debt Reduction

### Technical Debt Cleanup Roadmap

1. **Dead Frontend Code Removal**:
   * Delete redundant `PaperOrderPage.tsx` (functionality unified into `PaperTradingPage.tsx` + `OrderDrawer.tsx`).
   * Remove unused auth input components (`AuthInput.tsx`, `PasswordInput.tsx`, `AuthLayout.tsx`).
   * Clean up unused styling rules in `styles.css` and `shell.css`.
2. **Dead Backend Code Removal**:
   * Remove obsolete auth schemas (`backend/app/schemas/auth.py`).
   * Remove orphan utility scripts (`check_token.py`, `debug_pos.py`, `drop_scan_snapshots.py` where superseded by Alembic).
3. **API Utility Consolidation**:
   * Unify overlapping endpoint responses between `/api/v1/scanner/latest` and `/api/v1/analysis/recommendations`.

---

## 13. Migration Strategy

### Step-by-Step Rollout Order

```
[ Phase 2.1: DB Schema Verification ]
  └── Confirm Phase 1 Alembic migrations (FK removal & single owner defaults).
        │
        ▼
[ Phase 2.2: Backend Service Refactoring ]
  └── Apply single-owner context across paper trading & broker token endpoints.
        │
        ▼
[ Phase 2.3: Frontend Route & Layout Overhaul ]
  └── Implement new domain navigation (`navConfig.tsx`), AppShell, and unified `/` Dashboard.
        │
        ▼
[ Phase 2.4: Unified Execution Drawer Integration ]
  └── Connect `OrderDrawer.tsx` to Recommendation Cards on Dashboard & Scanner.
        │
        ▼
[ Phase 2.5: Technical Debt Cleanup ]
  └── Remove dead pages (`PaperOrderPage.tsx`), obsolete schemas, and unused env vars.
```

### Risk & Rollback Strategy
* **Database Safety**: Take PostgreSQL dump (`pg_dump`) prior to deploying backend route updates.
* **Feature Flags**: Use simple environment flag `ENABLE_PHASE2_UI=true` during staging validation.
* **Rollback Plan**: Revert frontend build artifacts and restore backend release commit if navigation regress passes.

---

## 14. Out of Scope

The following core modules are explicitly **OUT OF SCOPE** and MUST NOT be modified during Phase 2 transformation:
- Recommendation Engine scoring and ranking algorithms (`backend/app/services/recommendation_service.py`).
- Market Scanner vectorization and indicator calculation routines (`backend/app/services/scanner_service.py`).
- AI Trading Agents and LLM prompt chain logic.
- Technical Indicator math (EMA50, EMA200, MACD, RSI, Supertrend).
- Backtesting engines and historical simulation modules.
- Paper Trading Order Matching Engine mechanics (slippage, fill execution).
- FYERS WebSocket market data ingestion pipeline.
- Scheduler trigger timing and cron intervals.

---

## 15. Future Phase Readiness Assessment

Phase 2 establishes clean architectural interfaces supporting upcoming development phases without requiring breaking changes later:

1. **Research Dashboard Phase**: Dedicated `/research/workstation` route provides layout slots for deep LLM rationale visualization.
2. **Experiment Framework Phase**: Preserves `/api/v1/governance/routes` and `experiments` database tables for backtesting parameter sweeps.
3. **Adaptive Strategies & Weighting**: Recommendation record schemas preserve raw feature vectors allowing dynamic re-weighting in future phases.
4. **Trading Intelligence Phase**: Single-owner architecture enables zero-friction sidecar integrations for automated webhooks or trade execution bots.

---

## User Scenarios & Testing

### User Story 1 — Unified Command Center & One-Click Research (Priority: P1)

As the single quant operator,  
I want a consolidated root Dashboard (`/`) showing market permissiveness, live scanner status, and top AI recommendations,  
So that I can assess market conditions and dive directly into technical research without navigating multiple disconnected tabs.

**Why this priority**: Core value proposition of transforming into a Personal AI Trading Research Platform.

**Independent Test**: Load `/` in browser; verify market regime banner, scanner status widget, and top recommendation cards render with zero auth prompts.

**Acceptance Scenarios**:
1. **Given** the application is open at `/`, **When** a user views the dashboard, **Then** market permissiveness state and top AI recommendations are visible immediately.
2. **Given** a recommendation card on `/`, **When** clicking "Inspect", **Then** the app navigates to `/research/workstation?symbol=XYZ` displaying indicator details.

---

### User Story 2 — Streamlined Paper Trading Execution from Recommendation (Priority: P2)

As the single quant operator,  
I want to execute a paper trade directly from any recommendation card using a slide-out order drawer,  
So that I can seamlessly act on AI signals without opening a separate order page.

**Why this priority**: Eliminates workflow friction between signal discovery and trade execution.

**Independent Test**: Click "Trade" on a recommendation card; verify `OrderDrawer` opens pre-populated with symbol, entry price, and stop-loss; submitting creates a live paper order under owner ID `00000000-0000-0000-0000-000000000001`.

**Acceptance Scenarios**:
1. **Given** a recommendation card, **When** clicking "Trade", **Then** the `OrderDrawer` slides open with pre-calculated position sizing.
2. **Given** the `OrderDrawer`, **When** submitting the order, **Then** the paper order is created and immediately visible in `/trading/paper-desk`.

---

## Success Criteria

- **SC-001**: 100% of frontend pages comply with the new single-operator domain navigation (`Overview`, `Research`, `Execution`, `Analytics`, `System`).
- **SC-002**: 0% regression in core trading engine metrics: Scanner accuracy, Recommendation scoring, and Paper Trading fill logic remain 100% identical.
- **SC-003**: 100% of legacy retail/admin split navigation links removed from frontend code.
- **SC-004**: Technical debt reduction completed: `PaperOrderPage.tsx` and obsolete auth schemas removed.

---

## Assumptions

- The platform is deployed in a single-operator environment (workstation or private server).
- FYERS API tokens are refreshed under the single application owner context.
- Existing database tables (`stock_candles`, `scan_snapshots`, `paper_positions`) are intact and populated.
