# Feature Specification: Validation, Interaction Analysis, Point-Budget Rebalancing & Controlled Promotion

**Feature Branch**: `015-shadow-promotion-rebalance`  
**Created**: 2026-07-22  
**Status**: Draft  
**Input**: User description: "Build the Validation, Interaction Analysis, Point-Budget Rebalancing, and Controlled Promotion process for the two shadow features delivered in Sprint 7 (Sentiment Time-Decay and Market Breadth)."

---

## 1 Feature Overview

Following the parallel shadow mode data collection in Sprint 7 for **Sentiment Time-Decay (FEAT-018)** and **Market Breadth (FEAT-016)**, this feature defines the formal evaluation, matrix rebalancing, and controlled sequential promotion process required to transition these candidate features into live production recommendation scoring.

### Core Workflow Pillars

1. **Attribution & A/B Ablation Report**: Evaluates empirical shadow data to compare recommendation performance across four distinct candidate configurations:
   - *Baseline*: Existing production scoring engine.
   - *Decay-Only*: Baseline with Sentiment Time-Decay applied.
   - *Breadth-Only*: Baseline with Market Breadth soft scoring applied.
   - *Combined*: Baseline with both Sentiment Time-Decay and Market Breadth applied.
   - Measures and isolates false-positive reduction, win-rate impact, and signal accuracy attributable to each candidate feature.

2. **Feature Interaction & Redundancy Check**: Analyzes mathematical and statistical correlation between Sentiment Time-Decay and Market Breadth outputs across historical market situation tags to determine whether the signals are complementary or redundant. Produces a binding Go / No-Go promotion decision.

3. **Point-Budget Matrix Rebalancing**: Rebalances the production 100-point scoring matrix to allocate permanent points for Market Breadth while ensuring the sum of all scoring factors remains strictly equal to 100 points. Applies the principle of minimal disruption by adjusting factors with demonstrated score slack.

4. **Controlled Sequential Promotion**:
   - *Stage 1*: Promotes Sentiment Time-Decay as a calibration enhancement to the sentiment scoring sub-system.
   - *Stage 2*: Promotes Market Breadth as a structural enhancement to the 100-point composite scoring matrix (subject to positive Go decision).
   - Enforces strict kill-switch governance, rollback readiness, and post-promotion health verification for both features.

---

## 2 User Scenarios & Testing *(mandatory)*

### User Story 1 - A/B Attribution & Interaction Analysis (Priority: P1)

As a quantitative researcher, I want an automated attribution report and feature interaction analysis comparing baseline, decay-only, breadth-only, and combined configurations across situation tags so that I can objectively decide which shadow candidate features to promote.

**Why this priority**: Essential prerequisite to prevent promoting unverified or redundant features into live production.

**Independent Test**: Execute the attribution report generator against historical shadow dataset containing situation tags, verify 4-way ablation metrics output, verify feature correlation calculation, and confirm Go / No-Go decision recommendation.

**Acceptance Scenarios**:

1. **Given** historical shadow data with situation tags, **When** attribution analysis is executed, **Then** the system outputs comparative performance metrics (false-positive rate, precision, signal accuracy) for Baseline, Decay-Only, Breadth-Only, and Combined configurations.
2. **Given** paired shadow outputs for Sentiment Time-Decay and Market Breadth, **When** interaction analysis is performed, **Then** the system calculates feature correlation and flags whether the signals provide complementary value or redundant overlap.
3. **Given** completed attribution and interaction results, **When** the evaluation report is generated, **Then** it provides an explicit Go / No-Go recommendation for promoting Sentiment Time-Decay and Market Breadth independently.

---

### User Story 2 - Point-Budget Matrix Rebalancing (Priority: P1)

As a portfolio manager, I want the production 100-point recommendation matrix to be rebalanced with absolute mathematical integrity so that adding Market Breadth maintains a total sum of exactly 100 points without disrupting baseline stability.

**Why this priority**: Critical requirement to prevent point-budget inflation, invalid recommendation thresholds, or corrupted scoring math.

**Independent Test**: Pass a proposed matrix allocation containing Market Breadth points to the matrix validator, verify that the total matrix sum equals exactly 100 points, confirm minimal disruption constraint, and verify valid score range bounds $[0, 100]$.

**Acceptance Scenarios**:

1. **Given** a new point allocation incorporating Market Breadth, **When** matrix rebalancing is validated, **Then** the sum of all scoring component weights strictly equals 100 points.
2. **Given** multiple candidate rebalancing models, **When** rebalancing is evaluated, **Then** point deductions are drawn preferentially from scoring factors exhibiting highest slack/variance without altering core signal weights unnecessarily.
3. **Given** an invalid matrix allocation where sum $\ne 100$, **When** rebalancing validation runs, **Then** the system rejects the allocation with an explicit validation error and blocks promotion.

---

### User Story 3 - Controlled Sequential Promotion & Kill-Switch Governance (Priority: P2)

As a system administrator, I want to promote approved candidate features sequentially (Sentiment Time-Decay first, Market Breadth second) with instant kill-switch capability so that production recommendation performance is safely updated and instantly reversible.

**Why this priority**: Ensures zero operational risk during live rollout and guarantees clean rollback pathways if post-promotion anomalies occur.

**Independent Test**: Trigger Stage 1 promotion of Sentiment Time-Decay, verify live sentiment calculation updates while Market Breadth remains in shadow mode; trigger Stage 2 promotion of Market Breadth, verify rebalanced matrix scoring; activate kill-switch for either feature, verify immediate fallback to baseline logic without system downtime.

**Acceptance Scenarios**:

1. **Given** an approved attribution report, **When** Stage 1 promotion is executed, **Then** Sentiment Time-Decay transitions to active production sentiment scoring while Market Breadth remains in Shadow Mode.
2. **Given** successful Stage 1 rollout, **When** Stage 2 promotion is executed, **Then** Market Breadth transitions to active production scoring using the rebalanced 100-point matrix.
3. **Given** an active production feature (Time-Decay or Market Breadth), **When** its kill-switch is engaged, **Then** the system immediately reverts that feature to safe baseline behavior without throwing errors or requiring application restarts.

---

### Edge Cases

- **Inconclusive Attribution Data**: How does the system handle scenarios where shadow sample size is insufficient or A/B performance delta is statistically neutral? It defaults to a "No-Go" decision for promotion, keeping the feature in Shadow Mode to accumulate more data.
- **High Feature Correlation (>0.85)**: How does the system handle two candidate features that show very high correlation? It flags redundancy and recommends promoting only the primary feature (Sentiment Time-Decay) while rejecting or deferring the secondary feature.
- **Kill-Switch Engagement During Live Request**: How does the system handle kill-switch toggling mid-scan? Active requests finish using the configuration active at request start, while subsequent requests immediately pick up the disabled state without state corruption.
- **Matrix Under/Overflow**: How does the system handle rounding errors during score summation? Integer point budgets are enforced so all factor allocations sum to exactly 100 without fractional drift.

---

## 3 Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an Attribution & A/B Ablation process that evaluates historical shadow data across four configurations: Baseline, Decay-Only, Breadth-Only, and Combined.
- **FR-002**: Attribution analysis MUST quantify false-positive reduction, signal precision, and accuracy metrics for each configuration across market situation tags.
- **FR-003**: System MUST perform a Feature Interaction Check that calculates statistical correlation between Sentiment Time-Decay and Market Breadth outputs to determine signal redundancy versus complementarity.
- **FR-004**: System MUST generate a decision-ready Evaluation & Interaction Report that delivers explicit Go / No-Go promotion recommendations for each candidate feature.
- **FR-005**: System MUST enforce a Point-Budget Matrix Rebalancing rule requiring that any scoring matrix incorporating Market Breadth sums to exactly 100 points.
- **FR-006**: Matrix rebalancing MUST follow the principle of minimal disruption, deducting points from existing scoring factors with verified slack rather than core primary signals.
- **FR-007**: System MUST support Controlled Sequential Promotion, promoting Sentiment Time-Decay in Stage 1 (calibration update) prior to promoting Market Breadth in Stage 2 (structural matrix update).
- **FR-008**: System MUST block Stage 2 promotion until Stage 1 promotion has been verified and approved in live execution.
- **FR-009**: System MUST provide independent, operational kill-switches for both Sentiment Time-Decay and Market Breadth, allowing either feature to be instantly disabled and reverted to baseline behavior.
- **FR-010**: System MUST verify post-promotion recommendation quality, ensuring live performance metrics match or exceed baseline benchmarks post-rollout.

---

### Key Entities

- **AttributionReport**: Represents the structured A/B ablation evaluation results, including sample size, performance metrics per configuration (Baseline, Decay-Only, Breadth-Only, Combined), situation tag breakdowns, and feature attribution scores.
- **InteractionAnalysis**: Represents the correlation assessment between candidate features, containing correlation coefficient, redundancy classification (complementary vs redundant), and promotion decision (Go vs No-Go).
- **ScoringMatrixConfig**: Represents the active 100-point composite scoring matrix structure, detailing individual factor weights, sum invariant check ($=100$), version number, and rebalancing audit history.
- **PromotionStateRecord**: Represents the governance status of candidate features, tracking current state (`shadow`, `promoted_stage_1`, `promoted_stage_2`, `disabled_killswitch`), execution timestamp, and active kill-switch flags.

---

## 4 Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of candidate feature promotions are preceded by a complete A/B attribution report and feature interaction check.
- **SC-002**: 100% of valid scoring matrix configurations strictly sum to exactly 100 points with zero tolerance for budget variance.
- **SC-003**: Engaging a kill-switch for either promoted feature reverts scoring to baseline behavior in under 1 second without service disruption.
- **SC-004**: Sequential promotion completes with zero unhandled runtime exceptions during live scan operations.
- **SC-005**: Post-promotion recommendation precision across live scans matches or improves upon pre-promotion baseline metrics.

---

## 5 Assumptions

- **Shadow Dataset Availability**: Sufficient shadow mode telemetry from Sprint 7 is available in `analysis_history` across diverse market situation tags.
- **RuleManager Governance**: The RuleManager and feature-flag infrastructure established in Sprint 5 is operational for managing feature promotion states and kill-switches.
- **Scoring Engine Modularity**: The recommendation scoring engine supports dynamic factor weighting and matrix configuration updates.
