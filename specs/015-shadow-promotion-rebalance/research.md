# Research & Technical Decisions: Validation, Interaction Analysis, Rebalancing & Promotion

**Feature**: `015-shadow-promotion-rebalance`  
**Date**: 2026-07-22

---

## 1. Attribution & A/B Ablation Methodology

### Decision
Implement a pure, offline data extraction and evaluation service (`AttributionValidationService`) in `backend/app/services/attribution_validation_service.py` that queries historical `AnalysisHistory` records containing Sprint 7 shadow mode telemetry (`shadow_outputs->'sentiment_decay'` and `shadow_outputs->'market_breadth'`).

### Rationale
- **4-Way Synthetic Replay**: Evaluates each historical scan record against 4 candidate scoring configurations:
  1. *Baseline*: Production score stored in `AnalysisHistory`.
  2. *Decay-Only*: Substitutes time-decayed sentiment score into calculation.
  3. *Breadth-Only*: Applies market breadth soft score contribution ($[-15.0, +15.0]$) to composite score.
  4. *Combined*: Applies both time-decayed sentiment and market breadth soft score contribution.
- **Ablation Metrics**: Calculates win rate, false-positive rate, precision, signal accuracy, and feature-specific alpha attribution percentage across situation tags (`GOOD_NEWS_CATALYST`, `MARKET_REGIME`, etc.).
- **Sample Size & Safeguards**: Requires minimum 30 historical shadow records. If sample size $<30$ or keys are missing, reports status `INSUFFICIENT_DATA` and enforces automatic `No-Go`.

---

## 2. Feature Interaction & Redundancy Analysis

### Decision
Calculate Pearson correlation coefficient ($r$) and Spearman rank correlation between the numeric score delta of Sentiment Time-Decay ($\Delta_{decay} = score_{decay} - score_{base}$) and Market Breadth ($\Delta_{breadth} = soft\_contribution$).

### Rationale & Decision Matrix
- $r < 0.70$: **Complementary** $\to$ Decision: **Promote Both** (Stage 1 Decay, Stage 2 Breadth).
- $0.70 \le r \le 0.85$: **Moderate Overlap** $\to$ Decision: **Promote Decay First**, re-evaluate Breadth after 7 days.
- $r > 0.85$: **Redundant** $\to$ Decision: **Promote Decay Only**, Reject Market Breadth.
- **Persistence**: Results written to JSON report (`specs/015-shadow-promotion-rebalance/reports/attribution_and_interaction_report.json`) and logged via `AuditTrailManager`.

---

## 3. Point-Budget Rebalancing Strategy

### Decision
Rebalance the 100-point production recommendation matrix upon Stage 2 Market Breadth promotion:
- **Baseline Matrix**: Technical: 35 pts, Sentiment: 25 pts, Fundamental: 25 pts, Volume: 15 pts = 100 pts.
- **New Rebalanced Matrix**: Technical: 35 pts, Sentiment: 25 pts, Fundamental: 15 pts, Volume: 15 pts, Market Breadth: 10 pts = 100 pts.

### Rationale (Minimal Disruption Principle)
- Fundamental score has the highest static slack for swing/day trading scans (infrequently updated relative to market ticks).
- Deducting 10 points from Fundamental (25 $\to$ 15) and allocating 10 points to Market Breadth preserves Technical (35) and Volume (15) responsiveness while ensuring the matrix sum strictly equals 100.
- Matrix invariant assertion `sum(weights) == 100` strictly enforced via schema validator and unit test suite.

---

## 4. Controlled Sequential Promotion Architecture

### Decision
Utilize existing Sprint 5 `RuleManager` singleton with two explicit feature keys:
1. `"sentiment_decay"` (Stage 1)
2. `"market_breadth"` (Stage 2)

### Rationale
- **Stage 1 (Decay)**: Calibration update. When `RuleManager().is_active_in_production("sentiment_decay")` is True, `NewsAnalysisAgent` and `RecommendationService` substitute decayed sentiment scores in the live scoring pipeline.
- **Stage 2 (Breadth)**: Structural matrix update. When `RuleManager().is_active_in_production("market_breadth")` is True, `RecommendationService` applies Market Breadth soft score contribution and rebalanced matrix weights.
- **Kill-Switch**: Setting state to `"disabled"` (or `"shadow"`) instantly bypasses live execution in $<1\text{ms}$, falling back to baseline logic with 0 downtime.
