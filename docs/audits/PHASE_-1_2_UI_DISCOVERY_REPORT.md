# PHASE -1.2 — UI DISCOVERY AUDIT
**Objective:** Reverse-engineer and document the existing frontend exactly as implemented, with no modifications or inferred future features. Treat the repository as the single source of truth.

---

## 1. Overall Frontend Architecture & State Strategy

- **Framework**: React (SPA), Vite, TypeScript.
- **Routing**: Manual state-based routing (`mainView` state in `App.tsx` / `Dashboard.tsx`) with History API `pushState` for basic URL manipulation. No third-party router (e.g., `react-router-dom`) is used.
- **State Management**: React Context/Local State (useState, useMemo, useEffect). Heavy reliance on prop drilling and custom hooks (e.g., `useTradingDashboard`, `useInfrastructureHealth`). No Redux, Zustand, or MobX present.
- **Data Fetching**: Custom fetch wrapper (`fetchWithDiagnostics` in `api.ts`) against the FastAPI backend.
- **Real-Time Data**: Standard WebSocket API (`ws://.../ws/ticks`) for live price ticks, combined with periodic HTTP polling (`setInterval` logic in hooks) for state reconciliation.
- **Theme/Styling**: Vanilla CSS with CSS variables (`styles.css`). Theme mode state (`light`/`dark`) sets `data-theme` on the `<html>` root element.

---

## 2. Screen Inventory & Specifications

### 2.1 Main Shell (App.tsx / Dashboard.tsx)
- **Screen Name**: App Shell
- **Purpose**: Acts as the main layout, navigation container, and global state holder.
- **User Goals**: Navigate between modules, monitor global system connection, trigger scans, and toggle themes.
- **Entry Points**: The root URL (`/`) or `/logs` directly.
- **Navigation**: Top navigation bar with tabs: Scanner, Home, Central Command, Paper Trading, System Logs.
- **Components Used**: `DashboardHeader`, `FilterBar`, `InfrastructureStatus`, `LiveDataBadge`.
- **Hooks Used**: `useState`, `useEffect`, `useMemo`.
- **API Calls**: `fetchUniverses`, `getLatestScan` / `loadLatestScan`, `fetchSavedScans`.
- **State Management**: `mainView` (router), `theme`, `timeframe`, `lookback`, `topN`, `selectedUniverse`, `screenerResult`, `liveTicks` (WebSocket).
- **Business Rules**: Polls the market status every 30 minutes; skips auto-polling if the market is closed.
- **Loading States**: Scanner progress (`ScannerProgress` component), streaming `progressStage` and `progressPercent` states.
- **Empty States**: Shows "Ready for the next scan" instructional banner when no `screenerResult` is present.
- **Validation Rules**: N/A.
- **Permissions**: Unrestricted.
- **Error Handling**: Displays an inline banner showing scanner request failures (e.g., FYERS_TOKEN_EXPIRED, FYERS_RATE_LIMIT) with a "Retry scan" button.
- **Polling**: 30-minute auto-poll for new cached scans.
- **WebSockets**: Connects to `/ws/ticks` for `TICK_UPDATE` messages, managing a reconnect backoff loop.
- **Dialogs**: N/A.
- **Actions**: Triggering a preset scanner, changing universes.
- **Buttons**: Navigation tabs, "Run Scanner", Theme Toggle.
- **Filters**: Signal, search, score range, sortBy, onlyHighConfidence.
- **Tables**: N/A (Delegates to child views).
- **Cards**: N/A.
- **Charts**: N/A.
- **Notifications**: N/A.
- **Theme/Styling**: Dark mode default, switches `data-theme`. Uses `.main-nav-bar`.

---

### 2.2 Home / Workstation Page
- **Screen Name**: WorkstationPage
- **Purpose**: The primary executive dashboard showing market overview, saved scans, automation status, and system health.
- **User Goals**: Get a high-level pulse on system readiness and market conditions, load saved scans, or configure risk settings.
- **Entry Points**: Clicking "Home" in the top navigation.
- **Navigation**: "Run Scanner" quick action redirects to Scanner view.
- **Components Used**: `MarketCard`, `MoverList`.
- **Hooks Used**: `useState`, `useEffect`.
- **API Calls**: `fetchMarketOverview`, `fetchSavedScans`, `fetchWorkstationAlerts`, `fetchRiskSettings`, `fetchApiHealth`, `getTokenStatus`, `getLatestScan`.
- **State Management**: Local state for `market`, `savedScans`, `alerts`, `risk`, `health`, `latestScan`, `tokenStatus`, and form states (`priceAlert`, `scanAlertName`).
- **Business Rules**: Evaluates if the current time is within the trading window (09:15 AM - 10:00 PM IST). Scanner state is determined by token validity, trading window, and scheduler status.
- **Loading States**: Shows "Loading market data..." text when `market` is null.
- **Empty States**: Displays "Market data unavailable" if indices are empty.
- **Validation Rules**: N/A.
- **Permissions**: Unrestricted.
- **Error Handling**: Sets `error` state and renders an `.error-state` panel if API fetches fail.
- **Polling**: N/A (Manual refresh button provided).
- **WebSockets**: N/A.
- **Dialogs**: N/A.
- **Actions**: Create price alert, Create scan alert, Save risk settings, Delete scan/alert, Load scan.
- **Buttons**: "Refresh Market Data", "Generate FYERS Token", "Load", "Delete".
- **Filters**: N/A.
- **Tables**: N/A.
- **Cards**: `MetricCard` (Stocks Scanned, Data Coverage, Scan Duration).
- **Charts**: N/A.
- **Notifications**: N/A.
- **Theme/Styling**: Uses CSS grid (`.dashboard-grid`, `.workstation-two-col`) and `.panel`. Background colors used dynamically to indicate scanner readiness (Green/Yellow/Red).

---

### 2.3 Scanner View (Dashboard / Candidate Table)
- **Screen Name**: Scanner Dashboard
- **Purpose**: Displays screener results, applies filters, and presents the `CandidateTable` or `AllAnalyzedStocksTable`.
- **User Goals**: Find actionable swing trading ideas, review scores and signals, and select a stock for deeper inspection.
- **Entry Points**: "Scanner" tab in navigation, or "Run Scanner" from Workstation.
- **Navigation**: Clicking a row opens `StockDetailPanel`.
- **Components Used**: `FilterBar`, `SummaryRow`, `CandidateTable`, `AllAnalyzedStocksTable`, `ScanHistoryPanel`.
- **Hooks Used**: `useMemo` for filtering/sorting logic.
- **API Calls**: `runPresetScreener` (uses EventSource streaming for progress), `saveScannerPreset`.
- **State Management**: Relies heavily on the parent `App` shell states (`screenerResult`, `filteredRows`).
- **Business Rules**: Filtering logic matches exact string states (e.g., `BUY` matches `buy` or `bullish`, `WATCH` matches `watch`, `neutral`, `sideways`). Sorts by `rank`, `confidence`, `riskReward`, or `score`.
- **Loading States**: Renders `ScannerProgress` displaying Server-Sent Events (SSE) stage messages.
- **Empty States**: Renders an `.empty-state` inside `CandidateTable` if filters return zero rows.
- **Validation Rules**: N/A.
- **Permissions**: Unrestricted.
- **Error Handling**: Displays data source warnings if the backend provides `data_warning`.
- **Polling**: N/A.
- **WebSockets**: Subscribes to tick data passed down to `CandidateTable` to calculate live distances to entry.
- **Dialogs**: N/A.
- **Actions**: Save scan, export CSV, toggle between "Shortlisted" and "All Analyzed", select a stock.
- **Buttons**: "Save Scan", "Export CSV", "Buy" (inline table).
- **Filters**: FilterBar updates parent state (Signal, Score Range, Search, High Confidence).
- **Tables**: `CandidateTable` (shows Rank, Symbol, Signal, Score Composition, Trade Plan, Equity Curve, Trend).
- **Cards**: Summary Metrics (Total scanned, Data valid, Shortlisted, BUY/WATCH/REJECTED candidates).
- **Charts**: Mini inline AreaChart from `recharts` for trailing equity curves.
- **Notifications**: N/A.
- **Theme/Styling**: Grid-based layout. Table rows use hover states, and dynamic status tags for signals (`.signal-bullish`, `.signal-bearish`).

---

### 2.4 Stock Detail Panel
- **Screen Name**: StockDetailPanel
- **Purpose**: A deep-dive view into a single stock's analysis, technicals, trade plan, and news.
- **User Goals**: Review all technical evidence, check confidence breakdowns, inspect multi-timeframe alignment, and push to paper trading.
- **Entry Points**: Clicking a row in the `CandidateTable`.
- **Navigation**: "Back to scan results" button closes the panel.
- **Components Used**: `OverviewTab`, `TechnicalsTab`, `TradePlanTab`, `NewsTab`, `BacktestTab`, `ChartTab` (implied).
- **Hooks Used**: `useState` (tab selection, risk amount), `useEffect` (fetching symbol details).
- **API Calls**: `fetchSymbolDetail`.
- **State Management**: Local state `tab` (overview, technicals, trade-plan, news, backtest, chart). `symbolDetail` holds extended API data.
- **Business Rules**: Calculates dynamic position sizing in TradePlanTab: `positionSize = Math.floor(riskAmount / riskPerShare)`. Maps ATR classifications (low, medium, high) to specific badge colors.
- **Loading States**: Disables the "Paper Trade" button and changes text to "Loading…" while fetching detail.
- **Empty States**: Displays "No stock selected" if accessed without a valid row. Renders "No detailed trade plan" if the item lacks execution data.
- **Validation Rules**: Risk amount input has `min={100}`, `step={100}`.
- **Permissions**: Unrestricted.
- **Error Handling**: Captures error strings in `detailError`, though mostly relies on fallback `?? "--"` renders if data is missing.
- **Polling**: N/A.
- **WebSockets**: N/A.
- **Dialogs**: Uses `window.alert` fallback if `onSendToPaperTrading` isn't provided.
- **Actions**: Change tabs, switch risk amount, click "Send to paper trading".
- **Buttons**: Tabs (Overview, Technicals, etc.), "Paper Trade", "Back to scan results".
- **Filters**: N/A.
- **Tables**: Small key-value pairs (e.g., Multi-timeframe).
- **Cards**: `MetricTile` components (Score, Confidence, Risk/Reward). `ReasonList` for Top reasons/Risk warnings.
- **Charts**: RangeBar component (inline custom rendering for 52-week low/high). (Full charts exist in ChartTab/BacktestTab).
- **Notifications**: N/A.
- **Theme/Styling**: Extensive use of `.metric-card`, `.status-tag`, and CSS Grid (`.detail-grid`).

---

### 2.5 Paper Trading Page
- **Screen Name**: PaperTradingPage
- **Purpose**: Simulate trade execution, monitor open positions, track orders, and view account analytics.
- **User Goals**: Place simulated buy/sell orders, view live P&L, manage risk, and review trade history.
- **Entry Points**: "Paper Trading" navigation tab, or "Send to paper trading" from the `StockDetailPanel`.
- **Navigation**: Inner tabs: "positions", "orders", "history", "analytics", "account".
- **Components Used**: `MarketEngineHealthWidget`, `TradeDetailsModal`.
- **Hooks Used**: `useState`, `useEffect`, `useMemo`, `useRef`.
- **API Calls**: `fetchPaperTradingDashboard`, `fetchPaperAccountSummary`, `fetchPaperQuote`, `placePaperOrder`, `updatePaperOrder`, `deletePaperOrder`, `prefillPaperTrade`, `resetPaperTradingAccount`, `fetchPositions`, `fetchPendingPaperOrders`, `fetchPaperTrades`, `fetchMarketEngineStatus`, `fetchPaperTradingEngineStatus`.
- **State Management**: Vast local state including `dashboard`, `listTab`, `ticket` (order form state), `accountSummary`, `engineHealth`.
- **Business Rules**: Checks for offline gap replay when dashboard loads. Order ticket validates risk logic (`riskPercent > account.max_risk_per_trade`). Calculates risk metrics on the fly (estimated cost, risk per share).
- **Loading States**: `isBusy` flag disables actions and might show loading indicators.
- **Empty States**: N/A.
- **Validation Rules**: Calculates if risk exceeds the account guideline and returns a string warning.
- **Permissions**: Unrestricted.
- **Error Handling**: Uses `setError` to show string messages if order placement or fetching fails. Stores API warnings in `statusMessage`.
- **Polling**: Extremely aggressive polling:
  - Account summary: 10 seconds.
  - Engine status: 10 seconds.
  - Engine health: 10 seconds.
  - Dashboard: 10 seconds.
  - Live Quote (HTTP): 1 second.
- **WebSockets**: N/A (Uses 1-second HTTP polling for live pricing inside this component).
- **Dialogs**: `TradeDetailsModal` shows exit reason, source, price, and time. Native browser `confirm` used for deleting orders.
- **Actions**: Place order, Update order, Cancel order, Close position, Quick buy/sell, Reset account.
- **Buttons**: "Close Position", "Cancel", "Confirm Buy Order".
- **Filters**: N/A.
- **Tables**: Orders table, Positions table, Trade History table.
- **Cards**: `MarketEngineHealthWidget` displaying DEGRADED/RUNNING status and stats.
- **Charts**: N/A.
- **Notifications**: Gap replay notifications injected into `statusMessage`.
- **Theme/Styling**: Uses standard buttons, modals with `.modal-backdrop`.

---

### 2.6 Central Command
- **Screen Name**: CentralCommand
- **Purpose**: A condensed, high-level execution and monitoring view connecting live ticks to open positions.
- **User Goals**: Monitor live system health, live P&L, open positions, and quickly act on incoming scanner signals.
- **Entry Points**: "Central Command" navigation tab.
- **Navigation**: Single page view.
- **Components Used**: None custom imported (all inline HTML elements).
- **Hooks Used**: `useTradingDashboard` (Custom hook).
- **API Calls**: `placePaperOrder`, `cancelPaperOrder`.
- **State Management**: Uses `useTradingDashboard` to abstract the polling of `MarketEngineStatus`, `PaperAccountSummary`, and `TodayCandidates`. Local state `selectedStock` tracks the active order panel.
- **Business Rules**: Disables the "Confirm Buy Order" button if the data feed (`isLiveDataActive`) is offline.
- **Loading States**: N/A.
- **Empty States**: "No open positions" in the portfolio table. "No valid stocks found" in the scanner feed list.
- **Validation Rules**: N/A.
- **Permissions**: Unrestricted.
- **Error Handling**: Uses `window.alert` on order failure.
- **Polling**: Handled completely by `useTradingDashboard` (10 seconds).
- **WebSockets**: Implicit via `useTradingDashboard` engine health logic.
- **Dialogs**: Native `alert`.
- **Actions**: Close position, Confirm Buy Order, Select a scan feed item.
- **Buttons**: "Close Position", "Confirm Buy Order".
- **Filters**: N/A.
- **Tables**: Open Positions table (Symbol, Side, Entry Price, LTP, Unrealized P&L, Action).
- **Cards**: Order Panel safeguarding widget (visually changes color based on data feed status).
- **Charts**: N/A.
- **Notifications**: Visual status feedback ("LIVE MARKET SPREAD" vs "STALE DATA — EXECUTION HALTED").
- **Theme/Styling**: Uses Tailwind CSS utility classes (e.g., `bg-slate-950`, `text-green-500`, `flex-col`, `col-span-12`). This is notable as it deviates from the vanilla CSS approach in the rest of the application.

---

### 2.7 System Logs
- **Screen Name**: SystemLogs (Observed from routing map)
- **Purpose**: Displays backend and system event logs.
- **User Goals**: Debugging backend failures, checking scheduler runs, and viewing error traces.
- **Entry Points**: "System Logs" navigation tab or `/logs` URL.
- **Navigation**: N/A.
- **Components Used**: Likely inline standard elements (not deeply inspected, known to exist via `App.tsx` router).
- **Hooks Used**: Assumed standard `useState`/`useEffect`.
- **API Calls**: Assumed log streaming endpoint.
- **Theme/Styling**: Vanilla CSS.

---

## 3. Notable Discoveries & Architectural Quirks
- **Routing**: The app manages URL paths (`window.history.replaceState`) and view rendering manually without a router library.
- **Styling Inconsistency**: Most components (`WorkstationPage`, `App`, `Dashboard`, `PaperTradingPage`) use vanilla CSS files (`styles.css`) with standard class names (e.g., `panel`, `button`, `metric-card`). However, `CentralCommand.tsx` is completely styled with **Tailwind CSS**.
- **Duplicated Shells**: `App.tsx` and `Dashboard.tsx` are largely identical root components. `App.tsx` acts as the main entry point (imported in `main.tsx`). `Dashboard.tsx` appears to be an iteration or alternative, holding identical logic but with slightly different WebSocket integrations (a live badge wrapper).
- **Extreme Polling vs WebSockets**: The application uses actual WebSockets (`/ws/ticks`) for live price ticks in the main dashboard but falls back to aggressive 1-second `setInterval` HTTP polling for live quotes inside the `PaperTradingPage`. Account and System Status are universally polled via HTTP every 10 seconds.
- **Fyers API Dependency**: The entire Scanner application flow is heavily gated by FYERS Token validity. If the token expires, the application gracefully degrades state and disables auto-scanners, prompting manual regeneration.
