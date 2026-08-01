# Data Model: Portfolio Configuration Infrastructure

## Entities

### `Settings` (`backend/app/config/settings.py`)

Extended to include the following portfolio simulation parameters with strict Pydantic constraints:

- `portfolio_simulation_enabled: bool` (default: `False`)
- `portfolio_max_concurrent_positions: int` (default: `5`, constraint: `>= 1`)
- `portfolio_max_position_pct: float` (default: `20.0`, constraint: `> 0.0` and `<= 100.0`)
- `portfolio_minimum_trade_value: float` (default: `1000.0`, constraint: `>= 0.0`)
- `portfolio_allow_fractional_shares: bool` (default: `False`, constraint: must be `False`)
- `portfolio_reserve_cash_enabled: bool` (default: `False`)
- `portfolio_starting_capital: float` (default: `100000.0`, constraint: `>= 1000.0`)

**Validation Rules**: 
Pydantic numeric validation (e.g., `Field(ge=1)`, `Field(gt=0.0, le=100.0)`, `Field(ge=1000.0)`) will be used to enforce boundaries.
A `@field_validator` will be used for `portfolio_allow_fractional_shares` to enforce it is strictly `False` to maintain Indian Stock Market (NSE/BSE) whole-share delivery mechanics.
