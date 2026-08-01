# Feature Specification: Validation & Minimal Promotion

**Feature Branch**: `012-validation-minimal-promotion`  
**Created**: 2026-07-21  
**Status**: Draft  
**Input**: User description: "Build the Validation & Minimal Promotion capability for the first candidate feature (News Deduplication) so it can safely move from Shadow Mode into Production."

---

## 1 Feature Summary

This feature establishes the decision-support validation and controlled promotion framework required to safely migrate the first production candidate feature (`news_dedup`) from Shadow Mode into Production. To guarantee safety, transparency, and reversibility, the feature specifies:

1. **A Challenger Validation Report**: An automated or on-demand tool that aggregates and analyzes the past 14 days of shadow execution data for a specific rule. The report calculates operational metrics (deduplication rate, article counts, etc.) and quality metrics (false-positive rate, sentiment impact) to provide a clear, machine-readable validation artifact.
2. **A Minimal Promotion Gate (Rule Manager)**: A state management module that tracks the lifecycle state of experimental rules (shadow, production, disabled). It exposes administrative controls to transition a rule to production and an immediate kill-switch to revert to baseline behavior, alongside a query interface for runtime routing.
3. **A Controlled Promotion Path**: A routing gate that dynamically switches the live pipeline inputs. When promoted and active, the pipeline feeds the deduplicated article list into live sentiment scoring. When disabled, killed, or not yet promoted, it defaults to the original, undeduplicated article list with zero runtime risk.

---

## Clarifications

### Session 2026-07-21

- Q: How should users retrieve and view the generated validation reports? → A: Both CLI command and saved files: Expose a CLI command to trigger/view the report, which also automatically writes the output files to a standardized reports directory.
- Q: What is the explicit maximum latency budget allowed for retrieving a rule's active state during live pipeline runs? → A: Strict sub-2 milliseconds: Require state lookups to resolve in under 2ms using local in-memory caching to avoid external DB calls on every scan.
- Q: How should the system access the "Sprint 1 baseline" metrics to compare the false-positive rate? → A: Static configuration parameter: Define a fixed baseline false-positive rate (e.g., in a configuration file or environment variable) that is loaded dynamically during report generation.

---

## 2 Previous Specification Review

- **FEAT-011 (News Deduplication & Research Workflows)**: Implemented the core deduplication engine heuristic and the isolated shadow execution pathway that logs to `news_deduplication_audit` and records telemetry in `shadow_outputs`. The validation report defined here will consume these database records.
- **AGENTS.md / CLI Governance**: Command routes map agent governance commands to CLI handlers. The promotion gate commands must integrate into this governance interface.

---

## 3 Architecture Overview

The recommendation pipeline currently runs in a bifurcated mode:
- **Production Pipeline**: Sentiment scoring reads the full, unfiltered article list.
- **Shadow Pipeline**: Runs in parallel, applying deduplication to the same inputs, saving outputs to a shadow audit log, but without impacting production scores.

This feature introduces a dynamic **Routing Gate** between article retrieval and sentiment scoring:
- If a rule's active state is `production`, the sentiment scoring engine is fed the deduplicated article list.
- If a rule's active state is `shadow` or `disabled`, the sentiment scoring engine is fed the original article list.

---

## 4 User Scenarios & Testing *(mandatory)*

### User Story 1 - Challenger Validation Report (Priority: P1)

As a quantitative risk officer, I want to review an objective analysis of the shadow execution data over the last 14 days before promoting the news deduplication rule, so that I can confirm it behaves as expected and does not degrade signal quality.

**Why this priority**: Core decision-support artifact required before any promotion action can be taken.
**Independent Test**: Generate a validation report for a rule with 14 days of logged shadow data and verify that all key metrics are populated and formatted in a clear, machine-readable layout.

**Acceptance Scenarios**:

1. **Given** the news deduplication rule has been running in shadow mode for 14 days, **When** the validation report is generated, **Then** the report calculates and outputs:
   - Total recommendations analyzed.
   - Total articles processed.
   - Total articles deduplicated.
   - Deduplication rate (total articles deduplicated / total articles processed).
   - Average production sentiment score under shadow execution.
   - False-positive rate of the shadow recommendations.
2. **Given** a generated validation report, **When** inspected by a human or automated parser, **Then** the report is output in a structured, machine-readable format (e.g., JSON) alongside a clean human-readable summary.

---

### User Story 2 - Minimal Promotion Gate & Kill-Switch (Priority: P1)

As a system administrator, I want to deliberately promote the news deduplication rule from shadow to production or disable it instantly if anomalies occur, using a single, clear action.

**Why this priority**: Essential safety control to prevent runaway behavior or unexpected production degradation.
**Independent Test**: Promote a rule, verify that its active status query returns `production`, then trigger the kill-switch and verify its status immediately transitions to `disabled`.

**Acceptance Scenarios**:

1. **Given** a rule is in `shadow` state and has a valid validation report and completed review checklist, **When** an authorized administrator promotes the rule, **Then** the rule's lifecycle state updates to `production`.
2. **Given** a rule is in `production` state, **When** the administrator activates the kill-switch, **Then** the rule's lifecycle state immediately transitions to `disabled` and the change is logged for audit purposes.
3. **Given** a query is made by the live pipeline for a rule's active state, **When** the state is checked, **Then** the gate returns the current active state (`shadow`, `production`, or `disabled`) with sub-millisecond response latency.

---

### User Story 3 - Controlled Promotion Path Integration (Priority: P1)

As a live trading system user, I want the system to dynamically route articles so that my live recommendations use deduplicated articles when the rule is promoted, and immediately fallback to undeduplicated articles if the rule is killed.

**Why this priority**: Guarantees high availability and zero residual impact on live systems during promotion or emergency rollback.
**Independent Test**: Simulate live recommendation scoring under different rule states (`shadow`, `production`, `disabled`) and verify that the correct article list is passed to sentiment scoring.

**Acceptance Scenarios**:

1. **Given** a rule is in `production` state, **When** a recommendation scan runs, **Then** the sentiment scoring engine processes only the deduplicated article list, and the generated recommendation utilizes this deduplicated sentiment score.
2. **Given** a rule is in `shadow` or `disabled` state, **When** a recommendation scan runs, **Then** the sentiment scoring engine processes the original, undeduplicated article list, and the shadow deduplication logic runs in parallel (if in `shadow`) or is bypassed entirely (if in `disabled`).
3. **Given** the rule is promoted or killed during a recommendation run, **When** the pipeline queries the active state, **Then** the system switches behavior atomically between runs without causing pipeline execution failures, crashes, or hung states.

---

### Edge Cases

- **Incomplete Shadow Data (Under 14 Days)**: If a validation report is requested but fewer than 14 days of shadow data are available, the report must output a clear warning indicating the data is incomplete, while still displaying metrics calculated for the available time window.
- **Concurrent Promotion / Kill Signals**: If a promote command and a kill command are issued simultaneously or in rapid succession, the system must process them sequentially, with the kill command always taking precedence (reverting to baseline/disabled state) to ensure safety.
- **State Store Unavailability**: If the state repository tracking rule states is unavailable during live execution, the pipeline must fail-safe by defaulting to `disabled` (original baseline logic) and issuing a high-priority system alert.

---

## 5 Requirements *(mandatory)*

### Functional Requirements

#### Challenger Validation Report
- **FR-001**: The system MUST support generating a validation report for the `news_dedup` rule analyzing the last 14 days of shadow execution data.
- **FR-002**: The validation report MUST calculate the following metrics:
  - Total recommendations analyzed.
  - Total articles processed.
  - Total articles deduplicated.
  - Deduplication rate (percentage of deduplicated articles relative to total processed).
  - Average production sentiment score under shadow execution.
  - False-positive rate of shadow recommendations.
- **FR-003**: The false-positive rate MUST be calculated using automatic log correlation, where false positives are inferred if a generated shadow recommendation is not acted upon or falls below threshold actions (e.g., no order executed) within a standard time window of 24 hours. The generated report MUST compare this calculated rate against a statically configured Sprint 1 baseline value loaded from system configuration.
- **FR-004**: The validation report MUST be generated in both a structured machine-readable format (JSON) and a human-readable format (Markdown) by invoking a CLI command (e.g., `experiment.report`), which prints the output to `stdout` and automatically persists the output files to a standardized directory (e.g., `governance/reports/`).

#### Minimal Promotion Gate (Rule Manager)
- **FR-005**: The system MUST track the lifecycle state of each experimental rule, supporting three distinct states: `shadow`, `production`, and `disabled`.
- **FR-006**: The system MUST provide administrative controls to transition a rule's state:
  - Transition from `shadow` to `production` (Promotion).
  - Transition from `production` to `disabled` (Kill Switch).
- **FR-007**: The system MUST expose a query interface that returns the current lifecycle state of a rule to the live pipeline with strict sub-2 millisecond latency (achieved via local in-memory caching of the rule state to avoid external database roundtrips during live recommendation scans).
- **FR-008**: Transitioning a rule state via the administrative controls MUST be performed via a CLI command interface, specifically by extending the existing `/specify` agent command router (`app.governance.experiment_cli`) with promotion and kill commands.
- **FR-009**: The system MUST log all state transitions to an audit log containing the operator name, timestamp, previous state, new state, and promotion/kill reason.

#### Controlled Promotion Path
- **FR-010**: The recommendation pipeline MUST check the rule's active state before executing sentiment scoring.
- **FR-011**: When the rule state is `production`, the pipeline MUST feed the deduplicated article list into the live sentiment scoring engine.
- **FR-012**: When the rule state is `shadow` or `disabled`, the pipeline MUST feed the original, undeduplicated article list into the live sentiment scoring engine.
- **FR-013**: If the rule state is `shadow`, the system MUST execute the deduplication logic in the background in parallel (shadow mode) and log output statistics, without affecting the production path.
- **FR-014**: The pipeline MUST enforce that promotion to `production` is only permitted after a process-level check (assertive flag), where the operator must explicitly supply a command flag (e.g., `--checklist-approved`) asserting that they have reviewed the validation report and completed the FEAT-010 human review checklist.

---

### Key Entities

- **Experimental Rule**: Represents a candidate feature rule (e.g., `news_dedup`). Attributes: `rule_id` (string), `name` (string), `state` (enum: shadow / production / disabled), `updated_at` (datetime).
- **Validation Report**: The metrics artifact compiled from shadow data. Attributes: `report_id` (string), `rule_id` (string), `generated_at` (datetime), `metrics` (JSON object including counts, deduplication rate, and false-positive rate).
- **State Transition Audit Log**: A persistent record of rule state changes. Attributes: `log_id` (string), `rule_id` (string), `operator` (string), `timestamp` (datetime), `from_state` (enum), `to_state` (enum), `reason` (string).

---

## 6 Success Criteria *(mandatory)*

### Measurable Outcomes
- **SC-001**: A Challenger Validation Report can be generated for 14 days of shadow data, clearly showing if the deduplication rate is between 5% and 40% and comparing the false-positive rate against the Sprint 1 baseline.
- **SC-002**: A rule state transition command (promote or kill) executes and takes effect within 1 second of invocation.
- **SC-003**: When a rule is promoted to `production`, the sentiment scoring engine uses the deduplicated article list for all subsequent live recommendation calculations.
- **SC-004**: When the kill-switch transitions a rule to `disabled`, the sentiment scoring engine immediately (on the next execution cycle) reverts to using the original undeduplicated article list with zero residual impact.
- **SC-005**: All state transitions are logged with 100% auditability, including references to the validation report and human review checklist completion.

---

## 7 Assumptions

- **Single Admin Role**: All authenticated operators have full access to promote or kill rules, in accordance with Phase 0 scope.
- **Data Availability**: Adequate shadow mode logging has occurred over the last 14 days to compile the validation report.
- **Heuristic Baseline**: The Sprint 1 baseline data is available in the database for comparative metrics (e.g., comparing false-positive rates).
- **Graceful Failures**: Any network, database, or logic error in querying rule state falls back to baseline behavior to prevent live recommendation calculation failure.
