# Data Model: Execution Costs Configuration

## Entities

### `Settings` (`backend/app/config/settings.py`)

Extended to include the following execution costs parameters:

- `costs_enabled: bool` (default: `True`)
- `slippage_bps: float` (default: `5.0`)
- `commission_fixed: float` (default: `0.50`)
- `commission_percent: float` (default: `0.001`)

**Validation Rules**: No new validation logic required. Rely on Pydantic's built-in type coercion and validation as per specification constraints.
