# Phase 2 End-to-End Quickstart & Validation Guide

**Feature Branch**: `027-phase2-transformation` | **Date**: 2026-07-31  
**Spec**: [spec.md](file:///E:/Trading_lab/trading-system/specs/027-phase2-transformation/spec.md)

---

## 1. Environment Setup

### Prerequisites
- Python 3.11+ with active virtual environment (`venv`)
- Node.js 18+ and npm
- Running PostgreSQL database instance

### Database Migration Verification
Validate that database migrations execute cleanly under the single-owner model:

```bash
# From repository root
alembic upgrade head
python check_tables.py
```

Expected Output: `users`, `user_sessions`, and `user_profiles` tables are absent. `paper_trading_accounts` and `broker_tokens` exist without FK errors.

---

## 2. Launching Backend & Frontend

### Start Backend Service
```powershell
# From repository root
.\start_backend.ps1
```
*Backend runs on `http://localhost:8000`.*

### Start Frontend Application
```powershell
cd frontend
npm run dev
```
*Frontend runs on `http://localhost:5173`.*

---

## 3. End-to-End Validation Scenarios

### Scenario 1 — Instant Dashboard Load & Navigation Domain Verification
1. Open browser to `http://localhost:5173/`.
2. **Verification**:
   - Page loads directly to the Central Command Dashboard (`/`).
   - Zero login redirects or authentication popups appear.
   - Header shows single-operator status, theme toggle, and system health badge.
   - Sidebar reflects new domain navigation: `Overview`, `Research`, `Execution`, `Analytics`, `System`.

### Scenario 2 — Market Scan & AI Recommendation Inspection
1. Navigate to `/research/scanner` or click "Run Scanner" on `/`.
2. Inspect top recommendation card.
3. Click "Inspect Details".
4. **Verification**: App routes to `/research/workstation?symbol=TCS` showing technical indicators (EMA50, EMA200, MACD, Supertrend) and AI agent rationale.

### Scenario 3 — One-Click Paper Trade Execution via Order Drawer
1. On any recommendation card or scanner candidate row, click "Trade".
2. **Verification**:
   - Slide-out `OrderDrawer` opens on the right side of the screen.
   - Symbol, signal (BUY/SELL), entry price, and default stop-loss are pre-calculated.
3. Click "Submit Paper Order".
4. **Verification**:
   - Order submits successfully to `POST /api/v1/paper-trading/orders` without auth headers.
   - Real-time toast notification confirms fill.
   - Navigating to `/trading/paper-desk` shows the open position under default owner context (`00000000-0000-0000-0000-000000000001`).

### Scenario 4 — Automated Test Suite Execution
Run backend pytest suite to verify zero engine regression:

```bash
pytest backend/app/tests/ -v
```

Expected Result: 100% of Scanner, Recommendation, and Paper Execution unit tests pass cleanly.
