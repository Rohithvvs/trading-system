# Phase 0: Research

**Decision**: We will extend the existing `Settings` class in `backend/app/config/settings.py` (which acts as the equivalent configuration object) to add the execution costs parameters.

**Rationale**: The feature spec requires extending the existing configuration architecture without creating duplicates. Since `Settings` serves as the global configuration for the backend, adding the parameters there with `Field(default=...)` maintains backward compatibility and matches the project's existing configuration patterns (e.g., `feat008_enabled`, etc.).

**Alternatives considered**: Creating a new `ExecutionCostsConfig` class, which was rejected as it violates the specification ("Do not create duplicate configuration classes").
