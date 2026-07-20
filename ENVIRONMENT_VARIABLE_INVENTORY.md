# ENVIRONMENT VARIABLE INVENTORY

## Required Variables
*(Must be set securely per deployment stage)*
- `DATABASE_URL`: Primary PostgreSQL connection string. Must use `postgresql+asyncpg://` schema.
- `REDIS_URL`: Primary Redis connection string.
- `GROQ_API_KEY`: Required for LLM recommendations in OrchestratorAgent.
- `FYERS_APP_ID`: Required for broker authentication.
- `FYERS_SECRET_ID`: Required for broker authentication.
- `CORS_ORIGINS`: Comma-separated list of allowed UI domains.
- `VITE_API_URL`: (Frontend) Explicit mapping to the backend domain.

## Optional Variables
- `FYERS_REDIRECT_URI`: Broker OAuth callback. (Only strictly required if UI-based oauth flow is re-enabled).
- `NEWS_API_KEY`: Only required if `news_provider=marketaux`.
- `FYERS_TOKEN_CACHE_MINUTES`: TTL for token retention.
- `NIFTY500_SYMBOLS`, `NIFTY_NEXT_500_SYMBOLS`, `BSE500_SYMBOLS`: Override dynamic universe pools instead of using local CSV structures.
- `COSTS_ENABLED`: FEAT-024A execution-costs toggle (bool, default `True`). Loaded by `Settings`; **non-binding** until later FEAT-024A specs wire consumers. Does not currently affect backtests, paper trading, or FEAT-008 fill models.
- `SLIPPAGE_BPS`: FEAT-024A slippage in basis points (float, default `5.0`). Loaded by `Settings`; unused at runtime in Spec 1. Distinct from FEAT-008 / `backtest_service` `slippage_rate` profiles.
- `COMMISSION_FIXED`: FEAT-024A fixed commission per order (float, default `0.50`). Loaded by `Settings`; unused at runtime in Spec 1.
- `COMMISSION_PERCENT`: FEAT-024A percentage commission (float, default `0.001` = 0.1%). Loaded by `Settings`; unused at runtime in Spec 1. Distinct from `backtest_service` `brokerage_rate` profiles.

## Missing Variables
- `VITE_WS_URL`: A dedicated websocket endpoint configuration is missing. The frontend aggressively replaces `http` with `ws`, which causes critical failures behind API Gateways enforcing separate routing.
- `SECRET_KEY`: There is no centralized JWT/HMAC Secret Key variable detected for system endpoints, meaning sessions/auth might be using deterministic defaults or none at all.

## Unused / Duplicate Variables
- `VITE_API_BASE_URL` vs `VITE_API_URL`: Both are checked inconsistently across frontend files (`import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL`). This causes environment ambiguity.
- `mongo_url`, `mongo_db_name`: Defined in `settings.py` but entirely unused in the current architecture (switched fully to Postgres).
- `COSTS_ENABLED`, `SLIPPAGE_BPS`, `COMMISSION_FIXED`, `COMMISSION_PERCENT`: Defined and loadable via `Settings` (FEAT-024A Spec 1) but have **no runtime consumers** yet. Changing them does not alter PnL, fills, or API payloads. Do not operate as if costs are applied. Parallel cost logic remains in FEAT-008 / `backtest_service` cost profiles until a later spec reconciles models.
