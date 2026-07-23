# Implementation Plan: Validation, Interaction Analysis, Point-Budget Rebalancing & Controlled Promotion

**Branch**: `015-shadow-promotion-rebalance` | **Date**: 2026-07-22 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/015-shadow-promotion-rebalance/spec.md)  
**Input**: Feature specification from `specs/015-shadow-promotion-rebalance/spec.md`

---

## Summary

This feature delivers the evaluation, matrix rebalancing, and controlled sequential promotion process for the two candidate features built in Sprint 7 (**Sentiment Time-Decay FEAT-018** and **Market Breadth FEAT-016**). It implements an offline A/B attribution report generator, feature correlation check, a strict 100-point rebalanced scoring matrix configuration, and a two-stage sequential promotion workflow utilizing the existing `RuleManager` and kill-switch mechanism.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy (PostgreSQL/SQLite), Pydantic v2, Pandas, asyncio  
**Storage**: PostgreSQL `analysis_history` (JSONB `shadow_outputs`), `rule_states.json`  
**Testing**: pytest  
**Target Platform**: Windows / Linux server  
**Project Type**: Web service (FastAPI backend + CLI governance tools)  
**Performance Goals**: Kill-switch lookup $<1\text{ms}$, matrix rebalancing sum check $0\text{ms}$ overhead  
**Constraints**: Zero impact on live scoring when in shadow mode; scoring matrix MUST strictly sum to exactly 100.0 points; all experimental writes use SAVEPOINT isolation.  
**Scale/Scope**: Shadow dataset evaluation across historical analysis records with situation tags.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Pure Functions**: Attribution calculation, correlation analysis, and matrix sum validation are implemented as pure, deterministic functions. *(Pass)*
- **RuleManager Governance**: Feature promotions gated behind `RuleManager().is_active_in_production(rule_id)` with Instant Kill-Switch fallback to baseline behavior. *(Pass)*
- **Test-First**: Unit and integration tests written and passing prior to completing feature delivery. *(Pass)*
- **No Machine Learning**: Deterministic scoring formulas and standard Pearson/Spearman statistical correlation. *(Pass)*
- **Matrix Integrity**: Strict validation ensuring scoring weights sum to exactly 100.0 points. *(Pass)*

---

## Project Structure

### Documentation (this feature)

```text
specs/015-shadow-promotion-rebalance/
├── plan.md              # Implementation plan (this file)
├── research.md          # Technical decisions & ablation methodology
├── data-model.md        # Pydantic schemas for attribution, matrix config & state records
├── quickstart.md        # Runnable validation scenarios & commands
├── contracts/           # Governance API contracts
│   └── promotion_api.md # REST endpoints for attribution report & promotion/kill actions
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── schemas/
│   │   ├── shadow_telemetry.py        # Attribution and matrix schemas
│   │   └── scoring_config.py          # 100-point ScoringMatrixConfig schema
│   ├── services/
│   │   ├── attribution_validation_service.py # Pure 4-way A/B ablation & correlation analysis
│   │   ├── scoring_matrix_service.py  # 100-point rebalanced matrix manager
│   │   ├── recommendation_service.py  # Production scoring path with Stage 1 & Stage 2 gates
│   │   └── shadow_executor.py         # Shadow execution routines
│   ├── governance/
│   │   ├── rule_manager.py            # Rule states ("sentiment_decay", "market_breadth")
│   │   └── experiment_cli.py          # CLI commands for attribution report & promotion
│   └── routes/
│       └── governance.py              # Governance API endpoints
└── tests/
    ├── unit/
    │   ├── test_attribution_validation.py # Unit tests for ablation math & correlation
    │   └── test_scoring_matrix_rebalance.py # Unit tests for 100-point sum invariant
    └── integration/
        └── test_sequential_promotion.py   # Integration tests for Stage 1, Stage 2, and Kill-Switch
```

**Structure Decision**: Single Python project structure in `backend/` consistent with existing architecture.

---

## Technical Decisions Breakdown

### 1. Attribution & Validation Report (FEAT-019 / FEAT-017 / FEAT-027)
- **Data Query**: Query `AnalysisHistory` records joining with `WatchedStock` where `shadow_outputs` contains `sentiment_decay` and `market_breadth` over the requested window (default 30 days).
- **4-Way Ablation**: Replays baseline, decay-only, breadth-only, and combined configurations for each record.
- **Metrics**: Computes false-positive rate, win rate, precision, signal accuracy, and alpha attribution % per situation tag (`GOOD_NEWS_CATALYST`, `MARKET_REGIME`).
- **Sample Safeguard**: Minimum sample size of 30 records required; otherwise outputs `INSUFFICIENT_DATA` and enforces `No-Go`.

### 2. Feature Interaction / Redundancy Check
- **Correlation Calculation**: Computes Pearson correlation coefficient ($r$) between Sentiment Time-Decay delta and Market Breadth soft contribution.
- **Decision Thresholds**:
  - $r < 0.70 \to$ **COMPLEMENTARY** (Promote Both).
  - $0.70 \le r \le 0.85 \to$ **MODERATE_OVERLAP** (Promote Decay first, defer Breadth).
  - $r > 0.85 \to$ **REDUNDANT** (Promote Decay only, reject Breadth).
- **Audit Persistence**: Writes audit record via `AuditTrailManager` and exports JSON report.

### 3. Point-Budget Rebalancing (FEAT-027)
- **Exact New Allocation**: Technical 35, Sentiment 25, Fundamental 15, Volume 15, Market Breadth 10 = **100 Points Total**.
- **Minimum Disruption Rationale**: Fundamental score has the highest static slack for short-term swing/day scans. Deducting 10 points from Fundamental (25 $\to$ 15) and allocating 10 points to Market Breadth preserves Technical (35) and Volume (15) responsiveness.
- **Matrix Invariant Enforcement**: `ScoringMatrixConfig` Pydantic validator asserts `sum == 100.0`. Any invalid matrix raises a hard `ValueError`.

### 4. Sequential Promotion to Production
- **Stage 1 (Decay)**: Promotes `"sentiment_decay"`. When active, `NewsAnalysisAgent` and `RecommendationService` substitute decay-adjusted sentiment score into live recommendation calculation while Market Breadth remains in shadow mode.
- **Stage 2 (Breadth)**: Promotes `"market_breadth"`. When active, `RecommendationService` applies Market Breadth soft score contribution and rebalanced 100-point matrix weights.
- **Kill-Switch**: Disabling either rule in `RuleManager` (`"disabled"`) immediately reverts scoring to baseline behavior in $<1\text{ms}$.

### 5. Testing & Safety Strategy
- **Matrix Invariant Unit Test**: Asserts sum of weights strictly equals 100.0.
- **Kill-Switch Integration Test**: Tests state transitions (`shadow` $\to$ `production` $\to$ `disabled`) and verifies exact score identity with baseline upon kill.
- **Baseline Comparison Test**: Compares post-promotion output against `baseline_v1.0.json`.
- **Rollback Safeguard**: If post-promotion false-positive rate increases by $>2.0\%$, automatic kill-switch trigger via `RuleManager`.

---

## Complexity Tracking

*No constitution violations present. Design follows minimal disruption, pure function design, and existing RuleManager singleton patterns.*
