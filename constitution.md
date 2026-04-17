# Constitution — Trading System

Generated from the repository codebase on 2026-04-13.

**System purpose**
- Provide an advisory-only stock analysis and recommendation engine for manual traders. The system scores, ranks and produces human-readable trade plans and reasoning; it does not perform automated/live order execution. (See [README.md](README.md) and server wiring in [backend/app/main.py](backend/app/main.py)).

**Core principles**
- **Advisory-only:** outputs are recommendations for a human operator.
- **Human-in-loop:** UI and paper trading are explicit manual steps; no auto-execution.
- **Explainability:** deterministic technical and backtest signals are combined with generated LLM reasoning to produce traceable, reviewable outputs.
- **Modularity:** agents, services, models and routes have distinct responsibilities.
- **Fail-safe by default:** external provider fallbacks and mock data keep the system responsive when credentials or providers are missing.
- **Auditable:** analysis and backtest history are persisted for post-hoc review.

**AI governance rules (enforced by code)**
- LLMs produce advisory reasoning only; outputs are validated and used as explanatory text. The LLM usage pattern and required response format are implemented in [backend/app/services/llm_service.py](backend/app/services/llm_service.py).
- Required LLM response schema: JSON object containing `bullets`, `risk_factors`, `invalidation_signals`, `summary`. If missing, the system falls back to deterministic reasoning.
- LLM call policy in code: low randomness (temperature 0.2), bounded timeout (20s), and a deterministic fallback path when the provider fails.
- LLM responses must never be used to trigger automatic execution or external actuation without explicit human confirmation and separate approval flows.

**Security & access control**
- Current codebase configures CORS origins via [backend/app/config/settings.py](backend/app/config/settings.py) and reads secrets from environment variables (.env). There is no authentication or authorization layer implemented.
- Required before production: TLS, authentication (JWT/OIDC), per-endpoint RBAC, secret management (KeyVault/secret store), rate limiting and input sanitization for all endpoints.

**Performance constraints**
- Heavy compute (pandas, TA, backtests) runs synchronously in request threads (see [backend/app/services/technical_analysis_service.py](backend/app/services/technical_analysis_service.py) and [backend/app/services/backtest_service.py](backend/app/services/backtest_service.py)).
- External HTTP calls (FYERS, LLM, news) are synchronous and may block; LLM requests use a 20s timeout in the current implementation.

**Failure handling strategy**
- External service failures degrade to mock providers (FYERS -> generate_mock_ohlcv, news -> generate_mock_articles), and LLM failures fall back to deterministic reasoning.
- Exceptions are logged and surfaced as HTTP errors when appropriate; request middleware logs start/end and failures (see [backend/app/main.py](backend/app/main.py)).

**Minimum operational controls before production**
- Add authentication and RBAC, circuit breakers and retry/backoff for external services, background processing for long-running analysis jobs, structured metrics and alerting.

**Assumptions & clarifications**
- The repository uses SQLite and mock fallbacks by default; there is no Azure Blob or Azure SQL usage present in the code. If Azure integration is required, it must be added explicitly as an infrastructure migration.
