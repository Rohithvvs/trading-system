# CLASSIFICATION_RULEBOOK — Operating Prompt Framework
**Version:** 1.1 — FEAT-003 Revised  
**Date:** 2026-07-11  
**Scope:** This document translates the system taxonomy into a strict, operational prompt validation framework. It prevents prompt drift, standardizes input submissions, and guides LLMs to generate bounded, brownfield-safe implementation suggestions.

---

## 1. Taxonomy Drift Risks

To prevent future sessions from drifting, models must monitor these three high-probability friction points:
1. **The "SIT-BMR" Gravity Well:** LLMs tend to dump any general system feature, indicator, or logic change into `SIT-BMR` (Broad Market Regime). 
2. **The "Data Origin" Conflation:** Classifying an idea based on *what data it reads* rather than *which file is modified*. For example, tagging a volume-based rule as `COMP-MD` (Data Quality) because it uses volume data, when it should be `COMP-SCR` (ScreenerService).
3. **The "CSE vs GN/BN" Sentiment Mismatch:** Conflating subjective sentiment indicators (`SIT-GN`/`SIT-BN`) with scheduled or unscheduled objective corporate events (`SIT-CSE`).

---

## 2. Classification Operating Rules

All candidate modifications must adhere to these four hard rules:

*   **Rule 1: Delta-Based Component Tagging (with Multi-File Tie-Breaker):** The primary component tag is strictly determined by the target file/class containing the code delta. If the logic consumes news but is written in `ScreenerService`, it is tagged `COMP-SCR`, not `COMP-NEWS`. If a feature requires code deltas in multiple files, the primary component is the one executing the final downstream decision (e.g., `COMP-REC` takes priority over `COMP-TA` if TA just provides the input indicator).
*   **Rule 2: Boundary Exclusivity:** Every submission must specify exactly one primary component and one primary situation. Optional secondary tags are strictly capped at one component and two situations.
*   **Rule 3: Gating Order:** Filters that discard assets *prior* to scoring are `COMP-SCR`. Filters that downgrade assets *after* synthesis are `COMP-RISK`.
*   **Rule 4: Situation Exclusivity (Objective vs Subjective Events):** Scheduled actions, unscheduled objective company events (halts, block deals, sudden resignations), and single-stock-specific technical setups when no broader market or sector condition is the primary driver are `SIT-CSE`. Subjective media commentary, news sentiment, and general press reactions to those events are `SIT-GN` or `SIT-BN`.

---

## 3. Classifier Prompts and Instructions

Paste these target validations into the model context when evaluating or modifying trading ideas:

### Instruction 1: The "Code Delta" Validation
- **Purpose:** Force classification by file modification location, not data source.
- **When to apply:** During initial component assignment.
- **Failure mode prevented:** Classifying a new technical indicator calculation as `COMP-MD` (Market Data) instead of `COMP-TA` (Technical Analysis).
- **Example:** *"This indicator reads yfinance data but the code delta is written in TechnicalAnalysisService. It must be tagged COMP-TA."*

### Instruction 2: The Screener vs Gate Validator
- **Purpose:** Enforce the pipeline sequence order (Stage 1 vs Stage 5).
- **When to apply:** Categorizing filters that eliminate or downgrade stocks.
- **Failure mode prevented:** Tagging a pre-analysis volume filter as `COMP-RISK` or a post-synthesis risk-reward block as `COMP-SCR`.
- **Example:** *"The rule checks average volume before scoring. This is a pre-filter; tag it COMP-SCR, not COMP-RISK."*

### Instruction 3: Synthesis vs Source Calculation Auditor
- **Purpose:** Protect the calculation boundaries of agents from synthesis logic.
- **When to apply:** Reviewing ideas that adjust recommendations.
- **Failure mode prevented:** Modifying the scoring logic of an agent (e.g., News Analysis) directly inside the weighted merger class (`COMP-REC`).
- **Example:** *"This idea adjusts standard weights based on VIX. The code delta belongs in RecommendationAgent; tag it COMP-REC, not COMP-TA."*

### Instruction 4: Target Calculation vs Execution Block Divider
- **Purpose:** Distinguish between execution targets and trade-blocking filters.
- **When to apply:** Analyzing exit, stop-loss, or entry planning logic.
- **Failure mode prevented:** Confusing ATR-based stop-loss positioning (`COMP-PLAN`) with risk-reward ratio gating rules (`COMP-RISK`).
- **Example:** *"This code computes the target price level. Tag it COMP-PLAN, not COMP-RISK."*

### Instruction 5: Objective Event vs Subjective News Inspector
- **Purpose:** Enforce the boundary between scheduled/unscheduled objective events and news sentiment.
- **When to apply:** Classifying corporate announcements or date-based triggers.
- **Failure mode prevented:** Tagging a scheduled earnings date filter as `SIT-GN` or a sudden CEO resignation as `SIT-BN`.
- **Example:** *"This logic blocks entries 3 days before earnings. This is a calendar event; tag it SIT-CSE, not SIT-GN."*

### Instruction 6: Index Trend vs Sector Strength Classifier
- **Purpose:** Prevent index-wide regimes from masking sector-specific trends.
- **When to apply:** Classifying macro indicator filters.
- **Failure mode prevented:** Tagging a sector rotation rule as `SIT-BMR` (Broad Market Regime).
- **Example:** *"This rule measures IT sector outperformance. Tag it SIT-SR, not SIT-BMR."*

### Instruction 7: Universal Baseline Allocation
- **Purpose:** Define standard tags for structural features that affect all conditions.
- **When to apply:** Categorizing backtest constraints or universal platform defaults.
- **Failure mode prevented:** Leaving infrastructure rules untagged or assigning them to random news regimes.
- **Example:** *"This slippage calculation applies to all trades. Tag it COMP-BT and SIT-BMR."*

### Instruction 8: Non-Redesign Constraint Verification
- **Purpose:** Block attempts to rewrite core logic or introduce unauthorized agents.
- **When to apply:** Prior to any architectural or component implementation draft.
- **Failure mode prevented:** Creating a new runtime agent when a local delta to an existing service is sufficient.
- **Example:** *"Adding a MarketRegimeAgent violates the brownfield constraint. Inject the logic as a helper in ScreenerService under COMP-SCR."*

---

## 4. Misclassification Traps

Avoid these common classification errors at component and situation boundaries:

```
                  ┌──────────────────────────────────────────────┐
                  │            COMPONENT BOUNDARIES              │
                  └──────────────────────────────────────────────┘

 COMP-SCR  ◄─────────────────── Pre-scoring Filter? ───────────────────►  COMP-TA
(ScreenerService)                                                  (TechnicalAnalysis)
  TRAP: Tagging TA indicators used as screener blocks (e.g., Close > SMA50) as COMP-TA.
  RULE: If the logic runs in ScreenerService and drops the stock before scoring, it is COMP-SCR.

 COMP-TA   ◄───────────────── Score vs Weight Synthesis? ──────────────►  COMP-REC
(TechnicalAnalysis)                                                (RecommendationAgent)
  TRAP: Adjusting component weights inside indicator calculation modules.
  RULE: Indicator value math belongs in COMP-TA. Adjusting how those values are merged is COMP-REC.

 COMP-RISK ◄──────────────── Downgrade Trade vs Target Math? ──────────►  COMP-PLAN
(Strict Buy Gate)                                                    (Trade Planning)
  TRAP: Tagging target calculation or Risk-Reward ratio logic as RISK because it affects downstream buys.
  RULE: All math generating price levels or calculating the numeric Risk:Reward ratio is COMP-PLAN.
        Evaluating the downstream boolean condition (e.g., 'if R:R < 1.25 then downgrade') is COMP-RISK.

 COMP-NEWS ◄───────────────── Text Score vs Synthesis Weight? ──────────►  COMP-REC
(NewsAnalysisAgent)                                                (RecommendationAgent)
  TRAP: Placing volume-spike catalyst triggers inside the News agent.
  RULE: Internal math to calculate an agent's single output score belongs to that agent (COMP-NEWS).
        Merging and weighting scores across different agents is COMP-REC.


                  ┌──────────────────────────────────────────────┐
                  │            SITUATION BOUNDARIES              │
                  └──────────────────────────────────────────────┘

 SIT-BMR   ◄───────────────── Sector vs Broad Market? ─────────────────►  SIT-SR
(Broad Market Regime)                                               (Sector Regime)
  TRAP: Tagging sector index trends (e.g., Bank Nifty SMA cross) as SIT-BMR.
  RULE: If the index represents an industry sub-sector, it is SIT-SR. Nifty 50/500 indices are SIT-BMR.

 SIT-GN / SIT-BN ◄─────────── Subjective Sentiment vs Event? ─────────►  SIT-CSE
(News Sentiment)                                                    (Company-Specific)
  TRAP: Tagging corporate events (sudden CEO resignation, halts, block deals) as SIT-GN/BN because they generate news.
  RULE: Scheduled actions, unscheduled objective company events (halts, block deals, sudden resignations),
        and single-stock-specific technical setups when no broader market or sector condition is the primary driver
        are SIT-CSE. Subjective commentary, sentiment, and general press reactions to those events are SIT-GN/BN.
```

---

## 5. Candidate Submission Template

Use this template to present any future feature, indicator, or rule change for review. Do not generate code until this metadata is validated.

```markdown
### Candidate Idea Submission
- **Idea Name:** [Brief descriptive title]
- **One-Line Description:** [What the code does in plain English]
- **Primary Component Tag:** COMP-[SCR|TA|NEWS|FUND|BT|REC|RISK|PLAN|EXP|MD]
- **Secondary Component Tag:** [Optional: Specify one or None]
- **Primary Situation Tag:** SIT-[GN|BN|BMR|SR|CSE]
- **Secondary Situation Tags:** [Optional: Specify up to two, comma-separated]
- **Target Implementation Class:** [Name of the existing class to modify]
- **Required Input Data:** [Describe any new data feeds or indicators required]
- **Safe Fallback Behavior:** [Action taken if inputs are missing/uncomputed]
- **Deterministic Logic Check:** [One sentence verifying this contains no live LLM runtime decisions]
- **Explainability Check:** [Describe how a human manually verifies this rule's output]
```

---

*End of CLASSIFICATION_RULEBOOK v1.1 — FEAT-003 Revised*
