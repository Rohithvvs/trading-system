# UI Contracts & Route Schemas: Phase 3 Frontend Foundation

**Feature Branch**: `028-phase3-frontend-foundation`  
**Date**: 2026-07-31  

---

## 1. Routing Contract Table

| Canonical Route | Target View Component | Permitted Query Parameters | Redirect Rule |
| :--- | :--- | :--- | :--- |
| `/` | `DashboardPage` | None | N/A |
| `/research/scanner` | `ScannerView` | `signal`, `search`, `score`, `sortBy` | Redirect `/scanner` → `/research/scanner` |
| `/research/workstation` | `StockWorkstationPage` | `symbol` | N/A |
| `/research/markets` | `MarketsPage` | `universe`, `timeframe` | Redirect `/markets` → `/research/markets` |
| `/trading/paper-desk` | `PaperTradingPage` | `tab` (`positions` \| `orders` \| `watchlist`) | Redirect `/paper` → `/trading/paper-desk` |
| `/paper-order` | `PaperOrderPage` | `symbol`, `side`, `prefill` | N/A |
| `/analytics/performance` | `PerformancePage` | `timeframe` | Redirect `/performance` → `/analytics/performance` |
| `/system/diagnostics` | `DiagnosticsPage` | None | Redirect `/diagnostics` → `/system/diagnostics` |
| `/system/logs` | `SystemLogs` | `level`, `limit` | Redirect `/logs`, `/admin/logs` → `/system/logs` |

---

## 2. Event Bridge Contracts

### `paper:open-order` Custom Event
Dispatched when user clicks a "Paper Trade" CTA button anywhere in the platform.
```typescript
interface PaperOpenOrderEventDetail {
  symbol: string;
  side?: "BUY" | "SELL";
  prefill?: RecommendationPrefillRequest | null;
  orderId?: string | null;
  returnTo?: string;
  currentPrice?: number | null;
  signal?: "BUY" | "WATCH" | "REJECT" | null;
  score?: number | null;
  confidence?: number | null;
  riskReward?: number | null;
}
```
Listening target: `PaperOrderRouteBridge` in `App.tsx` navigates directly to `/paper-order`.
