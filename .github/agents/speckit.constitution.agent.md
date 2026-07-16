---
description: Create or update the project constitution from interactive or provided principle inputs, ensuring all dependent templates stay in sync.
handoffs: 
  - label: Build Specification
    agent: speckit.specify
    prompt: Implement the feature specification based on the updated constitution. I want to build...
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Pre-Execution Checks

**Check for extension hooks (before constitution update)**:
- Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.before_constitution` key
- If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Outline.
    ```
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

## Outline

You are updating the project constitution at `.specify/memory/constitution.md`. This file is a TEMPLATE containing placeholder tokens in square brackets (e.g. `[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`). Your job is to (a) collect/derive concrete values, (b) fill the template precisely, and (c) propagate any amendments across dependent artifacts.

**Note**: If `.specify/memory/constitution.md` does not exist yet, it should have been initialized from `.specify/templates/constitution-template.md` during project setup. If it's missing, copy the template first.

Follow this execution flow:

1. Load the existing constitution at `.specify/memory/constitution.md`.
   - Identify every placeholder token of the form `[ALL_CAPS_IDENTIFIER]`.
   **IMPORTANT**: The user might require less or more principles than the ones used in the template. If a number is specified, respect that - follow the general template. You will update the doc accordingly.

2. Collect/derive values for placeholders:
   - If user input (conversation) supplies a value, use it.
   - Otherwise infer from existing repo context (README, docs, prior constitution versions if embedded).
   - For governance dates: `RATIFICATION_DATE` is the original adoption date (if unknown ask or mark TODO), `LAST_AMENDED_DATE` is today if changes are made, otherwise keep previous.
   - `CONSTITUTION_VERSION` must increment according to semantic versioning rules:
     - MAJOR: Backward incompatible governance/principle removals or redefinitions.
     - MINOR: New principle/section added or materially expanded guidance.
     - PATCH: Clarifications, wording, typo fixes, non-semantic refinements.
   - If version bump type ambiguous, propose reasoning before finalizing.

3. Draft the updated constitution content:
   - Replace every placeholder with concrete text (no bracketed tokens left except intentionally retained template slots that the project has chosen not to define yet—explicitly justify any left).
   - Preserve heading hierarchy and comments can be removed once replaced unless they still add clarifying guidance.
   - Ensure each Principle section: succinct name line, paragraph (or bullet list) capturing non‑negotiable rules, explicit rationale if not obvious.
   - Ensure Governance section lists amendment procedure, versioning policy, and compliance review expectations.

4. Consistency propagation checklist (convert prior checklist into active validations):
   - Read `.specify/templates/plan-template.md` and ensure any "Constitution Check" or rules align with updated principles.
   - Read `.specify/templates/spec-template.md` for scope/requirements alignment—update if constitution adds/removes mandatory sections or constraints.
   - Read `.specify/templates/tasks-template.md` and ensure task categorization reflects new or removed principle-driven task types (e.g., observability, versioning, testing discipline).
   - Read each command file in `.specify/templates/commands/*.md` (including this one) to verify no outdated references (agent-specific names like CLAUDE only) remain when generic guidance is required.
   - Read any runtime guidance docs (e.g., `README.md`, `docs/quickstart.md`, or agent-specific guidance files if present). Update references to principles changed.

5. Produce a Sync Impact Report (prepend as an HTML comment at top of the constitution file after update):
   - Version change: old → new
   - List of modified principles (old title → new title if renamed)
   - Added sections
   - Removed sections
   - Templates requiring updates (✅ updated / ⚠ pending) with file paths
   - Follow-up TODOs if any placeholders intentionally deferred.

6. Validation before final output:
   - No remaining unexplained bracket tokens.
   - Version line matches report.
   - Dates ISO format YYYY-MM-DD.
   - Principles are declarative, testable, and free of vague language ("should" → replace with MUST/SHOULD rationale where appropriate).

7. Brownfield-First Development

Existing architecture MUST be preserved unless an approved specification explicitly authorizes architectural changes.

All implementations MUST:

Extend existing modules instead of replacing them.
Maintain backward compatibility unless a breaking change is explicitly approved.
Preserve existing APIs, contracts, and business logic.
Avoid unnecessary refactoring during feature implementation.
Use feature flags for high-risk or production-impacting changes whenever possible.

Rationale

The trading platform is an active brownfield project. Stability and incremental evolution are mandatory.

8. Architecture Integrity

Every feature MUST preserve architectural boundaries.

Implementations MUST:

Respect existing layer separation.
Prevent circular dependencies.
Keep business logic outside API controllers.
Preserve module ownership.
Maintain dependency direction.
Reuse existing shared components before creating new ones.

No implementation may redesign the system architecture unless explicitly approved in the specification.

Rationale

Maintaining architectural consistency reduces technical debt and prevents long-term degradation.

9. Production Safety

Every production feature MUST include operational safety mechanisms.

Each implementation MUST provide:

Rollback strategy
Timeout handling
Error handling
Retry strategy where appropriate
Structured logging
Failure recovery
Feature flag support for high-risk changes

Production behavior MUST fail safely rather than silently.

Rationale

Production safety is mandatory for a financial application.

10. Comprehensive Testing

Every implemented feature MUST include appropriate automated testing.

Minimum required tests:

Unit Tests
Integration Tests
Failure Path Tests
Edge Case Tests
Regression Tests (for production bugs)

Existing tests MUST continue passing before feature completion.

No feature may be considered complete without satisfying its defined acceptance criteria.

Rationale

Testing protects existing functionality while enabling safe continuous development.

11. Observability

Every production feature MUST expose sufficient operational visibility.

Implementations MUST include:

Structured logging
Error reporting
Performance metrics where appropriate
Traceable request identifiers
Business event logging when applicable

Critical failures MUST never occur silently.

Rationale

Operational visibility is essential for diagnosing production issues.

12. AI Development Governance

Specification is the single source of truth.

All AI-assisted development MUST follow this workflow:

Specification before implementation.
Implementation only within approved specification scope.
Architecture modifications require explicit approval.
Generated code requires human review.
Independent audit MUST be completed before merge.
AI-generated code MUST never bypass testing requirements.

Each AI tool has a single responsibility:

Spec Kit → Specification generation
DeepSeek → Feature implementation
OpenCode → Repository integration
Grok → Architecture and production audit
Human Developer → Final approval

Rationale

Clear responsibility boundaries improve consistency and reduce implementation drift.

13. Performance & Scalability

Every feature MUST consider production performance.

Implementations MUST:

Avoid unnecessary database queries.
Avoid O(n²) algorithms unless justified.
Use asynchronous patterns where appropriate.
Prevent blocking operations in async execution paths.
Batch large operations when practical.
Reuse caches before introducing new storage.

Performance regressions MUST be identified before merge.

Rationale

Trading systems require predictable performance under increasing workload.

14. Database Governance

Database integrity MUST be preserved.

All database changes MUST:

Use version-controlled migrations.
Preserve backward compatibility.
Include required indexes for new query paths.
Maintain transactional consistency.
Avoid destructive schema modifications without explicit approval.
Clearly define data ownership.

No direct production schema modifications are permitted outside approved migrations.

Rationale

Reliable data management is fundamental for trading systems.

15. Definition of Done

A feature SHALL be considered complete only when all of the following conditions are satisfied:

Specification approved.
Implementation completed.
Acceptance criteria satisfied.
Unit and integration tests pass.
Existing regression tests pass.
Documentation updated.
Production audit completed.
No unresolved Critical or High severity issues remain.
Required observability added.
Rollback strategy verified.

Incomplete implementations MUST NOT be merged.

Rationale

Consistent completion criteria improve software quality and release confidence.

16. Non-Negotiable Engineering Rules

The following rules apply to every implementation without exception:

No placeholder implementations.
No TODO code in production.
No disabled or skipped tests.
No duplicated business logic.
No silent exception handling.
No breaking API changes without specification approval.
No undocumented architectural changes.
No hardcoded secrets or credentials.
No speculative implementations beyond the approved specification.
No merge without successful audit and testing.

Rationale

These rules establish the minimum engineering standards for all project contributions.
7. Write the completed constitution back to `.specify/memory/constitution.md` (overwrite).

8. Output a final summary to the user with:
   - New version and bump rationale.
   - Any files flagged for manual follow-up.
   - Suggested commit message (e.g., `docs: amend constitution to vX.Y.Z (principle additions + governance update)`).

Formatting & Style Requirements:

- Use Markdown headings exactly as in the template (do not demote/promote levels).
- Wrap long rationale lines to keep readability (<100 chars ideally) but do not hard enforce with awkward breaks.
- Keep a single blank line between sections.
- Avoid trailing whitespace.

If the user supplies partial updates (e.g., only one principle revision), still perform validation and version decision steps.

If critical info missing (e.g., ratification date truly unknown), insert `TODO(<FIELD_NAME>): explanation` and include in the Sync Impact Report under deferred items.

Do not create a new template; always operate on the existing `.specify/memory/constitution.md` file.

## Post-Execution Checks

**Check for extension hooks (after constitution update)**:
Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.after_constitution` key
- If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

Project: Trading App Authentication System

Principles:
1. Security-First Auth: All auth endpoints (login, signup, refresh, PIN-verify) MUST 
   enforce rate limiting and generic error messages that never reveal account existence.
2. Zero-Trust Session Model: Every paper-trading API (holdings, balance, analytics) 
   MUST validate a live session token; no endpoint is exempt.
3. Layered Authentication: Full credential login MUST occur once; subsequent app 
   entry MUST use biometric-first with 4-digit PIN as mandatory fallback.
4. Token Hygiene: Refresh tokens MUST rotate on each use with reuse detection; 
   compromised token families MUST be revoked entirely, not per-token.
5. Device Transparency: Users MUST be able to view and revoke active sessions 
   from a device management screen.
6. Responsive UI: Auth screens MUST render correctly on both mobile and laptop 
   viewports using a single shared component set.

All production features MUST additionally include edge-case testing, failure-path testing, and regression testing where applicable. Existing test suites MUST continue passing before merge.