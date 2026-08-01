# Feature Specification: Operational Governance & Analytics Layer

**Feature Branch**: `016-operational-governance-analytics`  
**Created**: 2026-07-22  
**Status**: Draft  
**Input**: User description: "Build the long-term operational layer that turns the Recommendation Engine from a one-time project into a living, self-monitoring system. 1. Production Rule Governance (FEAT-026) 2. Sector Strength – Watch-Only Feature (FEAT-020) 3. Lightweight Analytics Dashboard (FEAT-028)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Production Rule Governance Review (Priority: P1)

As a trading system administrator or quant operator, I want an automated weekly governance report evaluating all promoted production rules (News Deduplication, Sentiment Time-Decay, Market Breadth) so that I can detect performance degradation or strategy decay early before it impacts live results.

**Why this priority**: Promoted rules can experience strategy decay over time. Without recurring health checks against historical baselines, performance drift goes unnoticed until live outcomes suffer.

**Independent Test**: Can be tested by triggering a governance report generation on demand and verifying that every promoted rule is assigned an accurate health status based on its 30-day false-positive rate compared to baseline.

**Acceptance Scenarios**:

1. **Given** promoted rules with active 30-day performance data, **When** a governance report is generated, **Then** the report presents the 30-day false-positive rate, baseline performance, and assigned health status (`healthy`, `caution`, `degraded`, or `insufficient data`) for News Deduplication, Sentiment Time-Decay, and Market Breadth rules.
2. **Given** a promoted rule whose recent 30-day false-positive rate has degraded beyond configured thresholds relative to its baseline, **When** governance evaluation runs, **Then** the system flags that rule as `caution` or `degraded` in the machine-readable output.
3. **Given** a rule with fewer data points than required for statistical validity in the last 30 days, **When** governance evaluation runs, **Then** the rule is assigned an `insufficient data` status without causing evaluation errors.

---

### User Story 2 - Passive Sector Strength Tracking in Shadow Mode (Priority: P2)

As a quant researcher, I want Sector Strength to be calculated passively relative to broader market benchmarks on every market scan so that historical regime dataset accumulates for future feature development without risking live scoring integrity.

**Why this priority**: Sector strength is a high-value regime signal, but needs historical validation before influencing live scores. Passive collection builds full historical context safely.

**Independent Test**: Can be tested by running market scans in shadow mode and confirming sector strength values are persisted in shadow output storage while verifying live 100-point scoring matrices and recommendation decisions remain completely unchanged.

**Acceptance Scenarios**:

1. **Given** an active market scan cycle, **When** the scan processes, **Then** relative sector strength against the market benchmark is calculated and recorded into shadow storage.
2. **Given** any sector strength calculation output or calculation failure, **When** live recommendations are evaluated, **Then** the live 100-point scoring matrix and final recommendation decisions are entirely unaffected by sector strength values.
3. **Given** consecutive market scans over time, **When** sector strength data is queried from shadow output storage, **Then** continuous, time-indexed sector performance records are available with full historical context.

---

### User Story 3 - Lightweight Operational Analytics Endpoints (Priority: P3)

As a system operator, I want programmatic analytics endpoints providing 7-day engine health metrics, shadow rule telemetry, and latest governance statuses so that day-to-day monitoring can be performed instantly without manual database queries.

**Why this priority**: Operational efficiency and ritual consistency require frictionless visibility into internal engine state without requiring direct SQL access.

**Independent Test**: Can be tested by querying the analytics endpoints and confirming accurate responses for 7-day recommendation counts/outcomes, active shadow rule statistics, and rule governance health summaries.

**Acceptance Scenarios**:

1. **Given** active recommendation activity over the past week, **When** an operator queries the engine health endpoint, **Then** the response provides recommendation totals, signal distribution, and outcome metrics for the rolling 7-day window.
2. **Given** running shadow rules (including Sector Strength), **When** an operator queries the shadow telemetry endpoint, **Then** the response details active shadow rule statuses, run counts, and latest output metrics.
3. **Given** completed governance evaluations, **When** an operator queries the rule status endpoint, **Then** the response returns the latest health statuses and false-positive deltas for all promoted rules.

---

### Edge Cases

- How does the system handle missing or incomplete market benchmark data during sector strength calculation?
  *The sector strength calculation logs a non-blocking shadow telemetry warning, assigns a neutral/null shadow metric for that scan, and allows the live scan to complete without interruption.*
- What happens if a rule has zero recommendations generated in the last 30 days during governance review?
  *The system assigns an `insufficient data` health status and records zero evaluation counts in the report.*
- How does the dashboard endpoint perform when historical database logs contain millions of scan records?
  *Analytics endpoints query pre-aggregated operational summaries or indexed rolling metrics to ensure response times remain fast under large data volumes.*

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an automated governance process that evaluates promoted rules (News Deduplication, Sentiment Time-Decay, Market Breadth) on a recurring weekly cycle or on-demand.
- **FR-002**: System MUST calculate the 30-day rolling false-positive rate for each promoted rule and compare it against the rule's original baseline false-positive metric.
- **FR-003**: System MUST classify each promoted rule into one of four health statuses: `healthy`, `caution`, `degraded`, or `insufficient data` based on false-positive rate variance.
- **FR-004**: System MUST generate a standardized, machine-readable governance report summary capturing evaluation metrics, baseline deltas, and health statuses for weekly review.
- **FR-005**: System MUST passively calculate Sector Strength relative to broader market benchmark indices during each market scan.
- **FR-006**: Sector Strength calculations MUST run strictly in watch-only / shadow mode and MUST NOT alter, weight, or impact the live 100-point scoring matrix or recommendation outputs.
- **FR-007**: System MUST persist all calculated Sector Strength values and execution metadata in shadow output storage for historical context retention.
- **FR-008**: System MUST expose an engine health analytics endpoint providing rolling 7-day summary metrics of recommendation volumes, signal distribution, and system outcomes.
- **FR-009**: System MUST expose a shadow telemetry analytics endpoint providing status, execution counts, and output metrics for all active shadow rules.
- **FR-010**: System MUST expose a rule governance status endpoint returning the most recent health evaluations and baseline comparison metrics for all promoted rules.
- **FR-011**: System MUST maintain strict fault isolation between shadow/governance processes and live recommendation generation, ensuring shadow or governance failures never disrupt live operations.

### Key Entities

- **Rule Governance Record**: Represents a health evaluation snapshot of a promoted production rule. Includes rule identifier, evaluation timestamp, 30-day false-positive rate, baseline false-positive rate, sample count, health status, and status reason.
- **Sector Strength Telemetry**: Represents passive shadow evaluation of sector performance. Includes scan timestamp, sector identifier, benchmark index identifier, relative performance metric, and shadow execution status.
- **Engine Operational Telemetry**: Aggregated operational summary of engine performance. Includes 7-day recommendation counts, signal outcome rates, active shadow rule statistics, and latest governance summary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On-demand or scheduled governance reports successfully evaluate 100% of promoted production rules and assign clear health statuses with 30-day baseline comparisons.
- **SC-002**: 100% of Sector Strength calculations execute silently in shadow mode during market scans, storing output telemetry without introducing any variation into live 100-point scoring results.
- **SC-003**: System operators can complete weekly system health reviews using exclusively governance reports and analytics endpoints, eliminating 100% of routine ad-hoc SQL query dependencies.
- **SC-004**: Analytics dashboard endpoints return aggregated health summaries, shadow telemetry, and governance statuses within 2 seconds.
- **SC-005**: Zero live recommendation pipeline failures or score anomalies are caused by shadow calculation errors or governance report generation.

## Assumptions

- Historical baseline metrics for News Deduplication, Sentiment Time-Decay, and Market Breadth were established during their respective promotion reviews and are available for comparison.
- Market benchmark index price/return data is available during standard market scan runs.
- Governance health classification rules use defined variance thresholds (e.g., within baseline tolerance = `healthy`, minor degradation = `caution`, significant degradation = `degraded`, insufficient sample size = `insufficient data`).
- Analytics endpoints are accessible to authenticated system operators in accordance with single-admin operational governance access controls.
