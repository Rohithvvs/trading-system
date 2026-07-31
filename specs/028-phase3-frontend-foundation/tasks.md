# Tasks: Phase 3 Frontend Foundation & Navigation Transformation

**Input**: Design documents from `/specs/028-phase3-frontend-foundation/`  
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/ui-contracts.md, quickstart.md  
**Tests**: Automated Vitest and Playwright test validation included per spec testing strategy.  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project environment initialization and routing configuration setup

- [X] T001 Create route configuration file in `frontend/src/routes/routesConfig.tsx`
- [X] T002 Update design token CSS variables in `frontend/src/design-system/tokens.css` for high-density surfaces
- [X] T003 [P] Add density mode context provider in `frontend/src/hooks/useDensity.tsx`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core UI layout wrappers and design components that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create standardized dashboard widget wrapper in `frontend/src/components/WidgetContainer.tsx`
- [X] T005 [P] Create dynamic header breadcrumb component in `frontend/src/components/Breadcrumbs.tsx`
- [X] T006 [P] Create header global symbol search component in `frontend/src/components/GlobalSearch.tsx`
- [X] T007 [P] Create dashboard quick actions bar in `frontend/src/components/QuickActionsBar.tsx`
- [X] T008 Configure global React Error Boundary wrapper in `frontend/src/components/ErrorBoundary.tsx`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Unified Research & Market Entry Point (Priority: P1) 🎯 MVP

**Goal**: Transform `/` into the personal AI Trading Research command center featuring 9 dedicated research widgets and instant scan summaries.

**Independent Test**: Navigate to `http://localhost:5173/`. Verify all 9 widgets render their data, handle loading/error states gracefully, and display market regime indicators.

### Tests for User Story 1

- [X] T009 [P] [US1] Unit test for widget container render states in `frontend/src/components/__tests__/WidgetContainer.test.tsx`
- [X] T010 [P] [US1] Integration test for Dashboard landing page in `frontend/src/tests/DashboardLanding.test.tsx`

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement Market Overview widget in `frontend/src/components/widgets/MarketOverviewWidget.tsx`
- [X] T012 [P] [US1] Implement Today's Scan summary widget in `frontend/src/components/widgets/TodaysScanWidget.tsx`
- [X] T013 [P] [US1] Implement AI Recommendation Summary widget in `frontend/src/components/widgets/RecommendationSummaryWidget.tsx`
- [X] T014 [P] [US1] Implement Paper Portfolio Summary widget in `frontend/src/components/widgets/PortfolioSummaryWidget.tsx`
- [X] T015 [P] [US1] Implement Recent Activity timeline widget in `frontend/src/components/widgets/RecentActivityWidget.tsx`
- [X] T016 [P] [US1] Implement Market Hours & Token Status widget in `frontend/src/components/widgets/MarketStatusWidget.tsx`
- [X] T017 [P] [US1] Implement Research Idea Status widget in `frontend/src/components/widgets/ResearchStatusWidget.tsx`
- [X] T018 [P] [US1] Implement Quick Actions bar widget in `frontend/src/components/widgets/QuickActionsWidget.tsx`
- [X] T019 [P] [US1] Implement Live Scanner Progress widget in `frontend/src/components/widgets/ScannerStatusWidget.tsx`
- [X] T020 [US1] Assemble 9-widget responsive grid layout inside `frontend/src/pages/DashboardPage.tsx`
- [X] T021 [US1] Connect Dashboard view route (`/`) in `frontend/src/App.tsx`

**Checkpoint**: User Story 1 (MVP) fully functional and testable independently at `/`

---

## Phase 4: User Story 2 - Domain-Driven Sidebar & Header Navigation (Priority: P2)

**Goal**: Provide a domain-grouped sidebar (Overview, Research & Discovery, Execution & Portfolio, Quantitative Analytics, Platform Control) with active link tracking, header breadcrumbs, and density mode toggling.

**Independent Test**: Click through all domain links in the sidebar. Verify active route highlighting, sidebar collapse persistence in `localStorage`, and header breadcrumb updates.

### Tests for User Story 2

- [X] T022 [P] [US2] Unit test for navigation helper functions in `frontend/src/layout/navConfig.test.ts`
- [X] T023 [P] [US2] Component test for AppShell sidebar collapse and theme toggle in `frontend/src/layout/__tests__/AppShell.test.tsx`

### Implementation for User Story 2

- [X] T024 [P] [US2] Update 5-domain navigation structure in `frontend/src/layout/navConfig.tsx`
- [X] T025 [US2] Embed `Breadcrumbs`, `GlobalSearch`, and density selector into `frontend/src/layout/AppShell.tsx`
- [X] T026 [US2] Update AppShell layout styling and responsive mobile drawer CSS in `frontend/src/layout/shell.css`
- [X] T027 [US2] Connect active route matching and sidebar collapse state persistence in `frontend/src/layout/AppShell.tsx`

**Checkpoint**: User Stories 1 AND 2 work independently with full navigation support

---

## Phase 5: User Story 3 - Full-Page Order Execution & Watchlist Integration (Priority: P3)

**Goal**: Seamlessly transition research candidates into paper trade execution via `/paper-order` ticket, tabbed paper desk workspace at `/trading/paper-desk`, and legacy route alias redirects.

**Independent Test**: Click "Trade" on an AI candidate card. Confirm redirection to `/paper-order` with pre-filled trade parameters. Test legacy route `/paper` redirecting to `/trading/paper-desk`.

### Tests for User Story 3

- [X] T028 [P] [US3] Integration test for paper order prefill navigation bridge in `frontend/src/tests/PaperOrderNavigation.test.tsx`
- [X] T029 [P] [US3] E2E test for legacy route alias redirects in `frontend/e2e/legacyRedirects.spec.ts`

### Implementation for User Story 3

- [X] T030 [P] [US3] Standardize full-page trade ticket prefill handler in `frontend/src/pages/PaperOrderPage.tsx`
- [X] T031 [P] [US3] Consolidate Watchlist tab inside Paper Trading Desk workspace in `frontend/src/components/PaperTradingPage.tsx`
- [X] T032 [US3] Configure client-side route redirects (`/home` → `/`, `/scanner` → `/research/scanner`, `/paper` → `/trading/paper-desk`, `/watchlist` → `/trading/paper-desk?tab=watchlist`, `/logs` → `/system/logs`) in `frontend/src/App.tsx`
- [X] T033 [US3] Connect event listener bridge `PaperOrderRouteBridge` in `frontend/src/App.tsx`

**Checkpoint**: All user stories functional, deep-linked, and testable independently

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Dead-code elimination, unreferenced asset removal, and production build verification

- [X] T034 Delete unreferenced legacy asset graphic `frontend/src/components/BullIllustration.tsx`
- [X] T035 Clean up obsolete CSS selectors and inline styles in `frontend/src/styles.css`
- [X] T036 Refactor `StatusCards.tsx` to use design-system `StatCard` tokens in `frontend/src/components/StatusCards.tsx`
- [X] T037 [P] Execute Vitest test suite (`npm run test`) and verify 100% test pass rate in `frontend/`
- [X] T038 Execute production bundle build (`npm run build`) and confirm zero build errors in `frontend/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - starts immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phases 3–5)**: Depend on Foundational phase completion. Can proceed sequentially in priority order (P1 → P2 → P3) or in parallel.
- **Polish (Phase 6)**: Depends on completion of all user story phases.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational (Phase 2). No dependencies on US2/US3.
- **User Story 2 (P2)**: Starts after Foundational (Phase 2). Integrates with AppShell navigation.
- **User Story 3 (P3)**: Starts after Foundational (Phase 2). Connects candidate cards to `/paper-order`.

---

## Parallel Execution Opportunities

- Setup tasks `T002`, `T003` can run in parallel.
- Foundational tasks `T005`, `T006`, `T007` can run in parallel.
- US1 Widget tasks `T011` through `T019` can be implemented in parallel across separate files.
- Tests `T009`, `T010`, `T022`, `T023`, `T028`, `T029` can run in parallel with component tasks.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1).
3. **STOP and VALIDATE**: Verify Dashboard at `/` independently.

### Incremental Delivery
1. Deliver MVP (Dashboard at `/`).
2. Add User Story 2 (Domain Navigation & AppShell polish).
3. Add User Story 3 (Paper Order execution & legacy redirects).
4. Perform Phase 6 Polish & final production build validation.
