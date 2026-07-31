# Validation & Execution Guide: Phase 3 Frontend Foundation

**Feature Branch**: `028-phase3-frontend-foundation`  
**Date**: 2026-07-31  

---

## 1. Environment Setup

Ensure Node.js and dependencies are installed in the `frontend` directory:

```powershell
cd frontend
npm install
```

---

## 2. Running Local Development Server

Launch the Vite development server:

```powershell
npm run dev
```

The application will be accessible at `http://localhost:5173`.

---

## 3. Automated Validation Scenarios

### Scenario A: Route Integrity & Legacy Alias Redirects
Verify that accessing legacy routes automatically redirects to canonical domain paths.

```powershell
# Run Vitest navigation test suite
npm run test -- navConfig.test.ts
```

### Scenario B: Frontend Production Build Verification
Confirm zero build errors or TypeScript failures across the frontend bundle:

```powershell
npm run build
```

Expected Output: Clean bundle generation in `frontend/dist/` with no build errors.

---

## 4. Manual UI Verification Scenarios

1. **Dashboard Entry Point (`/`)**: Open browser to `http://localhost:5173/`. Confirm that all 9 dashboard widgets render cleanly.
2. **Sidebar Collapse**: Click the `«` collapse button in the sidebar. Verify width shrinks to 64px, icons remain accessible, and state persists after refreshing the page (`F5`).
3. **Breadcrumbs Trail**: Click on "Opportunity Scanner" under Research & Discovery. Verify top header shows `Home / Research & Discovery / Opportunity Scanner`.
4. **Theme Toggle**: Toggle between Dark Mode and Light Mode. Confirm surfaces and text colors update instantly without unstyled text.
