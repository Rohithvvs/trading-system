# Validation Guide: Execution Costs Configuration

## Prerequisites
- The backend application is available for testing (Python 3.11+, Pydantic installed).

## Operational status (Spec 1)

These settings are a **configuration contract only**. They load into `Settings` with the defaults below, but **no runtime path applies them** to fills, backtests, paper trading, or API payloads in this phase.

- `costs_enabled=True` does **not** mean costs are charged.
- Do not confuse with FEAT-008 / `backtest_service` cost profiles (`slippage_rate`, `brokerage_rate`), which are a separate model.
- Env vars: `COSTS_ENABLED`, `SLIPPAGE_BPS`, `COMMISSION_FIXED`, `COMMISSION_PERCENT` (see `ENVIRONMENT_VARIABLE_INVENTORY.md`).

## Validation Scenarios

### Scenario 1: Default Configuration
1. Initialize the `Settings` instance in Python without providing any environment variables for the new fields.
   ```python
   from app.config.settings import settings
   assert settings.costs_enabled is True
   assert settings.slippage_bps == 5.0
   assert settings.commission_fixed == 0.50
   assert settings.commission_percent == 0.001
   ```
2. Assert that the defaults match the specification.

### Scenario 2: Environment Variable Override
1. Run the python interpreter or pytest with environment variable overrides:
   `COSTS_ENABLED=False SLIPPAGE_BPS=10.0 python -c "from app.config.settings import settings; print(settings.costs_enabled, settings.slippage_bps)"`
2. Assert that the configuration reflects the overridden values.

### Scenario 3: Backward Compatibility
1. Run the existing test suite:
   ```bash
   cd backend
   pytest
   ```
2. Ensure no tests fail due to the addition of these new configuration fields.
