# Implementation Plan: Execution Costs Configuration

**Branch**: `004-execution-costs-config` | **Date**: 2026-07-18
**Input**: Feature specification from `/specs/004-execution-costs-config/spec.md`

## 1. Specification Summary
This specification introduces the foundational configuration infrastructure required to support execution cost calculations in the trading system. It adds four specific configuration parameters (`costs_enabled`, `slippage_bps`, `commission_fixed`, `commission_percent`) without implementing any of the underlying calculation logic or business integration.

---

## 2. Previous Specification Dependency Analysis
This specification has **no dependencies on previous specifications**. It is the foundational specification (Specification 1) for the FEAT-024A (Execution Costs) feature.

---

## 3. Architecture Analysis
**Where configuration currently lives:**
The application's global configuration is centralized in `backend/app/config/settings.py` using a Pydantic `BaseSettings` class named `Settings`. Environment variables and default properties are managed through this class. Similar feature toggles (like `feat008_enabled`, `feat004_enabled`) are also housed here.

**Why this is the correct location:**
Extending the existing `Settings` class adheres to the project's established pattern for dependency injection and configuration access. It avoids creating redundant configuration singletons or `BacktestConfig` classes, strictly following the specification's mandate to "Reuse existing architecture" and "Do not create duplicate configuration classes".

**Why alternative locations should not be used:**
Creating a localized configuration model inside `backtest_service.py` or a dedicated `ExecutionCostsConfig` class would fragment the configuration loading mechanism, making it harder to manage environment variables centrally via `.env` or CI/CD pipelines.

---

## 4. Files To Modify

| File | Why Modify | Type of Change |
|------|------------|----------------|
| `backend/app/config/settings.py` | To introduce the new execution cost configuration properties to the global `Settings` object. | Extension (Add Fields) |

---

## 5. Configuration Fields To Add

1. **Name**: `costs_enabled`
   - **Datatype**: `bool`
   - **Default Value**: `True`
   - **Purpose**: A master toggle to enable or disable execution cost calculations, allowing for A/B comparisons against historical baselines.

2. **Name**: `slippage_bps`
   - **Datatype**: `float`
   - **Default Value**: `5.0`
   - **Purpose**: Defines the estimated slippage in basis points (5.0 bps = 0.05%).

3. **Name**: `commission_fixed`
   - **Datatype**: `float`
   - **Default Value**: `0.50`
   - **Purpose**: Defines the fixed commission cost per executed order.

4. **Name**: `commission_percent`
   - **Datatype**: `float`
   - **Default Value**: `0.001`
   - **Purpose**: Defines the percentage-based commission cost (0.001 = 0.1%).

---

## 6. Public Impact Analysis
- **APIs**: No changes.
- **Database**: No changes.
- **Models**: No changes to database models or response schemas.
- **Services**: No changes to existing service business logic.
- **Serialization**: No changes to JSON payloads.
- **UI**: No changes.
- **Backward Compatibility**: Fully backward compatible. Existing services will ignore the new configuration fields until explicitly programmed to use them in future specifications.

---

## 7. Future Specification Preparation
This foundational specification enables future work without implementing it by providing a strict, type-safe configuration contract. 
- **Specification 2 (Calculation Logic)** can inject this `Settings` object and build pure functions to calculate slippage and commission without worrying about how values are sourced or validated.
- **Specification 3 (Backtest Integration)** can pass these configurations seamlessly into `BacktestService` to adjust the PnL calculations.
- **Specification 4 (Reporting/API)** can read `costs_enabled` to determine whether to surface gross or net metrics in the JSON payload.

---

## 8. Risks
- **Architectural Risks**: Low. Modifying a central configuration file is standard practice.
- **Duplicate Configuration Risks**: Mitigated by directly reusing the `Settings` class rather than creating a new `BacktestConfig`.
- **Compatibility Risks**: Low. Adding optional/defaulted fields to a Pydantic settings class does not break existing consumers.
- **Maintainability Risks**: Low. The types and defaults are strictly defined and validated by Pydantic on startup.

---

## 9. Acceptance Criteria
- [x] `backend/app/config/settings.py` is updated to include `costs_enabled`, `slippage_bps`, `commission_fixed`, and `commission_percent`.
- [x] All new fields have the correct types (`bool`, `float`).
- [x] All new fields have the correct default values (`True`, `5.0`, `0.50`, `0.001`).
- [x] The system initializes successfully without errors.
- [x] No execution cost calculations or business logic are added to `backtest_service.py` or any other service.
- [x] No API endpoint payloads or schemas are altered.
- [x] Existing tests continue to pass without modification.
  - Note: Feature-scoped tests pass. Any pre-existing failures elsewhere (e.g. unrelated `DATABASE_URL` mutation expectations) are out of scope for this feature delta.
