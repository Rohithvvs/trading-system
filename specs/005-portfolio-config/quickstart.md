# Validation Guide: Portfolio Configuration Infrastructure

## Prerequisites
- The backend application is available for testing (Python 3.11+, Pydantic Settings installed).

## Operational status (Spec 1)

These settings represent a **configuration contract only**. They load into `Settings` with the defaults below, but **no runtime path applies them** to position sizing, capital calculation, concurrent position logic, or API response payloads in this phase.

- `portfolio_simulation_enabled=True` does **not** perform portfolio simulation yet.
- Do not confuse with FEAT-008 / `backtest_service` single-position sizing parameters, which remain unchanged.
- Env vars: `PORTFOLIO_SIMULATION_ENABLED`, `PORTFOLIO_MAX_CONCURRENT_POSITIONS`, `PORTFOLIO_MAX_POSITION_PCT`, `PORTFOLIO_MINIMUM_TRADE_VALUE`, `PORTFOLIO_ALLOW_FRACTIONAL_SHARES`, `PORTFOLIO_RESERVE_CASH_ENABLED`, `PORTFOLIO_STARTING_CAPITAL` (these should be documented in `ENVIRONMENT_VARIABLE_INVENTORY.md`).

## Validation Scenarios

### Scenario 1: Default Configuration
1. Initialize the `Settings` instance in Python without providing any environment variables for the new fields.
   ```python
   from app.config.settings import settings
   assert settings.portfolio_simulation_enabled is False
   assert settings.portfolio_max_concurrent_positions == 5
   assert settings.portfolio_max_position_pct == 20.0
   assert settings.portfolio_minimum_trade_value == 1000.0
   assert settings.portfolio_allow_fractional_shares is False
   assert settings.portfolio_reserve_cash_enabled is False
   assert settings.portfolio_starting_capital == 100000.0
   ```
2. Assert that the defaults match the specification.

### Scenario 2: Environment Variable Override & Boundaries
1. Run the python interpreter or pytest with valid environment variable overrides:
   `PORTFOLIO_SIMULATION_ENABLED=True PORTFOLIO_MAX_CONCURRENT_POSITIONS=10 python -c "from app.config.settings import settings; print(settings.portfolio_simulation_enabled, settings.portfolio_max_concurrent_positions)"`
2. Assert that the configuration reflects the overridden values.
3. Test boundaries by attempting to boot the app with invalid values (e.g., `PORTFOLIO_MAX_POSITION_PCT=150.0` or `PORTFOLIO_ALLOW_FRACTIONAL_SHARES=True`). Pydantic should raise a `ValidationError` on startup.

### Scenario 3: Backward Compatibility
1. Run the existing test suite:
   ```bash
   cd backend
   pytest
   ```
2. Ensure no tests fail due to the addition of these new configuration fields.
