# Phase 0: Research

**Decision**: We will extend the existing `Settings` class in `backend/app/config/settings.py` (which acts as the centralized configuration object) to add the portfolio simulation configuration parameters.

**Rationale**: The feature specification requires extending the existing configuration architecture without creating duplicates. Since `Settings` serves as the global configuration for the backend using Pydantic Settings, adding the parameters there with `Field(default=...)` and numeric validation limits preserves backward compatibility, minimizes architectural bloat, and aligns with the pattern established in FEAT-024A (Execution Costs) and other features (e.g., `feat008_enabled`, `feat004_enabled`, etc.).

**Alternatives considered**:
1. Creating a separate `PortfolioConfig` class or schema. This was rejected because it splits configuration management and introduces duplicate config classes, which violates the architectural guidelines to reuse existing components.
2. Direct integration of configuration parameters inside `BacktestService` execution loop. This was rejected because configuration should be decoupled from logic layers and loaded statically via environment files.
