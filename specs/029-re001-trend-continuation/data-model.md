# Data Model: RE-001 Trend Continuation Integration

**Feature**: `029-re001-trend-continuation`  
**Date**: 2026-08-03  
**Source**: [spec.md](./spec.md) Key Entities + Clarifications  
**Note**: Logical model only — no SQL DDL, no migration scripts, no ORM code.

---

## 1. Entity Overview

```text
RecommendationEngineRegistration (config/logical)
        │
        ▼
EngineDecisionRecord  1──*  (optional link)  AnalysisHistory (production)
        │                         │
        │                         └── production action/score comparison
        │
        ├── EvidencePayload (embedded/JSON)
        ├── ExplanationPayload (embedded/JSON)
        ├── ValidationResultSet (embedded/JSON)
        └── StrategyTrace (embedded/JSON)

ScanRunIdentity (logical) 1──* EngineDecisionRecord
PaperOrder / Prefill (existing) *── optional provenance → EngineDecisionRecord
```

---

## 2. Entities

### 2.1 RecommendationEngineRegistration

Logical/config entity (may be settings-only in MVP).

| Attribute | Type (logical) | Required | Notes |
| --------- | -------------- | -------- | ----- |
| engine_id | string | yes | `RE-001` |
| name | string | yes | Trend Continuation Recommendation Engine |
| engine_version | string | yes | e.g. `1.0` |
| stage | enum | yes | Canonical: `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` (`ACTIVE` reserved/out of scope) |
| enabled | boolean | yes | master switch (`re001_enabled`) |
| updated_at | datetime | no | if persisted |

**Uniqueness**: `engine_id` + `engine_version` (or single active version config).

---

### 2.2 EngineDecisionRecord (system of record)

Persisted first-class row for one RE-001 evaluation outcome.

| Attribute | Type (logical) | Required | Notes |
| --------- | -------------- | -------- | ----- |
| recommendation_id | UUID/string | yes | stable Decision Object id |
| engine_id | string | yes | `RE-001` |
| engine_version | string | yes | |
| symbol | string | yes | NSE symbol key as used by app |
| mode | string | yes | e.g. swing |
| scan_run_id | string/int | preferred | Maps to existing completed-scan / latest-scan identity family (FR-027) |
| analysis_history_id | int | optional | FK-like link to production analysis row |
| market_regime | string | yes* | RE-001 bucket or `UNKNOWN` when rejecting for missing context |
| trading_objective | string | yes | REDS field |
| trading_style | string | yes | long-only swing |
| strategy_family | string | conditional | required for BUY/WATCH; may be null on early REJECT |
| strategy_name | string | conditional | primary strategy identity |
| recommendation_state | enum | yes | `BUY` \| `WATCH` \| `REJECT` |
| confidence_score | number | yes | finite |
| risk_profile | object/string | yes | REDS risk profile summary |
| portfolio_decision | object/string | yes | portfolio validation outcome summary |
| evidence | object | yes | structured evidence payload |
| explanation | object/string | yes | human-readable rationale |
| reason_codes | list[string] | yes | e.g. `missing_market_context`, `portfolio_context_unavailable` |
| trade_guidance | object | optional | entry/SL/target payload; `complete` flag for paper prefill |
| production_action | string | optional | comparison: production BUY/WATCH/REJECT |
| production_score | number | optional | comparison |
| is_mismatch | boolean | optional | production_action != recommendation_state |
| score_delta | number | optional | if scores comparable |
| created_at | datetime | yes | UTC |
| evaluation_status | enum | yes | `success` \| `rejected_by_rules` \| `error` \| `timeout` |

\* When missing market context, store regime as `UNKNOWN` (or empty) **and** `recommendation_state=REJECT` with reason code — do not invent Bull/Sideways/Bear.

**Uniqueness (recommended)**: one successful decision per (`engine_id`, `symbol`, `scan_run_id`, `engine_version`) — define upsert vs append policy in tasks (prefer append-with-run-id uniqueness for audit).

**Indexes (logical)**:
- `(engine_id, created_at)`
- `(symbol, created_at)`
- `(scan_run_id)`
- `(recommendation_state)`
- `(analysis_history_id)` if linked

---

### 2.3 Recommendation Decision Object (payload contract)

Not necessarily a separate table — maps onto EngineDecisionRecord columns + JSON payloads. Required fields per REDS / FR-004:

| Field | Notes |
| ----- | ----- |
| RecommendationID | = recommendation_id |
| EngineID | RE-001 |
| EngineVersion | |
| MarketRegime | Bull / Sideways / Bear / UNKNOWN |
| TradingObjective | |
| TradingStyle | |
| StrategyFamily | primary family when applicable |
| StrategyName | primary strategy name |
| RecommendationState | BUY / WATCH / REJECT only |
| ConfidenceScore | |
| RiskProfile | |
| PortfolioDecision | |
| Evidence | |
| Explanation | |
| Timestamp | created_at |

---

### 2.4 StrategyTrace (embedded)

| Attribute | Notes |
| --------- | ----- |
| primary_strategy | selected owner |
| supporting_strategies | list with pass/fail or score contribution |
| rejected_strategies | list with reasons |
| priority_order | as evaluated |
| regime_bucket | Bull/Sideways/Bear used for activation |

---

### 2.5 ValidationResultSet (embedded)

| Check | Outcome |
| ----- | ------- |
| market_regime | pass / fail / missing |
| liquidity | pass / fail |
| risk | pass / fail |
| portfolio | pass / fail |
| policy | pass / fail |
| bull_stock_filter | pass / fail |

Any hard fail → cannot be BUY.

---

### 2.6 Lab Comparison Record

May be columns on EngineDecisionRecord (preferred MVP) rather than separate table.

| Attribute | Notes |
| --------- | ----- |
| production_action | |
| production_score | |
| re001_action | = recommendation_state |
| is_mismatch | |
| compared_at | usually created_at |

---

### 2.7 Production AnalysisHistory (existing — unchanged meaning)

| Attribute | RE-001 interaction |
| --------- | ------------------ |
| recommendation | **Production only** — never overwritten by RE-001 in lab mode |
| shadow_outputs | **Not** RE-001 SoR; leave other features intact |
| id | optional link target from EngineDecisionRecord |

---

### 2.8 Paper provenance (existing entities — extended metadata)

Logical fields on prefill/order (implementation chooses column vs JSON metadata):

| Attribute | Required for SC-005 |
| --------- | ------------------- |
| source_engine_id | yes when from RE-001 |
| source_engine_version | yes when from RE-001 |
| source_recommendation_id | yes when from RE-001 |

---

## 3. State Transitions

### 3.1 Engine stage (configuration)

```text
OFF ──enable──► LAB_SHADOW ──ops──► PAPER_LINKED
 ▲                  │                    │
 └──────── disable ─┴────────────────────┘

LAB_SHADOW and PAPER_LINKED: both evaluate + persist when re001_enabled
PAPER_LINKED: ops signal that paper attribution is intentional validation mode
ACTIVE (production shortlist authority) — OUT OF SCOPE for this feature
```

### 3.2 RecommendationState (decision)

```text
(no state machine across time)
Per evaluation, one of:
  BUY | WATCH | REJECT
Terminal for that recommendation_id.
```

Rules:
- Missing market context → REJECT only.
- Validation hard fail → not BUY.
- Supporting evidence alone cannot create BUY.

### 3.3 Evaluation status

```text
started → success
       → rejected_by_rules (valid Decision Object with REJECT/WATCH)
       → timeout
       → error
```

---

## 4. Validation Rules (data)

1. `recommendation_state` ∈ {BUY, WATCH, REJECT}.
2. `engine_id` for this feature = `RE-001`.
3. BUY/WATCH require primary strategy identity (family + name) except documented edge cases — prefer always recording attempted strategy for WATCH; REJECT for missing context may omit primary.
4. `confidence_score` finite.
5. `evidence` and `explanation` non-empty for successful evaluations.
6. `reason_codes` includes `missing_market_context` or `portfolio_context_unavailable` when applicable.
7. Do not persist a BUY when `evaluation_status` is error/timeout.
8. Production comparison fields optional but required when production snapshot available.
9. BUY requires portfolio validation pass when snapshot present; without snapshot, no BUY.

---

## 5. Relationships Summary

| From | To | Cardinality | Nature |
| ---- | -- | ----------- | ------ |
| EngineDecisionRecord | RecommendationEngineRegistration | N:1 | logical |
| EngineDecisionRecord | AnalysisHistory | N:0..1 | optional link |
| EngineDecisionRecord | Scan run | N:1 | preferred |
| Paper order | EngineDecisionRecord | N:0..1 | provenance |

---

## 6. Non-goals for data model

- No rewrite of production recommendation column.
- No removal of shadow_outputs.
- No full Strategy Library schema product in MVP.
- No SQL scripts in this document.
