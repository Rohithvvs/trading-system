# Contract: RE-001 Recommendation Decision Object

**Feature**: `029-re001-trend-continuation`  
**Status**: Planning contract (not implementation)  
**Alignment**: REDS v1.0 §9 + spec FR-004 / FR-025

---

## Purpose

Canonical output of RE-001 evaluation. All consumers (persistence, lab API, UI, paper provenance, analytics) MUST accept this shape.

---

## Recommendation states

Allowed values only:

- `BUY`
- `WATCH`
- `REJECT`

No other states.

---

## Required fields

| Field | Type (logical) | Rules |
| ----- | -------------- | ----- |
| recommendation_id | string | Unique per evaluation |
| engine_id | string | Constant `RE-001` |
| engine_version | string | Non-empty (e.g. `1.0`) |
| market_regime | string | `Bull` \| `Sideways` \| `Bear` \| `UNKNOWN` |
| trading_objective | string | Non-empty |
| trading_style | string | Long-only swing intent |
| strategy_family | string \| null | Required when state is BUY or WATCH |
| strategy_name | string \| null | Required when state is BUY or WATCH |
| recommendation_state | string | BUY \| WATCH \| REJECT |
| confidence_score | number | Finite |
| risk_profile | object \| string | Present |
| portfolio_decision | object \| string | Present |
| evidence | object | Structured; non-empty for success path |
| explanation | object \| string | Human-readable rationale |
| timestamp | datetime | UTC |
| reason_codes | string[] | Includes `missing_market_context` or `portfolio_context_unavailable` when applicable |
| trade_guidance | object \| null | Optional entry/SL/target guidance for paper prefill (see below) |

---

## Trade guidance (optional but preferred for BUY)

| Field | Type | Rules |
| ----- | ---- | ----- |
| entry_low / entry_high | number | > 0 and ordered when present |
| stop_loss | number | > 0 when present |
| target_1 | number | > 0 when present |
| risk_reward_ratio | number | optional |
| complete | boolean | true only when entry, SL, and target_1 usable |

**Paper prefill rule (FR-015)**: If `trade_guidance.complete` is true, paper prefill uses it; otherwise fall back to production `trade_plans` for the same symbol/scan. Provenance always identifies RE-001 when the operator originated from a lab decision.

**Population**: Prefer reuse of existing plan-building helpers / production plan snapshot already in LabExecutionContext — do not invent a second ATR stack unless required.

---

## Strategy trace (required under evidence or sibling object)

| Field | Description |
| ----- | ----------- |
| primary_strategy | Selected owner |
| supporting_strategies | List of confirmations |
| rejected_strategies | List with reasons |
| validation_results | Regime, liquidity, risk, portfolio, policy, bull_stock_filter |

---

## Invariants

1. Missing/unusable market regime ⇒ `recommendation_state = REJECT`, `market_regime = UNKNOWN` (or equivalent), reason `missing_market_context`.
2. Supporting strategies never alone produce BUY.
3. Validation hard-fail never yields BUY.
4. Deterministic for fixed inputs + version + config.
5. LLM text MUST NOT be the sole determinant of `recommendation_state`.
6. Missing portfolio/risk snapshot ⇒ no BUY; reason `portfolio_context_unavailable`.

---

## Comparison extension (lab)

Optional fields when production snapshot exists:

| Field | Description |
| ----- | ----------- |
| production_action | Production BUY/WATCH/REJECT |
| production_score | Production composite score if available |
| is_mismatch | production_action ≠ recommendation_state |

---

## Non-goals

- This contract does not replace production `FinalRecommendation` schema for shortlist ownership.
- This contract does not define HTTP transport (see lab API contract).
