# FEAT-009 — Reusable Research Prompt Chain
**Version:** 1.0  
**Date:** 2026-07-13  
**Scope:** Canonical stage-by-stage prompt chain for transforming an idea into an implementable research OS feature. Every stage maps its outputs to the FEAT-008 persistence schema.

---

## Operational Usage

1. **Paste `SHARED_CONTEXT_PACK.md`** as the first message in every new session.
2. **Run each stage in order.** Do not skip stages.
3. **At each stage, persist the output** to the corresponding FEAT-008 entity before advancing.

---

## Stage Order

```
context → research → critique → synthesis → implementation
```

---

## Reference Architecture

The following engine modules must be referenced by name when scoping any research idea:

| Module | Code |
|---|---|
| Market Data / Data Quality | COMP-MD |
| ScreenerService | COMP-SCR |
| TechnicalAnalysisService | COMP-TA |
| NewsAnalysisAgent | COMP-NEWS |
| FundamentalAnalysisAgent | COMP-FUND |
| BacktestAgent | COMP-BT |
| RecommendationAgent | COMP-REC |
| Strict Buy Gate / Risk Management | COMP-RISK |
| Trade Planning | COMP-PLAN |
| Explanation / Audit Engine | COMP-EXP |

Situations (SIT-GN, SIT-BN, SIT-BMR, SIT-SR, SIT-CSE) and evaluation axes (Profitability, False Positive Risk, False Negative Risk, Overfitting Risk, Data Availability, Implementation Complexity, Testability, Explainability) are defined in `COMPONENT_SITUATION_TAXONOMY.md`.

---

## Data Reference

### Available

| Data | Source |
|---|---|
| OHLCV daily price history | FYERS (primary), yfinance (fallback) |
| Technical indicators | Computed (EMA20/50, SMA20/50/200, RSI, MACD, Supertrend) |
| News headlines | NewsAnalysisAgent |
| Fundamental data | FundamentalAnalysisAgent |
| Backtest metrics | BacktestAgent |
| Volume | Part of OHLCV |

### Missing / Weak

| Data | Status |
|---|---|
| Broad market regime | Missing |
| Sector relative strength | Missing |
| News article body | Missing |
| News deduplication | Missing |
| Sentiment time-decay | Missing |
| Slippage / transaction costs | Missing |
| Realistic position sizing | Missing |
| Volatility contraction / squeeze | Missing |
| Multi-timeframe confirmation | Missing |

Full detail in `SHARED_CONTEXT_PACK.md` sections 5–6.

---

## Stage Contracts

### Stage 1 — Context

| Field | Value |
|---|---|
| **Purpose** | Establish system scope, constraints, and data boundaries so the session has a shared vocabulary. |
| **Required inputs** | The idea description from the human. |
| **Required outputs** | A ResearchSession row in `research_sessions` with status `ACTIVE`, session_label matching the idea name, and metadata capturing the initial idea brief. |
| **FEAT-008 write target** | `research_sessions` — call `create_session(label, symbol, metadata)` |

---

### Stage 2 — Research

| Field | Value |
|---|---|
| **Purpose** | Flesh the idea into a structured research entity with component tag, situation tags, evidence level, lifecycle stage, bucket, required data, safe fallback, and rollback criteria. |
| **Required inputs** | ResearchSession ID from Stage 1; the idea description; data available / missing lists. |
| **Required outputs** | One ResearchIdea row in `research_ideas` with all mandatory fields populated: `component_tag`, `situation_tags` (JSON array), `evidence_level`, `lifecycle_stage`, `bucket`, `required_data` (JSON dict), `safe_fallback`, `rollback_criteria` (JSON dict). |
| **FEAT-008 write target** | `research_ideas` — call `create_idea(...)` |

---

### Stage 3 — Critique

| Field | Value |
|---|---|
| **Purpose** | Stress-test the idea against the eight evaluation axes from SHARED_CONTEXT_PACK section 10. Identify trade-offs, blind spots, and whether the idea is ready for synthesis. |
| **Required inputs** | ResearchIdea ID from Stage 2; the eight-axis framework. |
| **Required outputs** | One or more ResearchCritique rows in `research_critiques` covering: profitability impact, false positive risk, false negative risk, overfitting risk, data availability, implementation complexity, testability, and explainability. Each critique has a `critique_type` from `{PROFITABILITY, FALSE_POSITIVE, FALSE_NEGATIVE, OVERFITTING, DATA_AVAILABILITY, COMPLEXITY, TESTABILITY, EXPLAINABILITY}`. |
| **FEAT-008 write target** | `research_critiques` — call `create_critique(idea_id, critique_type, content, severity)` for each axis. |

---

### Stage 4 — Synthesis

| Field | Value |
|---|---|
| **Purpose** | Summarize the research + critique into a coherent synthesis that declares the idea's readiness, recommended action, and implementation approach. |
| **Required inputs** | ResearchIdea ID; all ResearchCritique IDs; the idea and critique content. |
| **Required outputs** | One ResearchSynthesis row in `research_syntheses` with `synthesis_text` containing the consolidated assessment, `source_idea_ids` referencing the originating idea, `status` set to `DRAFT`, and optionally a `confidence_score`. |
| **FEAT-008 write target** | `research_syntheses` — call `create_synthesis(session_id, title, synthesis_text, source_idea_ids, confidence_score)` |

---

### Stage 5 — Implementation

| Field | Value |
|---|---|
| **Purpose** | Formalise the implementation decision and track its rollout state (coding, testing, review, deployed). This stage is gated by critique resolution — all critiques blocking the idea must first be resolved. |
| **Required inputs** | ResearchSynthesis ID; ResearchIdea ID; decision rationale. |
| **Required outputs** | One ResearchDecision row in `research_decisions` with `decision_type` from `{IMPLEMENT, DEFER, REJECT}` and `rationale` explaining the call. At least one ResearchRolloutState row in `research_rollout_states` per rollout phase (e.g., `CODING`, `TESTING`, `REVIEW`, `DEPLOYED`). |
| **FEAT-008 write targets** | `research_decisions` — call `create_decision(session_id, decision_type, rationale, synthesis_id, idea_id)`  
| | `research_rollout_states` — call `create_rollout_state(decision_id, rollout_phase)` for each phase |

---

## Compliance Rules

Every stage output **must**:
- Be persisted to the corresponding FEAT-008 table before the next stage begins.
- Reference the preceding stage's output by its FEAT-008 primary key.
- Use the component and situation tags from `COMPONENT_SITUATION_TAXONOMY.md` when filling research_ideas fields.

---

*End of FEAT-009 — Reusable Research Prompt Chain v1.0*
