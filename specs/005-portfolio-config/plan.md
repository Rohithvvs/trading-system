# Implementation Plan: Portfolio Configuration Infrastructure

**Branch**: `005-portfolio-config` | **Date**: 2026-07-18
**Input**: Feature specification from `/specs/005-portfolio-config/spec.md`

# 1. Specification Summary

The purpose of Specification 1 (Portfolio Configuration Infrastructure) is to introduce the configuration contract required to lay the foundation for future portfolio simulation capabilities (FEAT-024B) under Sprint 2. This configures the settings schema to accept constraints (such as concurrent positions and position sizing) without implementing any of the underlying portfolio logic or math. It is required to establish type-safety and environment-level consistency early in the Spec-Driven Development cycle.

---

# 2. Previous Specification Analysis

- **FEAT-024A (Execution Costs)**: Introduced execution cost configuration properties (`costs_enabled`, `slippage_bps`, `commission_fixed`, `commission_percent`) into the global `Settings` object in `backend/app/config/settings.py` loading from the `.env` file. 
- **What should be reused**: The Pydantic-based configuration mapping style and the deployment of setting variables using standard uppercase environments.
- **What should NOT be modified**: Unrelated configurations for FEAT-004, FEAT-007, FEAT-008, and the newly added FEAT-024A properties.
- **Dependencies for FEAT-024B**: No code dependencies are blocked, but the configuration mappings must be merged directly into the unified `Settings` model.

---

# 3. Current Architecture Analysis

- **Current Portfolio Flow**: No portfolio flow exists in the backtesting service. The trading platform implements a real-time/paper multi-asset portfolio (`PaperAccountSummary` in `backend/app/schemas/paper_trading.py`), but the offline backtest module acts strictly on a single-asset level.
- **Current Backtest Flow**: The `BacktestService.run` method simulates one symbol at a time using a standalone `PercentEquityPositionSizer` with a hardcoded equity starting point of `100000.0` and no multi-position capability.
- **Current Configuration Flow**: Centralized environment variable loading via `Settings` class (`backend/app/config/settings.py`) using Pydantic Settings.
- **Current Portfolio Limitations**: Backtesting runs are siloed per symbol. There is no concept of a consolidated portfolio or shared capital constraints.
- **Integration Point**: The new portfolio configuration will be integrated directly into the `Settings` class in `backend/app/config/settings.py`. This ensures it is loaded on startup, validated instantly, and made available downstream for dependency injection into services.

---

# 4. Files To Modify

| File | Why | Change Type |
|---|---|---|
| `backend/app/config/settings.py` | Add the new portfolio simulation configuration fields to the `Settings` class with Pydantic validations. | Extension (Add Fields & Validation) |

---

# 5. Configuration Design

The following configuration properties will be defined in `backend/app/config/settings.py`:

- **`portfolio_simulation_enabled`**: `bool` (default `False`) — Toggle to activate portfolio simulation downstream.
- **`portfolio_max_concurrent_positions`**: `int` (default `5`, validated `ge=1`) — Limits simultaneous open swing positions.
- **`portfolio_max_position_pct`**: `float` (default `20.0`, validated `gt=0.0`, `le=100.0`) — Allocation limit per trade.
- **`portfolio_minimum_trade_value`**: `float` (default `1000.0`, validated `ge=0.0`) — Minimum size of a trade.
- **`portfolio_allow_fractional_shares`**: `bool` (default `False`, strictly validated to be `False`) — Prevents fractional shares (essential for Indian Cash Equity/NSE/BSE).
- **`portfolio_reserve_cash_enabled`**: `bool` (default `False`) — Allows locking a portion of equity.
- **`portfolio_starting_capital`**: `float` (default `100000.0`, validated `ge=1000.0`) — Initial capital allocation.

---

# 6. Impact Analysis

- **Services**: None. `BacktestService` will load these properties but will not utilize them in this phase.
- **Models**: None. No change to DB or schemas.
- **APIs**: None. No changes to request/response payloads in this phase.
- **Database**: None.
- **Serialization**: None.
- **UI**: None.
- **Configuration**: Exposes new variables in `.env` and `Settings` class.
- **Dependency Injection**: Reuses the existing `Settings` instance injection; no new injection models needed.
- **Existing BacktestService**: Completely unaffected; runs exactly as before.

---

# 7. Future Specification Readiness

- **Specification 2 (Portfolio State Management)**: Enablers like `portfolio_starting_capital` and `portfolio_reserve_cash_enabled` will let the system initialize portfolio accounting states directly in memory.
- **Specification 3 (Position Sizing Engine)**: The properties `portfolio_max_position_pct`, `portfolio_minimum_trade_value`, and `portfolio_allow_fractional_shares=False` establish the data requirements for whole-share sizing calculators.
- **Specification 4 (Trade Lifecycle Integration)**: Prepares the backend to connect simulated order fills to portfolio cash adjustments.
- **Specification 5 (Concurrent Position Management)**: The parameter `portfolio_max_concurrent_positions` will serve as the validation gate to reject or queue trades when limits are reached.

---

# 8. Risks

- **Architectural Risks**: Negligible, as we are not modifying behavior.
- **Brownfield Risks**: Ensure no Pydantic settings parsing breaks during deployment. (Mitigated by testing default boot).
- **Integration Risks**: Low, purely declarative change.
- **Duplicate Configuration Risks**: `BacktestService.run` takes an parameter `position_sizing_pct`. We do not deprecate this parameter yet to avoid breaking current single-asset tests. It will be refactored to align with `portfolio_max_position_pct` in a later spec.
- **Backward Compatibility Risks**: None. Default values prevent any regression.

---

# 9. Acceptance Criteria

- [x] `backend/app/config/settings.py` includes all 7 portfolio simulation variables.
- [x] Fields are verified to have strict Pydantic range constraints (e.g. `starting_capital >= 1000.0`).
- [x] `portfolio_allow_fractional_shares` is strictly validated to reject `True` values on startup.
- [x] Application starts successfully with correct configuration overrides.
- [x] Existing `pytest` suite passes without error.
