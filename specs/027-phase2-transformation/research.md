# Phase 0 Research & Technical Architecture Decisions

**Feature Branch**: `027-phase2-transformation` | **Date**: 2026-07-31  
**Spec**: [spec.md](file:///E:/Trading_lab/trading-system/specs/027-phase2-transformation/spec.md)

---

## 1. Single Application Owner Context Architecture

### Decision
Implement a zero-friction, static application owner context provider in `backend/app/core/deps.py`:

```python
SYSTEM_OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")

def get_application_owner_id() -> UUID:
    """Returns static single-operator owner UUID for all internal operations."""
    return SYSTEM_OWNER_ID
```

### Rationale
- Eliminates JWT token decoding, session DB lookups, and cookie extraction overhead on every API call.
- Provides a clean interface for paper trading accounts and broker credentials without dropping table owner identifiers.
- Guarantees backward compatibility with existing database rows updated during Phase 1 migration.

### Alternatives Considered
- *Dropping `user_id` columns entirely*: Rejected because `user_id` columns on `paper_trading_accounts` and `broker_tokens` provide clear ownership provenance and prevent massive schema refactoring across existing services.

---

## 2. Navigation & Layout Refactoring Strategy

### Decision
Replace `RETAIL_NAV` vs `ADMIN_NAV` split in `frontend/src/layout/navConfig.tsx` with a single unified domain hierarchy:

```typescript
export const PLATFORM_NAV: NavItem[] = [
  { id: "dashboard", label: "Overview", path: "/", icon: DashboardIcon },
  { id: "scanner", label: "Opportunity Scanner", path: "/research/scanner", icon: ScannerIcon },
  { id: "workstation", label: "Stock Workstation", path: "/research/workstation", icon: WorkstationIcon },
  { id: "markets", label: "Market & Sectors", path: "/research/markets", icon: MarketIcon },
  { id: "paper-desk", label: "Paper Desk", path: "/trading/paper-desk", icon: PaperDeskIcon },
  { id: "watchlist", label: "Watchlist", path: "/trading/watchlist", icon: WatchlistIcon },
  { id: "performance", label: "Quant Analytics", path: "/analytics/performance", icon: AnalyticsIcon },
  { id: "diagnostics", label: "System Diagnostics", path: "/system/diagnostics", icon: DiagnosticsIcon },
  { id: "logs", label: "System Logs", path: "/system/logs", icon: LogsIcon },
];
```

### Rationale
- Organizes the platform by operator intention (`Research`, `Execution`, `Analytics`, `System`) rather than arbitrary admin/user permission boundaries.
- Provides consistent location matching and active tab highlighting in `AppShell.tsx`.

---

## 3. Integrated Slide-Out Execution Drawer (`OrderDrawer.tsx`)

### Decision
Unify paper trade order submission into a global slide-out drawer component (`OrderDrawer.tsx`) accessible from:
1. Recommendation cards on the root Dashboard (`/`).
2. Candidate stock rows in the Opportunity Scanner (`/research/scanner`).
3. Detail view in the Stock Workstation (`/research/workstation`).

### Rationale
- Prevents breaking context when evaluating AI signals. The operator can view technical charts and submit a pre-calculated paper order in a single overlay view without leaving the active research screen.
- Eliminates the standalone full-screen `PaperOrderPage.tsx`, simplifying frontend routing.

---

## 4. Technical Debt Cleanup Strategy

### Decision
Execute a targeted cleanup roadmap:
1. **Frontend Removal**: Delete `PaperOrderPage.tsx`, `AuthInput.tsx`, `PasswordInput.tsx`, `AuthLayout.tsx`, `UserProfilePage.tsx`.
2. **Backend Removal**: Delete lingering Pydantic schemas in `backend/app/schemas/auth.py` and `user_profile.py`.
3. **Database Migration Verification**: Verify Alembic migration drops constraints `fk_broker_tokens_user_id` and `fk_paper_trading_accounts_user_id` while maintaining static default value `'00000000-0000-0000-0000-000000000001'`.

---

## Summary of Architectural Approvals

- **Engine Safety**: Recommendation Engine, Scanner vectorization, AI Agents, Technical Indicators, and Paper matching are 100% verified untouched.
- **Single-Owner Pattern**: Approved static owner context injection.
- **Navigation Domain**: Approved 5-domain navigation structure.
- **Drawer Workflow**: Approved slide-out `OrderDrawer` integration.
