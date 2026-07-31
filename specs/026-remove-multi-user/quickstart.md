# Phase 1 Quickstart & Validation Guide

**Feature Branch**: `026-remove-multi-user`  
**Date**: 2026-07-31  

**Production cutover**: See [PRODUCTION_CUTOVER.md](./PRODUCTION_CUTOVER.md)  
(mandatory DB backup, `TOKEN_ENCRYPTION_KEY`, `API_KEY`, trusted network).

---

## Validation Scenario 1: Fresh Browser Launch (Direct Access)

1. Open a fresh browser tab with cleared cookies and local storage.
2. Navigate to `http://localhost:5173/`.
3. **Expected Result**:
   - The Central Command dashboard loads directly without redirecting to `/login`.
   - The application header displays system health, live data badges, and theme toggles without user avatars or login/logout buttons.

---

## Validation Scenario 2: Paper Trading Order Execution

1. Navigate to `/paper-trading` or click "Paper Trade" on any recommendation card in Central Command.
2. Submit a Buy paper trade order for symbol `RELIANCE` (qty 10, limit order).
3. **Expected Result**:
   - Order executes successfully without requesting auth cookies.
   - Position appears under the Primary Paper Account in the Paper Trading tab.

---

## Validation Scenario 3: FYERS Token Exchange Flow

1. Open `/settings` or access FYERS token generation via `/fyers/auth/url`.
2. Perform FYERS broker token refresh.
3. **Expected Result**:
   - FYERS token exchange completes and updates `fyers_tokens` database table.
   - Market Scanner data feeds continue operating smoothly.

---

## Validation Scenario 4: Governance Route Verification

1. Send GET request to `http://localhost:8000/api/v1/governance/routes`.
2. **Expected Result**:
   - Returns 200 OK with JSON registered CLI governance routes (e.g. `experiment.start`, `experiment.pause`, etc.) matching `AGENTS.md`.
