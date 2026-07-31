# Phase 0 Technical Research: Phase 3 Frontend Foundation

**Feature Branch**: `028-phase3-frontend-foundation`  
**Date**: 2026-07-31  

---

## 1. Research Overview

This research document evaluates architectural choices, state management patterns, routing mechanisms, and design token integration for the Phase 3 Frontend Foundation modernization.

---

## 2. Technical Decisions & Rationale

### Decision 1: Client-Side Routing Architecture
- **Choice**: React Router DOM (v6.22+) with centralized route table and top-level `<Navigate replace />` alias guards.
- **Rationale**: Provides declarative, zero-latency client-side navigation. Replacing legacy paths (`/scanner` → `/research/scanner`) via `<Navigate />` preserves backward compatibility for existing bookmarks without incurring network redirects.
- **Alternatives Considered**:
  - *Server-side HTTP redirects*: Rejected because SPA navigation shouldn't require round-trips to FastAPI.
  - *Hard-coded inline state views*: Rejected because it breaks browser history and deep-linking capabilities.

### Decision 2: State Persistence & UI Preferences
- **Choice**: Browser `localStorage` sync via explicit hooks (`useTheme`, `useDensity`, `readSidebarCollapsed`).
- **Rationale**: Lightweight, synchronous on mount, no external state dependencies, and resilient across page reloads.
- **Alternatives Considered**:
  - *Redux/Zustand*: Rejected as unnecessary overhead for simple UI layout preferences.

### Decision 3: Styling & Component Tokens
- **Choice**: Vanilla CSS Custom Properties (`tokens.css`, `components.css`, `shell.css`).
- **Rationale**: Zero build runtime cost, direct dark/light mode toggling via standard CSS variables (`[data-theme-active="dark"]`), and full alignment with existing brownfield styles.
- **Alternatives Considered**:
  - *TailwindCSS*: Rejected to respect user rules against introducing external styling frameworks unless explicitly requested.

### Decision 4: Code Splitting & Performance Optimization
- **Choice**: React `lazy()` and `<Suspense>` for heavy page views (`PaperTradingPage`, `StockWorkstationPage`, `MarketsPage`, `PerformancePage`, `SystemLogs`).
- **Rationale**: Ensures the primary AppShell layout and Dashboard paint rapidly (<1.5s), loading heavy sub-views on demand.

---

## 3. Summary of Resolved Technical Unknowns

- **Routing Compatibility**: Legacy routes cleanly mapped to new 5-domain structure.
- **Widget Resilience**: Isolated container loading states prevent single API failures from crashing the Dashboard.
- **Backend Safety**: Confirmed 100% read-only frontend scope; no backend endpoints or DB schemas affected.
