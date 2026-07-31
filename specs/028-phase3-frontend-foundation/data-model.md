# UI Data Model & Component Entities: Phase 3 Frontend Foundation

**Feature Branch**: `028-phase3-frontend-foundation`  
**Date**: 2026-07-31  

---

## 1. Core UI Entities

### Navigation Entities

#### NavigationDomain
Represents a top-level category grouping in the sidebar.
```typescript
interface NavDomain {
  id: string;          // e.g. "overview", "research", "execution", "analytics", "system"
  label: string;       // Human-readable title (e.g., "Research & Discovery")
  items: NavItem[];    // Child navigation items
}
```

#### NavigationItem
Represents an actionable leaf navigation link.
```typescript
interface NavItem {
  id: string;          // Unique item ID (e.g., "scanner")
  label: string;       // Display text (e.g., "Opportunity Scanner")
  path: string;        // Canonical path (e.g., "/research/scanner")
  match?: string;      // Path prefix matching rule for active state
  icon: ReactNode;     // SVG Icon representation
  testId: string;      // E2E test selector attribute
  badge?: string;      // Optional live status badge (e.g., "Live", "3")
}
```

---

### Dashboard Entities

#### DashboardWidgetConfig
Configuration schema defining a widget's position and state on `/`.
```typescript
interface DashboardWidgetConfig {
  id: string;                                    // Unique widget key (e.g., "market-overview")
  title: string;                                 // Header title
  gridSpan: 3 | 4 | 6 | 12;                      // Grid layout column span (out of 12)
  status: "idle" | "loading" | "ready" | "error"; // Current widget lifecycle state
  errorMessage?: string | null;                 // Error details if status === "error"
}
```

#### BreadcrumbSegment
Data structure representing a dynamic link in the top header breadcrumb bar.
```typescript
interface BreadcrumbSegment {
  label: string;       // Display label (e.g., "Stock Workstation")
  path: string;        // Target URL path (e.g., "/research/workstation")
  isLast: boolean;     // Whether this is the active leaf node
}
```

---

## 2. Layout State Models

### AppShellState
Represents client-side persistent layout preferences.
```typescript
interface AppShellState {
  sidebarCollapsed: boolean;  // Persisted in localStorage ("ui_sidebar_collapsed")
  theme: "dark" | "light";    // Persisted in localStorage ("theme")
  density: "compact" | "comfortable"; // Persisted in localStorage ("density")
  mobileMenuOpen: boolean;    // Transient state for responsive mobile menu drawer
}
```
