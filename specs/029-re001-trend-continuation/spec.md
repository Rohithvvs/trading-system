# Feature Specification: RE-001 Trend Continuation Recommendation Engine Integration

**Feature Branch**: `029-re001-trend-continuation`  
**Created**: 2026-08-03  
**Status**: Draft  
**Input**: Integrate RE-001 Trend Continuation Recommendation Engine as an additional engine inside the Recommendation Lab without redesigning or replacing the existing Trading Application recommendation pipeline.

**Business source of truth**: RE-001 Documents 01–02 and REDS v1.0 (Trading Lab “ALL REs”).  
**Implementation source of truth**: Existing trading-system application (scanner, recommendation, shadow/experiment, paper trading, analytics, APIs, dashboard).  
**RE-001 Document 03–05 status**: Not yet published in the RE corpus; technical integration contracts below are derived from REDS + Docs 01–02 + current application capabilities and are marked as assumptions where RE-001 Doc 03 would otherwise govern.

## Clarifications

### Session 2026-08-03

- Q: Where should RE-001 Recommendation Decision Objects be persisted for the MVP? → A: First-class `recommendation_engine_decisions` (or equivalent) table for RE-001 Decision Objects + comparison metadata
- Q: How should operators review production vs RE-001 decisions in the MVP UI? → A: Hybrid — RE-001 on symbol detail plus a compact Recommendation Lab comparison view (new tab/page) for scan-level production vs RE-001
- Q: Who may view RE-001 lab decisions and the compact Lab comparison surface? → A: Admin + Trader when lab feature permission / UI flag is enabled
- Q: On each scan/analysis run, which symbols must RE-001 evaluate in MVP? → A: Only symbols on the production shortlist / full-analysis set for that run
- Q: When market regime (or equivalent market context) is missing or unusable, what must RE-001 RecommendationState be? → A: REJECT with explicit missing-context reason code (never BUY)

### Session 2026-08-03 (analysis remediation)

- Q: Canonical engine stage enum? → A: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (ACTIVE reserved / out of scope); no SHADOW-LAB or LAB/SHADOW aliases in contracts
- Q: Feature permission key? → A: `recommendation_lab` only (not `re001_lab`)
- Q: Paper trade plan source for RE-001 prefill? → A: Prefer complete RE-001 trade guidance on Decision Object when present; else fall back to production `trade_plans` for the same symbol/scan; always stamp RE-001 provenance
- Q: Portfolio/risk snapshot for validation? → A: Prefer authenticated requesting user’s paper/risk snapshot; if unavailable (e.g. system/scheduler run), fail-closed for BUY → WATCH or REJECT with reason `portfolio_context_unavailable`
- Q: `scan_run_id` mapping? → A: Map to existing scan identity used by latest-scan / scan snapshot persistence (same identifier family the Lab comparison API lists by “completed scan”)
- Q: `PAPER_LINKED` vs `LAB_SHADOW`? → A: Both run RE-001 evaluation + persist; paper prefill from RE-001 is allowed in both lab stages for MVP, but `PAPER_LINKED` is the ops signal that paper attribution is an intentional validation mode; `OFF` disables all RE-001 side effects
- Q: SC-006 “materially lower”? → A: On shared fixture set, bear-regime RE-001 BUY count MUST be ≤ 50% of bull-regime RE-001 BUY count
- Q: SC-003 95% measurement? → A: Engineering gate = fail-open isolation tests; 95% is an operational soak metric after enablement (logged attempts vs production path failures attributable to RE-001 = 0)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lab Engine Produces Continuation Decisions Without Touching Production (Priority: P1)

As a quant operator, I want RE-001 to evaluate **only the production shortlist / full-analysis symbols** for trend-continuation setups in the Recommendation Lab while the existing production recommendation engine continues to publish BUY / WATCH / REJECT for the Scanner and Dashboard unchanged, so that we can validate a new institutional engine without risking production advisory quality or scan latency.

**Why this priority**: Brownfield safety and capital-preservation philosophy require isolation first. Production must remain authoritative until explicit promotion.

**Independent Test**: Run a full scan with RE-001 enabled in `LAB_SHADOW` mode; confirm production BUY/WATCH/REJECT lists and scores match a control run with RE-001 disabled, while RE-001 decision objects are still produced and stored for lab review.

**Acceptance Scenarios**:

1. **Given** RE-001 is registered and enabled in `LAB_SHADOW` (or `PAPER_LINKED`) mode, **When** a scanner or full-analysis run completes, **Then** production recommendations, shortlist ranking, and dashboard BUY/WATCH counts are identical to a run with RE-001 disabled.
2. **Given** a shortlisted symbol with sufficient market context, **When** RE-001 evaluates it, **Then** the system produces a standardized Recommendation Decision Object with EngineID = RE-001, RecommendationState ∈ {BUY, WATCH, REJECT}, strategy identity, confidence, evidence, and explanation.
3. **Given** RE-001 fails or times out for a symbol, **When** the pipeline continues, **Then** production analysis for that symbol still completes successfully and RE-001 failure is recorded without aborting the scan.

---

### User Story 2 - Operator Reviews RE-001 Decisions Side-by-Side (Priority: P1)

As a trader or research operator, I want to inspect RE-001’s primary strategy, supporting evidence, validation outcomes, and comparison to the production recommendation for the same symbol and scan, so that I can trust or challenge continuation setups before paper trading them.

**Why this priority**: REDS requires explainability and engine comparison before any promotion path. Operators cannot use RE-001 without transparent decision traces.

**Independent Test**: Open a symbol detail or lab comparison view after a scan and verify both production and RE-001 outcomes, strategy ownership, and evidence are visible for at least one BUY and one REJECT from RE-001.

**Acceptance Scenarios**:

1. **Given** both production and RE-001 decisions exist for a symbol, **When** the operator opens the symbol’s analysis detail in the lab or enhanced detail surface, **Then** they can see both RecommendationStates, scores/confidence, and RE-001 primary strategy name.
2. **Given** RE-001 selected Pullback Continuation as primary with Relative Strength and Volume as support, **When** the operator reads the explanation, **Then** primary vs supporting vs rejected strategies and validation results are distinguishable.
3. **Given** RE-001 issued REJECT due to market-regime or portfolio validation, **When** the operator reviews the decision, **Then** the reject reason is explicit (regime / risk / portfolio / insufficient evidence), not a silent empty result.

---

### User Story 3 - Paper Trade and Experiment Against RE-001 Outputs (Priority: P2)

As a research operator, I want to paper-trade and experiment-evaluate RE-001 recommendations through the existing validation lifecycle (paper trading, backtesting hooks, experiment framework) without promoting RE-001 to production shortlist ownership, so that promotion decisions are evidence-based.

**Why this priority**: REDS validation lifecycle and RE-001 success criteria require paper and experiment outcomes before production.

**Independent Test**: Prefill or tag a paper order from an RE-001 BUY decision; confirm paper account lifecycle works and experiment/analytics can attribute the idea to EngineID RE-001.

**Acceptance Scenarios**:

1. **Given** an RE-001 BUY decision, **When** the operator creates a paper ticket from that decision, **Then** entry/SL/target guidance is taken from RE-001 trade guidance when complete, otherwise from the production trade plan for the same symbol/scan, and the ticket is attributable to RE-001 (`source_engine_id`, version, `recommendation_id`).
2. **Given** multiple days of RE-001 lab runs, **When** experiment or analytics health views are queried for RE-001, **Then** counts of BUY/WATCH/REJECT and mismatch vs production (if compared) are available for the configured window.
3. **Given** RE-001 is not promoted, **When** daily scanner shortlist and production BUY lists are built, **Then** they continue to be driven solely by the existing production recommendation engine.
4. **Given** stage is `OFF`, **When** the operator attempts paper prefill from RE-001, **Then** no new RE-001-originated prefill is available from lab decisions for that disabled period.

---

### User Story 4 - Regime-Adaptive Continuation Behavior (Priority: P2)

As a quant operator, I want RE-001 to participate more in bull regimes, tighten confirmation in sideways regimes, and mostly preserve capital in bear regimes, so that continuation recommendations remain consistent with RE-001 philosophy.

**Why this priority**: Market-before-stock and adaptive strategy orchestration are core RE-001 invariants.

**Independent Test**: Feed or simulate three market-regime contexts (bull / sideways / bear) for the same technical setup and confirm participation aggressiveness and strategy priority shift as specified (without changing production engine labels).

**Acceptance Scenarios**:

1. **Given** market regime = Bull and a valid primary continuation setup, **When** RE-001 evaluates, **Then** participation is allowed under normal confidence rules with priority favoring Trend Following / Pullback / Momentum / Breakout as defined in RE-001 Doc 02.
2. **Given** market regime = Sideways, **When** RE-001 evaluates pullback-like setups, **Then** stricter confirmation is required and breakout/relative-strength priority is preferred.
3. **Given** market regime = Bear, **When** RE-001 evaluates ordinary continuation setups, **Then** most candidates become WATCH or REJECT except exceptional relative-strength leaders.

---

### User Story 5 - Register, Configure, and Disable RE-001 Safely (Priority: P3)

As a system administrator, I want feature flags and engine registration controls so that RE-001 can be enabled, disabled, versioned, and limited to `LAB_SHADOW` / `PAPER_LINKED` without code redeploy for every operational change.

**Why this priority**: Operational safety and REDS governance require explicit stage control (`OFF` / `LAB_SHADOW` / `PAPER_LINKED`; future `ACTIVE` only after promotion — out of scope).

**Independent Test**: Toggle RE-001 off via configuration; confirm no RE-001 decisions are produced and production path is unchanged; toggle `LAB_SHADOW` on and confirm decisions resume.

**Acceptance Scenarios**:

1. **Given** RE-001 master flag is OFF, **When** scans run, **Then** no RE-001 decision objects are generated and no lab UI sections depend on RE-001 data.
2. **Given** RE-001 is registered with version 1.0, **When** decisions are persisted, **Then** EngineID and EngineVersion are stored with every RE-001 Recommendation Decision Object.
3. **Given** an unauthorized or non-feature-permitted user, **When** they attempt lab-only RE-001 comparison surfaces, **Then** access is denied per existing auth and feature-permission model.
4. **Given** an authenticated Trader or Admin with the lab feature permission enabled, **When** they open symbol detail or compact Lab comparison after a lab run, **Then** RE-001 decisions are visible.

---

### Edge Cases

- **Missing market regime / unusable market context**: RE-001 MUST emit RecommendationState **REJECT** with an explicit reason code (e.g. `missing_market_context`); never BUY; never silent skip without a Decision Object when the symbol was in the evaluation set. Production path unaffected.
- **Missing breadth / sector as supporting inputs only**: When regime is present but supporting context is incomplete, RE-001 MUST NOT issue BUY solely on incomplete support; prefer lower confidence WATCH or REJECT with explicit evidence (regime missing remains REJECT per above).
- **Insufficient history for bull-stock filter or indicators**: Symbol is ineligible for RE-001 evaluation; recorded as REJECT or skipped-with-reason; not treated as BUY.
- **Multiple primary strategies qualify**: Exactly one primary strategy owns the recommendation; others become supporting evidence (RE-001 Doc 02 conflict resolution).
- **Validation fails after primary qualifies**: Result is WATCH or REJECT; never silent BUY.
- **Production BUY but RE-001 REJECT (or reverse)**: Both outcomes are retained for comparison; production shortlist still uses production action until promotion.
- **RE-001 timeout / exception**: Isolated; production result retained; error logged and counted in lab health metrics.
- **Empty shortlist**: No RE-001 work beyond idle/no-op; no spurious decisions.
- **Non-shortlisted matched symbols**: Not evaluated by RE-001 in MVP (even if screener matched).
- **Concurrent scans**: RE-001 execution must respect existing scan locking and must not corrupt production persistence.
- **Paper account risk limits**: Portfolio/risk validation may force REJECT even if technical continuation is strong (portfolio-before-trade).
- **No portfolio/risk snapshot** (scheduler or user without paper account): Fail-closed for BUY → WATCH or REJECT with reason `portfolio_context_unavailable`; never invent portfolio state.
- **RE-001 BUY without complete RE-001 trade guidance**: Paper prefill falls back to production trade_plans for same symbol/scan; provenance remains RE-001.
- **News/event extreme days**: RE-001 does not own news trading; news may only contribute as inherited shared context/supporting evidence, not as a primary RE-001 strategy family.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST register RE-001 as a distinct Recommendation Engine (EngineID = `RE-001`, name = Trend Continuation Recommendation Engine) inside the Recommendation Lab, without replacing the existing production recommendation engine.
- **FR-002**: System MUST keep the existing production recommendation pipeline (composite score → BUY/WATCH/REJECT, scanner shortlist, dashboard BUY/WATCH lists) behaviorally unchanged when RE-001 is disabled or running only in `LAB_SHADOW` / `PAPER_LINKED` mode.
- **FR-003**: RE-001 MUST emit only RecommendationStates BUY, WATCH, or REJECT (no additional states).
- **FR-004**: Every RE-001 evaluation MUST produce a standardized Recommendation Decision Object containing at minimum: RecommendationID, EngineID, EngineVersion, MarketRegime, TradingObjective, TradingStyle, StrategyFamily, StrategyName, RecommendationState, ConfidenceScore, RiskProfile, PortfolioDecision, Evidence, Explanation, Timestamp.
- **FR-005**: RE-001 MUST follow the REDS standard recommendation pipeline order: Market Context → Universe Selection → Eligibility Filtering (including Bull Stock Filter) → Strategy Selection → Technical Confirmation → Risk Validation → Portfolio Validation → Confidence Scoring → Recommendation Decision → Explanation → Decision Object.
- **FR-006**: RE-001 MUST NOT bypass Market Regime Detection or the Bull Stock Filter; it MAY apply stricter filters only.
- **FR-007**: RE-001 MUST orchestrate primary strategy families: Trend Following, Pullback Continuation, Breakout Continuation, Momentum Continuation — with exactly one primary strategy owning each recommendation when a BUY or WATCH is issued.
- **FR-008**: Supporting strategies (Relative Strength, Volume Confirmation, Multi-Timeframe Alignment, Sector Leadership, Market Breadth) MUST NOT independently generate recommendations; they only strengthen or weaken confidence.
- **FR-009**: Validation (market regime, liquidity, risk, portfolio, policy) MUST be able to reject or downgrade candidates and MUST never create a BUY by itself.
- **FR-010**: RE-001 MUST adapt strategy activation and priority by market regime per RE-001 Doc 02 (Bull / Sideways / Bear participation rules).
- **FR-011**: RE-001 MUST reuse existing shared platform capabilities for market data, technical indicators, news/events, sector/relative strength, market regime/breadth, backtesting, paper trading, analytics, scheduling, portfolio/risk, logging, configuration, and caching — it MUST NOT re-implement these as private parallel stacks.
- **FR-012**: RE-001 execution MUST be isolatable (feature-flagged) and fail-open with respect to production: RE-001 errors MUST NOT fail the production analysis path.
- **FR-013**: System MUST persist RE-001 decisions (and comparison metadata vs production when both exist) in a first-class queryable decisions table (e.g. `recommendation_engine_decisions` or equivalent) without overwriting production recommendation fields that drive current scanner shortlists. Namespaced JSON on `analysis_history` alone is not sufficient as the system of record for RE-001 Decision Objects.
- **FR-014**: Operators MUST be able to compare production vs RE-001 outcomes for the same symbol and scan context via (1) an RE-001 section on the existing symbol/analysis detail surface and (2) a compact Recommendation Lab comparison view (new tab or lightweight page) for scan-level side-by-side review. A full multi-engine Lab product is not required for MVP.
- **FR-015**: Operators MUST be able to originate paper-trading workflow from an RE-001 decision with engine provenance retained. **Trade guidance rule**: use complete RE-001 trade guidance on the Decision Object when present; otherwise fall back to production `trade_plans` for the same symbol and scan; provenance fields MUST still identify RE-001.
- **FR-016**: Analytics / experiment surfaces MUST expose RE-001 health metrics (decision counts by state, optional mismatch rate vs production, run success/failure) for a rolling operational window.
- **FR-017**: Scheduler-driven scans that already invoke the analysis pipeline MUST be able to include RE-001 lab evaluation when the engine is enabled, without requiring a separate manual batch as the only path. **MVP evaluation set**: RE-001 MUST evaluate only symbols on the production shortlist / full-analysis set for that run — not the full NIFTY500 and not the broader pre-shortlist matched set — unless a future feature expands the set.
- **FR-018**: RE-001 MUST be deterministic for a fixed version, fixed inputs, and fixed configuration (no live LLM-owned decision label; explanation text may reuse existing explainability services but MUST NOT solely determine BUY/WATCH/REJECT).
- **FR-019**: System MUST support configuration stages exactly: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (future `ACTIVE` reserved and out of scope for auto-promotion). Both `LAB_SHADOW` and `PAPER_LINKED` run evaluation+persist when `re001_enabled`; `OFF` disables all RE-001 side effects. `PAPER_LINKED` is the operational signal that paper attribution is intentional validation mode.
- **FR-020**: RE-001 MUST remain long-only swing, NIFTY500 universe, Indian equity cash market, advisory-only (no live broker order placement).
- **FR-021**: Mean reversion, event-driven, gap, news-primary, earnings-primary, sector-rotation-primary, fundamental-first, intraday, and short-selling philosophies MUST remain out of RE-001 scope.
- **FR-022**: Access to lab comparison and RE-001 decision surfaces MUST respect existing authentication and feature-permission patterns. **MVP visibility**: both Admin and Trader roles MAY view RE-001 symbol-detail and compact Lab comparison when feature key **`recommendation_lab`** is enabled. Operational stage/flag controls remain admin-appropriate; unauthenticated access is forbidden.
- **FR-023**: Every RE-001 decision MUST record decision trace elements needed for audit: primary strategy, supporting strategies, rejected strategies, validation results, and final rationale.
- **FR-024**: Bull Stock Filter eligibility for RE-001 MUST apply the shared REDS minimum intent (price vs intermediate/long MAs and bullish structure; relative strength recommended) using existing indicator/regime services rather than inventing a second market-data pipeline.
- **FR-025**: When market regime (or equivalent required market context) is missing or unusable for a symbol in the evaluation set, RE-001 MUST produce a Decision Object with RecommendationState = **REJECT** and an explicit missing-context reason code; it MUST NOT emit BUY and MUST NOT default to an assumed regime.
- **FR-026**: Portfolio validation MUST prefer the authenticated requesting user’s paper/risk snapshot when present. When no usable portfolio/risk snapshot exists (including scheduler/system runs without a user portfolio), RE-001 MUST fail-closed for BUY (WATCH or REJECT) with reason code `portfolio_context_unavailable` and MUST NOT invent portfolio state.
- **FR-027**: Lab comparison and persistence MUST associate each decision with a `scan_run_id` (or equivalent) mapped to the platform’s existing completed-scan identity used by latest-scan / scan snapshot flows so the compact Lab view can list one completed scan’s symbols.

### Key Entities

- **Recommendation Engine (registered)**: Logical engine identity (e.g., Production Composite Engine, RE-001) with version, stage, and enablement.
- **Recommendation Decision Object**: Standardized RE/lab decision payload (REDS §9 fields).
- **Production Recommendation**: Existing FinalRecommendation / shortlist-driving action for a symbol.
- **Primary Strategy**: One of Trend Following, Pullback Continuation, Breakout Continuation, Momentum Continuation owning a decision.
- **Supporting Evidence**: Secondary confirmations that adjust confidence but do not own the decision.
- **Validation Result**: Pass/fail outcomes for regime, liquidity, risk, portfolio, and policy checks.
- **Market Context**: Regime, breadth, sector leadership, and related shared inputs consumed before stock-level strategy evaluation.
- **Lab Comparison Record**: Paired production vs RE-001 outcomes for the same symbol/scan; stored with or linked from the first-class decisions table.
- **Engine Decision Record**: Durable row for one RE-001 Recommendation Decision Object (engine_id, version, symbol, scan/run identity, state, confidence, strategy fields, evidence/explanation payload, timestamps).
- **Engine Run Diagnostics**: Success/failure, duration, counts by RecommendationState for RE-001.
- **Experiment / Promotion Record**: Governance artefact for future promotion review (not auto-promote).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With RE-001 in `LAB_SHADOW` (or `PAPER_LINKED`) mode, production BUY/WATCH/REJECT labels and scanner shortlist membership match a disabled-RE-001 control on the same market snapshot for 100% of symbols in verification runs.
- **SC-002**: For every successfully completed RE-001 evaluation, operators can identify EngineID, primary strategy, RecommendationState, confidence, and at least one evidence rationale from the symbol/analysis detail surface without engineering database access.
- **SC-003**: Production path success MUST NOT decline due to RE-001 (engineering gate: fail-open isolation tests; RE-001 timeout/exception never fails production). Operational soak target after enablement: ≥95% of RE-001 evaluation attempts complete without RE-001-attributable production path failure (target: zero RE-001-caused production failures).
- **SC-004**: Operators can open the compact Recommendation Lab comparison view for a completed scan and review production vs RE-001 states for shortlisted symbols in under 2 minutes.
- **SC-005**: Paper tickets created from RE-001 decisions retain RE-001 provenance such that post-trade review can attribute ≥ 100% of those tickets to RE-001 (no silent untagged tickets).
- **SC-006**: On a controlled shared fixture set, bear-regime RE-001 BUY count MUST be ≤ 50% of bull-regime RE-001 BUY count for equivalent stock technical quality.
- **SC-007**: When RE-001 is toggled OFF, zero new RE-001 decision objects are created on subsequent scans.
- **SC-008**: Existing scanner, paper desk, analytics, and dashboard primary workflows remain usable without mandatory RE-001 UI steps (no forced lab gate for retail scanner use).

---

## Assumptions

- RE-001 Documents 01 and 02 plus REDS v1.0 are the business authority for philosophy, strategy orchestration, states, and inheritance rules.
- RE-001 Documents 03–05 (technical architecture, validation detail, deployment) are not yet published; integration mapping uses existing application services as the technical source of truth and REDS Shared Core Services as the logical service contract.
- The existing production composite recommendation engine remains the production shortlist authority until a separate, explicit promotion decision.
- “Recommendation Lab” is the multi-engine evaluation surface. **MVP UI (clarified)**: RE-001 section on symbol/analysis detail **plus** a compact Lab comparison view (new tab or lightweight page); full multi-engine Lab product page is out of MVP scope.
- REDS Shared Core Services map onto existing modules (see §11); greenfield rewrites of those services are out of scope.
- Bull / Sideways / Bear for RE-001 orchestration maps from existing market regime / market permission outputs via a documented mapping table (assumption until Doc 03 freezes exact labels).
- Default entry stage is `LAB_SHADOW` when enabling (settings default remains `OFF` until ops enables); not production `ACTIVE`.
- Canonical stages: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (`ACTIVE` reserved/out of scope).
- Feature permission key is exactly `recommendation_lab`.
- Advisory-only constraint remains: no live order routing.
- Strategy Library entries for the four primary families may start as RE-001-orchestrated rule sets implemented against existing technical features; full Strategy Library productization can be incremental if orchestration contracts remain stable.
- LLM reasoning remains explainability assist only for RE-001 labels (consistent with platform “no live LLM decisions” constraint).
- **MVP persistence (clarified)**: RE-001 Decision Objects and production-comparison metadata use a first-class decisions table; production `analysis_history.recommendation` remains production-only.
- **MVP UI (clarified)**: Hybrid — symbol detail RE-001 section + compact Lab comparison view; not admin-only; not full Lab product for MVP.
- **MVP lab visibility (clarified)**: Admin + Trader when `recommendation_lab` feature permission is enabled; not admin-only; not unauthenticated.
- **MVP evaluation set (clarified)**: Production shortlist / full-analysis symbols only — not full universe, not pre-shortlist matched set.
- **Missing market context (clarified)**: REJECT with explicit reason code; never BUY; never assume a default regime.
- **Paper trade guidance (clarified)**: RE-001 plan when complete → else production trade_plans; provenance always RE-001 when originated from lab decision.
- **Portfolio snapshot (clarified)**: Requesting user paper/risk when available; else fail-closed for BUY with `portfolio_context_unavailable`.
- **scan_run_id (clarified)**: Maps to existing completed-scan / latest-scan identity family.

---

# Integration Specification (Brownfield)

The following sections define the complete integration specification requested for planning and task generation. They describe **what must integrate where** against the current application, not greenfield redesign.

---

## 1. Executive Summary

### Why RE-001 is being added

The Trading Application already produces composite BUY / WATCH / REJECT recommendations. That production engine remains valuable and operational. Separately, the Trading Lab defines REDS (Recommendation Engine Development Standard) and a multi-engine roadmap (RE-001 → RE-007). **RE-001 — Trend Continuation Recommendation Engine** is the first institutional engine purpose-built to participate only in established trends (continuation, not reversal), with market-before-stock, portfolio-before-trade, and adaptive strategy orchestration.

Adding RE-001 lets the organization:

- Validate continuation-specific decision quality under REDS governance.
- Compare a philosophy-pure engine against the existing multi-factor composite engine.
- Build the Recommendation Lab multi-engine capability without freezing or rewriting production.

### Business goals

1. Capture high-quality trend continuation opportunities with capital preservation first.
2. Standardize engine outputs as Recommendation Decision Objects for fair comparison.
3. Reuse Shared Core capabilities already present in the application.
4. Keep production advisory behavior stable during lab validation.
5. Enable paper trading and experiment evaluation as the path to any future promotion.

### Expected outcome

- RE-001 runs as an **additional** lab engine on scan/analysis pathways.
- Operators can explain, compare, paper-trade, and experiment on RE-001 decisions.
- Production scanner shortlists and dashboards continue to use the existing recommendation engine until explicit promotion.
- The platform gains a reusable engine-registration pattern for future RE-00x engines.

---

## 2. Business Scope

### Business capability

Institutional trend-continuation recommendation generation inside the Recommendation Lab, governed by REDS, orchestrating primary continuation strategies with supporting evidence and validation, producing standardized BUY/WATCH/REJECT decisions.

### Business value

| Value | Description |
| ----- | ----------- |
| Focus | Pure continuation philosophy vs multi-factor composite noise |
| Safety | Capital preservation via regime and portfolio gates |
| Comparability | Fair engine comparison under shared decision objects |
| Explainability | Strategy ownership and evidence trails for human review |
| Evolution | First concrete multi-engine Lab member without redesigning the app |

### User workflow

1. Market data and scanner shortlist run as today.
2. Production recommendation is computed as today.
3. When enabled, RE-001 evaluates eligible symbols using shared context + continuation orchestration.
4. Operator reviews RE-001 (and production) on lab/detail surfaces.
5. Operator may paper-trade RE-001 ideas with provenance.
6. Experiment/analytics accumulate evidence for promotion review.

### Recommendation workflow (RE-001)

Market Context → Universe (NIFTY500 stage inputs) → Eligibility (Bull Stock Filter + stricter engine filters) → Strategy Selection/Activation → Technical Confirmation → Supporting Evidence → Risk Validation → Portfolio Validation → Confidence → Decision (BUY/WATCH/REJECT) → Explanation → Decision Object → Lab persistence / orchestrator consumption.

### Expected behaviour

- Bull: higher participation in healthy continuations.
- Sideways: selective, confirmation-heavy, breakout/RS preferred.
- Bear: mostly inactive; exceptional RS leaders only.
- Quality over quantity; profit alone is not success.

---

## 3. Current Architecture Analysis

### Current recommendation pipeline

Production path (as implemented):

1. Universe prioritization and screener stages (`ScreenerService` / `OrchestratorAgent`).
2. Market data load (FYERS / candle cache / authoritative store paths).
3. Technical analysis bulk scoring (`TechnicalAnalysisService`).
4. Parallel news, fundamentals, backtest agents.
5. Sector RS / market permission challenger paths.
6. `RecommendationAgent` → `LLMService` (reasoning) + `RecommendationService.build` (composite score, trade plans, overlays).
7. Final gate / score classification → production `FinalRecommendation`.
8. Persist `AnalysisHistory` (+ shadow_outputs keys for experimental features).
9. Rank and expose BUY/WATCH shortlists via analysis/scanner APIs and frontend.

### Current scanner flow

`ScanExecutionService` / scheduler daily-scan → lock → `OrchestratorAgent` multi-universe stages → shortlist top-N → full analysis → stop at first universe with BUY candidates → persist latest scan / candidates → SSE/API to UI.

### Current AI flow

LLM is used for structured reasoning and sentiment assistance; production label is deterministic score/gate based (platform constraint: no live LLM-owned decisions). RE-001 must preserve this determinism for RecommendationState.

### Current paper trading flow

Paper accounts, orders, positions, market engine fills, gap replay, analytics; `POST /paper-trading/from-recommendation` prefills from recommendation context. RE-001 must plug into provenance-aware prefill without changing fill engine semantics.

### Current analytics / experiment flow

- Analysis history + shadow_outputs telemetry.
- Analytics endpoints (engine health, shadow status, rule governance).
- Governance experiment services, promotion/shadow patterns (FEAT shadow infra).
- Walk-forward and backtest services for validation.

### Where RE-001 integrates

| Layer | Integration posture |
| ----- | ------------------- |
| After production recommendation is resolved per symbol | Run RE-001 in isolated envelope (lab/shadow), similar spirit to existing shadow hooks |
| Shared inputs | Consume already-fetched candles, technical results, regime/breadth/sector, portfolio/risk snapshots |
| Persistence | First-class decisions table for RE-001 Decision Objects + comparison metadata — not overwrite production `recommendation` shortlist field |
| UI | Symbol detail RE-001 section + compact Lab comparison view; retail scanner remains production-driven |
| Paper / EEF | Downstream consumers of Decision Objects via orchestrator/lab APIs |
| Scheduler | Piggyback enabled lab evaluation on existing scan jobs |

RE-001 does **not** replace `RecommendationService` scoring matrix as the production engine in this feature.

---

## 4. Integration Architecture

### Scanner

- Scanner shortlist and stage-stopping rules remain production-driven.
- RE-001 evaluates **only** symbols on the production shortlist / full-analysis set for that run, after production analysis inputs are available; never full-universe RE-001 evaluation in MVP.
- RE-001 never widens production shortlist ownership in lab mode.
- Optional: eligibility pre-filter metrics may be logged for RE-001, but must not change production `matched` / BUY candidate lists in lab mode.

### Recommendation Engine / Lab

- Introduce engine registry concept: Production engine + RE-001.
- RE-001 implements REDS engine responsibilities only: read context, select strategies, evaluate, decide, explain.
- Recommendation Orchestrator responsibilities (collect, paper, backtest, EEF, promotion, production forwarding) remain platform/orchestrator concerns — engines do not call production shortlist writers directly.

### Paper Trading

- Accept RE-001 Decision Objects / provenance on prefill and journal metadata.
- Risk/position lifecycle stays in existing paper trading services.
- Portfolio validation for RE-001 may read paper/portfolio state via shared portfolio capability.

### Analytics

- Extend engine health / lab analytics to segment by EngineID.
- Preserve existing production aggregates.
- Comparison metrics: optional mismatch rate production vs RE-001.

### Dashboard

- Retail scanner dashboard remains production recommendations.
- Symbol detail shows RE-001 decision, strategy, and evidence when present.
- Compact Recommendation Lab comparison view provides scan-level production vs RE-001 tables.
- Optional subtle badge when lab data exists; no forced redesign of SwingDecisionDashboard primary UX.

### APIs

- Reuse analysis/scanner read models; add lab endpoints or optional fields that are backward compatible.
- Production response contracts for shortlist fields remain stable.

### Database

- Reuse `analysis_history` for production recommendations; optional foreign keys/links from lab decisions to analysis/scan runs.
- **MVP**: first-class decisions table is the system of record for RE-001 Decision Objects (see §8).

### Scheduler

- Existing scan-related jobs may invoke lab evaluation when flags enabled.
- No new mandatory cron that places live trades.
- Failures in RE-001 must not fail the scheduled production scan job outcome.

### Experiment Framework

- Register RE-001 runs under experiment/shadow governance patterns.
- Support lifecycle: research → lab shadow → paper → EEF evaluation → promotion review.
- Auto-promotion to production shortlist is **out of scope**.

---

## 5. Feature Scope

### In Scope

- RE-001 engine registration and versioning.
- Lab/shadow execution path integrated with existing analysis orchestration (shortlist / full-analysis symbols only).
- REDS Decision Object emission for RE-001.
- Strategy orchestration for four primary families + supporting + validation layers (business rules from Doc 02).
- Shared service consumption mapping (SCS → existing modules).
- Persistence of lab decisions and production comparison records.
- Operator-visible comparison and explanation (symbol detail RE-001 section + compact Lab comparison view).
- Paper-trade provenance from RE-001.
- Analytics counters for RE-001 health.
- Feature flags / stage configuration.
- Regression protection for production recommendation path.
- Documentation of Bull Stock Filter and regime participation behaviour.

### Out of Scope

- Replacing or redesigning the production composite recommendation engine.
- Auto-promotion of RE-001 to production shortlist authority.
- Live broker execution.
- RE-002…RE-007 implementation.
- Mean reversion / event / gap / news-primary / earnings / short / pure intraday engines.
- Full Strategy Library product UI (beyond what RE-001 needs to name/select strategies).
- Full multi-engine Recommendation Lab product console (engines registry marketplace UI); MVP is compact comparison only.
- New shared libraries or new REDS architecture layers (REDS locked).
- Rewriting market data, scanner vectorization, or paper market engine.
- Publishing RE-001 Documents 03–05 (external authoring); this spec only consumes available docs.

### Must Not Change

- Production BUY/WATCH/REJECT classification ownership for scanner shortlists (until future promotion feature).
- Existing score thresholds and production gate semantics (unless untouched by this work).
- Auth session model, advisory disclaimer, long-only constraint.
- Paper fill/replay engine behaviour unrelated to provenance metadata.
- REDS Decision Object field set (must not invent alternate state machines).

### Must Reuse

- Market data / candle infrastructure.
- Technical analysis indicators and scores.
- Screener shortlist generation.
- News/events, fundamentals (as shared context only; not RE-001 primary philosophy).
- Sector RS / breadth / regime services.
- Backtest and walk-forward infrastructure.
- Paper trading, portfolio/risk settings.
- Analytics, logging, audit, feature permissions, configuration, caching, scheduler locks.
- Shadow/experiment isolation patterns for non-production evaluation.

---

## 6. Frontend Impact

### Pages affected

| Page / route | Impact |
| ------------ | ------ |
| Scanner (`/scanner`, App scanner orchestration) | Optional lab indicator; production tables unchanged by default |
| Symbol / stock detail (`StockDetailPanel`, analysis detail) | Show RE-001 decision, strategy, evidence when present |
| Paper Desk (`/paper`) | Provenance when order originated from RE-001 |
| Performance / analytics views | Optional RE-001 segment or link |
| Admin / diagnostics / central command | Flags, engine stage, lab health (supporting, not the only review path) |
| Compact Recommendation Lab | **Required MVP**: scan-level production vs RE-001 comparison (new tab or lightweight page) |

### Components affected

- `CandidateTable` / `AllAnalyzedStocksTable` — optional engine column or filter (non-breaking).
- `StockDetailPanel` — **required** RE-001 section: state, strategy, evidence, vs production.
- Compact Lab comparison component/page — scan-level side-by-side states.
- `AnalyticsPanel` / daily analytics — optional RE-001 metrics cards.
- `OrderDrawer` / paper prefill — engine provenance display.
- `navConfig` — feature-gated entry to compact Lab comparison view (visible to Admin and Trader when permission enabled).
- Feature catalog defaults — feature key for recommendation lab / RE-001 visibility; default allows Admin and Trader when active (permission can still disable).

### New pages

- **MVP required**: Compact Recommendation Lab comparison view (tab or lightweight page) — production vs RE-001 for a completed scan; not a full multi-engine product console.
- Full engines-registry Lab product page is **out of MVP** (defer to later multi-engine work).

### Modified pages

- Symbol/analysis detail: RE-001 section required when lab data exists.
- Scanner and paper flows as above; retail primary nav IA gains only a feature-gated Lab entry if needed.

### Navigation impact

- Feature-gated `Recommendation Lab` (or equivalent) entry for the compact comparison view.
- Must not remove or rename Markets / Scanner / Paper / Performance primary items.

### Dashboard impact

- Production BUY/WATCH summary cards remain production-sourced.
- Lab comparison and RE-001 detail sections must be clearly labeled experimental/lab to avoid operator confusion.

---

## 7. Backend Impact

### Services reused (no parallel reimplementation)

| REDS / need | Existing capability (examples) |
| ----------- | ------------------------------ |
| Market data | `market_data_service`, `fyers_service`, candle store / authoritative store |
| Technical indicators | `technical_analysis_service`, technical agent |
| Screener / universe | `screener_service`, `universe_service`, orchestrator stages |
| Regime | `market_permission_service`, `feat004_regime_overlay` |
| Breadth | `market_breadth` |
| Sector / RS | `sector_rs_service`, `sector_strength` |
| News / events | `news_service`, news agent, `event_calendar_service` |
| Fundamentals (context only) | fundamental analysis agent |
| Backtest | `backtest_service`, backtest agent, walk-forward |
| Paper / portfolio | `paper_trading_service`, workstation risk settings |
| Ranking | `ranking_service` (production lists) |
| LLM explainability assist | `llm_service` |
| Persistence | orchestrator persist paths, analysis history |
| Shadow / experiment | `shadow_executor*`, governance experiment services |
| Analytics | analytics routes/services, daily analytics |
| Config / flags | `settings` feature blocks |
| Logging / audit | logger, db_logger, audit services |
| Locks / scheduler | scan execution lock, APScheduler jobs |

### Services modified

- Orchestration path (`OrchestratorAgent` or equivalent scan/full analysis coordinator): isolated RE-001 invocation after production decision.
- Persistence layer: store Decision Objects / lab comparison without clobbering production recommendation field semantics.
- Paper prefill path: accept engine provenance.
- Analytics aggregation: optional EngineID dimension.
- Settings: RE-001 flags and stage.

### New services / modules (logical)

- RE-001 engine module (strategy orchestration + decision builder) implementing engine responsibilities only.
- Engine registry / loader (RE-001 registration; production engine remains default authority).
- Decision Object mapper (RE-001 internal result → REDS Decision Object; adapter to UI/API models).
- Optional lab query service for comparison reads.

These are **bounded additions**, not a second trading platform.

### New interfaces

- Engine evaluate contract: inputs = shared execution context; output = Recommendation Decision Object.
- Lab comparison query contract.
- Configuration contract for stage and enablement.

### Dependency changes

- Prefer zero new third-party dependencies.
- If any dependency is required, it must be justified in planning; default is none.

---

## 8. Database Impact

### Tables reused

- `analysis_history` (production recommendation fields remain authoritative for current shortlist consumers; may be referenced by lab decisions, not replaced by them).
- `shadow_outputs` JSONB remains for **other** experimental shadow features; it is **not** the system of record for RE-001 Decision Objects.
- `watched_stocks`, market data candle tables.
- Paper trading tables for orders/positions (provenance metadata fields or JSON notes as available).
- Experiment / governance tables where already present for experiment lifecycle.
- Scan snapshot / latest scan tables (production scan results unchanged in meaning).

### New tables (required for MVP)

| Logical store | Purpose |
| ------------- | ------- |
| `recommendation_engine_decisions` (required) | First-class RE-001 Decision Objects by engine_id, symbol, scan/run id, plus comparison metadata vs production when available |
| `recommendation_engine_registry` (optional) | Registered engines, versions, stages — may be config-only for MVP if decisions table alone is sufficient |

### Schema modifications

- Additive only: new decisions table (and optional registry); optional FK/link columns to analysis history or scan run identity.
- No destructive renames of production recommendation columns.
- No change to meaning of `analysis_history.recommendation` as production label without a dedicated promotion feature.
- Do not rely on namespaced JSON alone as the RE-001 decision system of record.

### Indexes

- Required on decisions table: `(engine_id, created_at)`, `(symbol, created_at)`, `(scan_run_id)` or equivalent run linkage, `(recommendation_state)`.

### Migration requirements

- Forward-only Alembic migration if new tables/columns.
- Deploy-safe defaults (NULL / empty) so old app versions do not break.
- Backfill not required for historical production rows.

---

## 9. API Impact

### Existing APIs reused

- `POST /analysis/screener/full`, `POST /analysis/full`, technical/news/backtest/final-recommendation paths.
- Latest scan / scanner restore endpoints.
- `POST /paper-trading/from-recommendation` and paper order APIs.
- `GET /api/v1/analytics/engine-health`, shadow-status, rule-governance (extend carefully).
- Auth and feature-permission endpoints.

### New APIs required (logical)

| Capability | Notes |
| ---------- | ----- |
| List registered engines | Lab registry read |
| Get RE-001 decisions for scan/symbol | Lab detail |
| Get production vs RE-001 comparison | Lab compare |
| Admin/config read of RE-001 stage | Operational |

MVP may expose lab fields on existing analysis payloads as **optional** properties instead of new routes, provided backward compatibility holds.

### Modified APIs

- Analysis/screener responses: optional non-breaking lab block (`lab_engines.RE-001` or similar).
- Paper prefill: optional engine provenance fields.
- Analytics health: optional per-engine breakdown.

### Backward compatibility

- Clients that ignore unknown fields continue to work.
- Production arrays `buy_candidate_symbols` / `watch_candidate_symbols` remain production-engine-driven in lab mode.
- No removal of existing fields.
- No change to auth cookie contract.

---

## 10. Recommendation Pipeline Integration

### How RE-001 enters the flow

```
Existing scan / full analysis
        ↓
Shared inputs assembled (candles, TA, news, fund, BT, regime, sector, breadth)
        ↓
Production RecommendationAgent / RecommendationService → production FinalRecommendation
        ↓
Final production gate / shortlist classification (UNCHANGED in lab mode)
        ↓
[If RE-001 enabled] Build Lab Execution Context (immutable snapshot)
        ↓
RE-001: eligibility → strategy activation → confirm → support → validate → decide → explain
        ↓
Recommendation Decision Object (EngineID=RE-001)
        ↓
Persist lab decision + optional comparison vs production
        ↓
Return production response (+ optional lab payload)
```

### Input

- Symbol, mode (swing), OHLCV, technical results.
- Market regime / permission, breadth, sector RS/leadership.
- Liquidity and quality flags.
- Portfolio / risk snapshot (paper or configured risk policy).
- Strategy eligibility metadata (SCM-like config for continuation families).
- Production recommendation snapshot (for comparison only; not a required input to RE-001 logic).

### Processing

1. Market context interpretation (Bull/Sideways/Bear mapping). If market regime/context is missing or unusable → Decision Object REJECT with `missing_market_context` (or equivalent); stop further strategy activation for that symbol.
2. Bull Stock Filter + RE-001 stricter filters.
3. Activate eligible primary strategies by regime/objective/style.
4. Evaluate candidates; apply supporting strategies.
5. Risk + portfolio validation.
6. Rank/conflict-resolve to one primary strategy.
7. Assign BUY/WATCH/REJECT + confidence.
8. Build explanation and Decision Object.

### Output

- REDS Recommendation Decision Object.
- Optional trade plan linkage: reuse existing plan builder outputs when validation passes, or lab-specific plan fields mapped into paper prefill without changing production plan meaning.

### Decision Object

Must include REDS §9 fields (see FR-004). RecommendationState limited to BUY/WATCH/REJECT.

### Persistence

- First-class decisions table is the system of record for RE-001 Decision Objects and comparison metadata.
- Production `recommendation` column remains production engine output.

### Analytics

- Increment RE-001 counters; record mismatches; expose via analytics/lab queries.
- Situation tagging may include continuation-related tags for research, without changing production labels.

---

## 11. Shared Component Reuse

| Domain | Reuse target | RE-001 may not |
| ------ | ------------ | -------------- |
| Market Data | Existing fetch/cache/store | Own broker client |
| Technical Analysis | Indicator scores, HH/HL, Supertrend, MAs, RSI, MACD, volume | Fork indicator engine |
| News | Shared sentiment as context only | News-primary strategy engine |
| Fundamental Analysis | Optional context | Fundamental-first selection |
| Backtesting | Validate continuation rules historically | Private backtest stack |
| Paper Trading | Orders, fills, analytics | Separate paper ledger |
| Analytics | Engine health patterns | Shadow-only custom DB access hacks in UI |
| Scheduler | Existing scan jobs | Unlocked parallel full-universe storms |
| Portfolio / Risk | Paper risk settings / portfolio checks | Silent ignore of portfolio heat |
| Logging | Structured logs | Unstructured-only diagnostics |
| Configuration | Settings + feature flags | Hardcoded secret stages |
| Caching | Candle/response caches | Bypass cache integrity rules |
| Experiment / Shadow | Isolation envelope | Write into production shortlist fields |
| Auth / Permissions | Existing guards; Admin+Trader with lab feature flag | Open lab without auth; admin-only lockout of traders for MVP |

---

## 12. Configuration

### Feature Flags

| Flag / setting | Purpose | Default |
| -------------- | ------- | ------- |
| `re001_enabled` | Master switch | `false` |
| `re001_stage` | Canonical: `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` (`ACTIVE` reserved/out of scope) | `OFF` |
| `re001_version` | Engine version string | `1.0` |
| `re001_persist_decisions` | Persist Decision Objects | `true` when enabled |
| `re001_compare_with_production` | Store comparison records | `true` when enabled |
| `re001_timeout_ms` | Isolation timeout | planning default; fail-open for production / fail closed for RE-001 BUY path |
| `re001_ui_enabled` | Lab UI surfaces | `false` or tied to feature permission `recommendation_lab` |

### Engine Registration

- Registry entry: `{ engine_id: "RE-001", name: "Trend Continuation Recommendation Engine", version, stage, enabled }`.
- Production engine remains separately identified and authoritative for shortlists in this feature.

### Environment Variables

- Mirror settings via env aliases consistent with existing `Settings` style (e.g., `RE001_ENABLED`, `RE001_STAGE`).
- No secrets unique to RE-001 beyond existing data providers.

### Configuration files

- Prefer `settings` feature block pattern used by FEAT-004/007/008/shadow.
- Strategy priority tables per regime may live in config/YAML/JSON loaded by the engine module (documented in plan phase).

### Runtime settings

- Hot toggle via settings/admin where platform already supports safe runtime flags; otherwise deploy-time env is acceptable for MVP.
- Stage transitions to anything that affects production shortlists require governance approval (future feature).

---

## 13. Validation Rules

### Business validation

- Long-only, swing, NIFTY500, advisory-only.
- States ∈ {BUY, WATCH, REJECT}.
- Primary strategy required for BUY/WATCH.
- Portfolio-before-trade and risk-before-recommend enforced.
- Regime participation rules applied.
- Missing/unusable market regime → REJECT with explicit reason code (never BUY; no default regime).
- Excluded philosophies not implemented as primary paths.

### Technical validation

- Inputs present or explicit abstain/REJECT path.
- Deterministic decision for fixed inputs/version.
- Isolation: exceptions do not fail production.
- Backward compatible API responses.
- Migrations additive and reversible in the forward-only sense (deploy safe).

### Recommendation validation

- Decision Object completeness (FR-004).
- Evidence and explanation present for human review.
- Conflict resolution yields single primary strategy.
- Confidence consistent with supporting/validation outcomes (no BUY with failed hard validation).

### Integration validation

- Production shortlist invariance tests (SC-001).
- Flag OFF ⇒ no RE-001 artefacts.
- Paper provenance tests.
- Analytics segmentation tests.
- Permission tests for lab surfaces (Admin + Trader with feature flag).
- Missing market regime ⇒ REJECT with reason code tests (FR-025).
- Evaluation-set tests: non-shortlisted symbols not evaluated.

---

## 14. Acceptance Criteria

1. RE-001 can be enabled in LAB_SHADOW and produces Decision Objects for shortlisted symbols without changing production shortlists.
2. Decision Objects include all mandatory REDS fields and valid states only.
3. Missing/unusable market regime yields REJECT with explicit reason code (never BUY; no default regime).
3a. Missing portfolio context yields no BUY with reason `portfolio_context_unavailable`.
3b. Paper prefill uses RE-001 trade guidance when complete else production trade_plans with RE-001 provenance.
4. Strategy orchestration records primary vs supporting vs validation outcomes.
5. Bull/Sideways/Bear participation differences are demonstrable in verification scenarios.
6. Operators can compare production vs RE-001 for the same symbol/scan via symbol detail + compact Lab view.
7. Paper prefill/order path can retain RE-001 provenance.
8. Analytics can report RE-001 decision counts by state for a rolling window.
9. Feature flag OFF removes RE-001 execution side effects.
10. Existing regression suite for production recommendation classification remains green.
11. No live order placement path introduced.
12. Documentation in feature folder states SCS mapping and non-goals clearly.
13. Failures in RE-001 are logged and countable without aborting production scan success.
14. RE-001 evaluates only shortlist/full-analysis symbols in MVP.

---

## 15. Regression Requirements

The following must never break:

| Area | Protection |
| ---- | ---------- |
| Existing Recommendation Engine | Score thresholds, gate semantics, production labels, trade plan generation for production path |
| Scanner | Stage order, shortlist caps, stage-stopping, latest scan persistence meaning |
| Paper Trading | Account isolation, order/position lifecycle, market engine fills, gap replay |
| Analytics | Existing engine-health aggregates still correct for production |
| Dashboard | Retail BUY/WATCH cards and scanner tables remain production-correct |
| Scheduler | Scan locks, job success criteria not tied to RE-001 |
| Auth / RBAC / feature guards | Existing permissions continue to enforce access |
| Shadow features | Existing shadow_outputs keys for other features remain intact |
| API clients | Unknown field tolerance; no removed fields |

Mandatory regression evidence: production invariance tests with RE-001 on/off; scanner smoke; paper smoke; analytics smoke.

---

## 16. Risk Assessment

| Severity | Risk | Mitigation |
| -------- | ---- | ---------- |
| **Critical** | RE-001 accidentally overwrites production shortlist labels | Hard separation of stores/fields; lab mode cannot write production recommendation authority; invariance tests |
| **Critical** | Production scan fails due to RE-001 exception/timeout | Isolated try/except + timeout; fail-open for production |
| **High** | Operator confuses lab BUY with production BUY | Clear UI labeling; production cards unchanged; provenance badges |
| **High** | Incomplete Decision Object breaks EEF/compare | Schema validation before persist; reject incomplete objects |
| **High** | Regime mapping wrong → overtrading in bear | Explicit mapping table + bear-regime verification set (SC-006); missing regime → REJECT not default Sideways |
| **Medium** | Performance regression on scan latency | **MVP evaluates shortlist only**; budget timeout; async/isolated execution patterns already used for shadow work |
| **Medium** | Decisions table migration complexity | Additive schema only; deploy-safe defaults; no production column rewrites |
| **Medium** | Strategy Library metadata immature | Start with engine-local strategy descriptors conforming to SCM shape |
| **Low** | Doc 03–05 absent causes parameter ambiguity | Assumptions section + defaults conservative (more REJECT/WATCH than BUY) |
| **Low** | Extra UI nav clutter | Feature-gate Lab nav; default off for pure retail |

---

## 17. Implementation Readiness

Dependencies before coding begins:

1. Agreement that production engine remains shortlist authority for this feature (no silent promotion).
2. RE-001 Docs 01–02 + REDS v1.0 accepted as business authority.
3. Documented mapping: existing regime labels → Bull/Sideways/Bear for orchestration (planning detail; missing regime → REJECT per Session 2026-08-03).
4. ~~Decision on MVP storage~~ — **Resolved**: first-class decisions table (Session 2026-08-03).
5. ~~Decision on MVP UI~~ — **Resolved**: hybrid symbol detail + compact Lab comparison view (Session 2026-08-03).
5a. ~~MVP evaluation set~~ — **Resolved**: production shortlist / full-analysis symbols only (Session 2026-08-03).
6. Feature flag names and default stage confirmed.
7. Paper provenance field strategy confirmed (column vs metadata JSON).
8. Timeout/isolation budget for RE-001 per symbol/scan.
9. Test fixtures for bull/sideways/bear continuation scenarios.
10. Analytics contract for per-engine counts.
11. Confirmation that no RE-001 Doc 03 hard parameters are required for orchestration MVP (or supply Doc 03 if thresholds must be frozen).
12. ~~Access control: which roles see lab data~~ — **Resolved**: Admin + Trader with lab feature permission (Session 2026-08-03).
13. Baseline production recommendation regression suite identified and runnable.
14. Scan locking behaviour understood (no second full unlocked universe scan for RE-001).

---

## 18. Definition of Done

RE-001 integration is complete when:

1. All P1 user stories pass acceptance scenarios.
2. Functional requirements FR-001–FR-027 are satisfied or explicitly deferred with stakeholder sign-off (none deferred for P1 isolation/decision object/compare).
3. Success criteria SC-001–SC-008 verified with recorded evidence.
4. Production invariance demonstrated (RE-001 on vs off).
5. Lab Decision Objects persisted in the first-class decisions table and reviewable via symbol detail + compact Lab comparison.
6. Paper provenance path verified.
7. Feature flags control execution.
8. Regression suites for recommendation, scanner, paper, and analytics remain green.
9. No production redesign residual (no replaced composite engine, no live trading).
10. Spec quality checklist complete; feature ready for `/speckit-plan` and subsequent tasks.
11. Operators can answer: “What did RE-001 decide, why, and how does it differ from production?” without DB consoles.
12. Governance path for future promotion is documented as **manual / future feature**, not auto-enabled.

---

## Traceability

| Source | Consumption in this spec |
| ------ | ------------------------ |
| REDS v1.0 | Pipeline, Decision Object, SCS, states, orchestrator boundaries, validation lifecycle |
| RE-001 Doc 01 | Mission, philosophy, scope, invariants, regime participation, success criteria |
| RE-001 Doc 02 | Strategy layers, orchestration, activation, priority, conflict resolution, adaptive behaviour |
| Existing app | Integration points, reuse inventory, regression surface, brownfield constraints |

---

## Notes for Planning (`/speckit-plan`)

- Prefer adapter + engine module over invasive rewrite of `RecommendationService`.
- Mirror proven shadow isolation patterns for lab execution.
- Keep retail UX production-first; lab clearly labeled.
- Treat missing Doc 03 parameters as conservative defaults to be tightened later without changing architecture.
- Locked by clarify (2026-08-03): first-class decisions table; hybrid UI; Admin+Trader visibility; shortlist-only evaluation; missing regime → REJECT.
