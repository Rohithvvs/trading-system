# Research and Outlining: Shadow Infrastructure Foundation

**Feature Branch**: `006-shadow-infra-foundation` | **Date**: 2026-07-20  
**Feature**: [spec.md](./spec.md)

---

## 1. Architectural Decisions

### Decision 1: Execution Isolation and Crash Safety
We decided to encapsulate the shadow execution pathway inside a try-except block at the very end of `OrchestratorAgent._analyze_symbol_post_bulk`.

- **Rationale**: If the experimental logic, settings, or interfaces fail or crash, the failure must not propagate. By wrapping the shadow trigger and catching all exceptions, the core production pipeline is fully isolated and continues to run.
- **Alternatives Considered**: 
  - *Triggering Shadow Execution via a background task runner (like APScheduler or Celery)*: Rejected for Spec 1 as it introduces unnecessary infrastructure overhead for simple swing trading scans. Post-bulk inline execution with try-except is simpler and sufficient.

### Decision 2: Context Data Isolation
We decided to deep copy mutable lists (like candles and technical indicator lists) when building the `ShadowExecutionContext`.

- **Rationale**: Python lists are passed by reference. If the experimental shadow ruleset mutates the candle list, it would corrupt the production indicators. Deep copying guarantees read-only isolation.
- **Alternatives Considered**: 
  - *Fenced read-only properties*: High overhead to write custom classes. Deep copying list/dictionary parameters is lightweight and standard.

### Decision 3: Decoupled Storage Flow
We decided to define the `IShadowStore` interface to write comparison logs using its own database session context.

- **Rationale**: Reusing the main analysis transaction session could cause locks or transaction rollbacks if a shadow database write fails. Decoupling ensures that failures to persist shadow logs do not affect production writes.
- **Alternatives Considered**:
  - *Write shadow logs to the main `AnalysisHistory` table*: Rejected, as it would violate the core requirement of never modifying production outputs or tables.

---

## 2. Technical Context & Key Inquiries

- **Do we need another LLM call?**  
  *Finding*: No. The shadow ruleset will consume the pre-computed LLM findings from the production context, eliminating excess API and token costs.
- **How will the drift tracker analyze shadow recommendations?**  
  *Finding*: By matching shadow comparisons (via `ShadowComparisonLog`) against actual returns in the future.
