# Feature Specification: Portfolio Configuration Infrastructure

**Feature Branch**: `005-portfolio-config`
**Created**: 2026-07-18
**Status**: Implemented

## 1. Feature Summary

The purpose of this specification is to introduce the foundational configuration infrastructure required for future portfolio simulation capabilities (FEAT-024B). This includes defining configuration properties for portfolio constraints, position sizing, and capital allocation without implementing any business logic, execution handling, or cash accounting at this stage.

## Clarifications

### Session 2026-07-18
- Q: Configuration Naming Convention → A: Functional-prefix `portfolio_` (e.g., `portfolio_max_concurrent_positions`) (Option A)
- Q: Configuration Boundaries & Validation → A: Enforce strict boundaries (e.g., `ge=1`, `le=100.0`) in Pydantic settings at initialization (Option A)

## 2. Previous Specification Review

- **FEAT-024A Spec 1 (004-execution-costs-config)**: Introduced base execution cost parameters (slippage_bps, commission_fixed, etc.) into the global configuration architecture (`Settings`). Portfolio simulation configuration will follow the same pattern, living alongside these settings in `backend/app/config/settings.py` to maintain a cohesive, environment-variable-driven configuration schema.
- **FEAT-008 (Realistic Trade Execution Model)**: Introduced `execution_model` switching and standalone sizing logic via `PercentEquityPositionSizer`. The new portfolio configuration properties will eventually replace or augment these single-asset parameters, allowing the `BacktestService` to manage a consolidated pool of capital across multiple simultaneous positions.

This specification seamlessly fits into the existing architecture by strictly extending the existing `Settings` class in `backend/app/config/settings.py`, and extending schemas in `backend/app/schemas/analysis.py` if request-level overrides are needed.

## 3. Existing Architecture Analysis

- **Configuration Layer**: All global configuration currently resides in `backend/app/config/settings.py` utilizing `pydantic-settings`. Values are loaded safely from the `.env` file.
- **BacktestService Layer**: Located in `backend/app/services/backtest_service.py`. Currently, it runs single-asset simulations holding a hardcoded starting equity of `100000.0`.
- **Data Models**:
  - `BacktestResult` (`backend/app/schemas/analysis.py`) models single-asset backtest outcomes.
  - `PaperAccountSummary`, `PaperPositionResponse`, etc. (`backend/app/schemas/paper_trading.py`) represent a fully realized, multi-asset portfolio for paper trading.

**Integration Point**: 
This feature will be implemented in `backend/app/config/settings.py`. By defining properties here, we prepare the system for subsequent specifications where the `BacktestService` will adopt these constraints to transition from single-asset simulations to multi-asset portfolio accounting.

**Files Involved**:
- `backend/app/config/settings.py`

## 4. Configuration Design

The following configuration properties will be introduced. They are tailored to the existing architecture without over-engineering, using Pydantic field annotations for strict boundary enforcement:

- `portfolio_simulation_enabled`: (bool, default `False`) Master toggle to enable portfolio simulation pathways.
- `portfolio_max_concurrent_positions`: (int, default `5`, strictly `>= 1`) Maximum number of swing positions that can be held simultaneously.
- `portfolio_max_position_pct`: (float, default `20.0`, strictly `> 0.0` and `<= 100.0`) Maximum percentage of total equity to allocate to a single position.
- `portfolio_minimum_trade_value`: (float, default `1000.0`, strictly `>= 0.0`) The minimum capital allocation to permit a valid trade (standard limit to avoid meaningless tiny positions).
- `portfolio_allow_fractional_shares`: (bool, default `False`) Hard-defaulted to `False` specifically to support Indian Cash Equity (NSE/BSE), where fractional trading is not permitted.
- `portfolio_reserve_cash_enabled`: (bool, default `False`) Toggle to instruct the system to maintain a cash buffer.
- `portfolio_starting_capital`: (float, default `100000.0`, strictly `>= 1000.0`) Base starting capital for the simulated portfolio.

## 5. Files To Modify

| File | Reason | Change Type |
|---|---|---|
| `backend/app/config/settings.py` | Introduce new Pydantic fields in the `Settings` class to support portfolio simulation configuration via `.env`. | Add configuration properties |

## 6. Public Impact Analysis

- **API**: No changes in this phase. (Subsequent phases may expose these as optional payload overrides).
- **Database**: No change.
- **JSON**: No change to current serialization.
- **UI**: No change.
- **Services**: No change.
- **Models**: No change.
- **Serialization**: No change.

## 7. Future Dependency Analysis

- **Specification 2 (Portfolio State Management)**: Will utilize `portfolio_starting_capital` and `portfolio_reserve_cash_enabled` to instantiate robust paper trading models (like `PaperAccountSummary`) inside the backtester.
- **Specification 3 (Position Sizing & Constraints)**: Will depend heavily on `portfolio_max_position_pct` and `portfolio_minimum_trade_value` to determine exact share amounts. It will respect `portfolio_allow_fractional_shares=False` for whole-share execution, while `portfolio_max_concurrent_positions` will govern trade queuing and rejection logic.
- **Specification 4 (Execution & Accounting)**: Will combine the execution costs defined in FEAT-024A with these new portfolio constraints to accurately deduct realistic Indian market charges (STT, Brokerage, Stamp Duty, GST, DP) from a shared capital pool.

## 8. Risks

- **Architectural Risks**: None. Centralizing configs in `settings.py` adheres strictly to the existing architectural patterns.
- **Backward Compatibility Risks**: Negligible. All new configuration fields will have sensible, safe defaults that do not intercept or mutate current `BacktestService` logic.
- **Duplicate Configuration Risks**: `BacktestService.run()` currently accepts `position_sizing_pct` directly. Care must be taken in later specifications to cleanly deprecate the old argument in favor of the new global `portfolio_max_position_pct`.
- **Future Extensibility Risks**: Global configurations enforce a single system-wide portfolio profile. This will be mitigated in future specs by allowing endpoints to override these globals.

## 9. Acceptance Criteria

- [x] New portfolio configuration fields (simulation_enabled, max_concurrent_positions, max_position_pct, minimum_trade_value, allow_fractional_shares, reserve_cash_enabled, starting_capital) are added to the `Settings` class in `settings.py`.
- [x] Strict boundaries are enforced at startup (e.g., project fails to boot if starting capital < 1000 or max position pct > 100).
- [x] `portfolio_allow_fractional_shares` defaults to `False` to align with NSE/BSE constraints.
- [x] Project starts successfully with valid environment configuration fields.
- [x] All existing tests pass successfully.
- [x] No execution, sizing, or cash accounting logic is implemented.
