# SHARED_CONTEXT_PACK — Swing Trading Recommendation Engine
**Version:** 1.1 — FEAT-001 Revised  
**Date:** 2026-07-11  
**Scope:** This document is the canonical context anchor for all future work on this system. Paste it as the first message in every new session.

---

## 1. System Intent

This is a **personal-use, long-only, algorithmic swing-trading recommendation engine** for Indian equities listed on the NSE.

- It produces **BUY / WATCH / REJECT** recommendations — it does not execute trades.
- It is designed for **human-in-the-loop** use: a human reviews all outputs before acting.
- Final decisions are made by deterministic code written by the owner — **not by live LLM inference**.
- The system is **brownfield**: it is operational and must not be redesigned without explicit instruction.

---

## 2. Non-Negotiable Constraints

| Constraint | Rule |
|---|---|
| Universe | NIFTY 500 only |
| Direction | Long-only. No short, no hedge. |
| Data primary | FYERS API |
| Data fallback | yfinance |
| Execution model | Human reviews recommendations; no auto-execution |
| No live LLM decisions | LLMs assist research and planning; code is deterministic |
| Brownfield safety | Every change must be a **bounded delta** to a named component |
| Backward compatibility | Existing pipeline stages must not break silently |
| Minimum history | 220 candles required for any stock to enter the pipeline |

---

## 3. Existing Architecture

```
Universe (NIFTY 500)
       │
       ▼
ScreenerService          ← pre-analysis hard filters
       │
       ▼
TechnicalAnalysisService ← 100-point technical score
       │
       ├──────────────────────────────┐
       ▼                              ▼
NewsAnalysisAgent         FundamentalAnalysisAgent
       │                              │
       └──────────┬───────────────────┘
                  ▼
            BacktestAgent
                  │
                  ▼
       RecommendationAgent            ← weighted synthesis → BUY / WATCH / REJECT
                  │
                  ▼
          Strict Buy Gate             ← final protection layer; can downgrade BUY → WATCH
```

---

## 4. Current Pipeline Stages

### Stage 1 — ScreenerService (Pre-Analysis Filters)
All conditions must pass or the stock is dropped before technical scoring.

- Minimum **220 candles** of price history
- **SMA50 > SMA200** (golden-cross style trend confirmation)
- **Close > SMA50**
- **20-day average volume > 100,000**

### Stage 2 — TechnicalAnalysisService (100-Point Score)
Hard filters are applied first. If any fail, the stock is rejected regardless of score.

**Hard filters (must all pass):**

| Filter | Threshold |
|---|---|
| Price > EMA20 | Required |
| Supertrend | Must be positive |
| MACD > Signal | Required |
| RSI | ≥ 50 |
| Volume | ≥ 50,000 |
| Price range | 100 ≤ Price ≤ 500,000 |

**Soft scoring components (combine to 100 points):**  
*(Note: Currently, if data for a soft scoring component is missing or fails to compute, it contributes 0 points to the total)*

- Trend: EMA20, EMA50 alignment, SMA20 slope
- Momentum: RSI, MACD histogram
- Structure: Higher-high / higher-low (HH/HL) sequence
- Candlestick context: Pattern library (currently limited)
- Liquidity: Volume relative to average
- Price: Within defined range constraints

### Stage 3 — Agent Layer (Parallel)

| Agent | Input | Output |
|---|---|---|
| NewsAnalysisAgent | Headline text | Sentiment score |
| FundamentalAnalysisAgent | Financial data | Fundamental score |
| BacktestAgent | Price history | Backtest performance metrics |

### Stage 4 — RecommendationAgent (Weighted Synthesis)

**Standard regime weights:**

| Component | Weight |
|---|---|
| Technical | 50 |
| Fundamental | 25 |
| Backtest | 25 |
| News | 0 |

**Catalyst regime weights (triggered when conditions below are met):**

| Component | Weight |
|---|---|
| Technical | 20 |
| Fundamental | 30 |
| Backtest | 20 |
| News | 30 |

**Catalyst regime trigger:**
- `abs(sentiment_score) >= 0.75` **OR** `current daily volume >= 3x 20-day average volume (matching Screener definition)`

**Recommendation thresholds:**

| Label | Composite Score |
|---|---|
| BUY | ≥ 72 |
| WATCH | 55 – 71.99 |
| REJECT | < 55 |

### Stage 5 — Strict Buy Gate (Final Protection)
Runs after RecommendationAgent. Can downgrade BUY → WATCH. Cannot upgrade. *(Note: The Gate can only downgrade to WATCH; it cannot downgrade to REJECT).*

**All four conditions must pass for BUY to survive:**

| Gate Condition | Requirement |
|---|---|
| Raw technical score | ≥ 75 |
| Risk-reward ratio | ≥ 1.25 |
| Data source | FYERS primary — no mock / fallback warning |
| History depth | Must re-verify the 220-candle minimum (failsafe for Screener) |

---

## 5. Data Available

| Data | Source | Notes |
|---|---|---|
| OHLCV daily price history | FYERS API (primary), yfinance (fallback) | Minimum 220 candles enforced |
| Technical indicators | Computed internally | EMA20, EMA50, SMA20, SMA50, SMA200, RSI, MACD, Supertrend |
| News headlines | NewsAnalysisAgent | Headline text only; no article body |
| Fundamental data | FundamentalAnalysisAgent | Source not specified beyond agent name |
| Backtest metrics | BacktestAgent | Computed from internal price history |
| Volume | Part of OHLCV | Used for screener and technical filters |

---

## 6. Data Missing / Weak / Unreliable

| Data | Status | Impact |
|---|---|---|
| Broad market regime | **Missing** | No filter for bear markets or high-VIX environments |
| Sector relative strength | **Missing** | Cannot rank stocks within sector or prefer strong sectors |
| News article body / full text | **Missing** | Sentiment is headline-only; low signal quality |
| News deduplication | **Missing** | Repeated headlines may inflate sentiment signal |
| Sentiment time-decay | **Missing** | Old news treated same as fresh news |
| News source credibility weighting | **Missing** | All sources treated equally |
| Slippage model | **Missing** | Backtest entries/exits assume zero slippage |
| Transaction costs / fees | **Missing** | Backtest P&L is overstated |
| Realistic position sizing | **Missing** | Backtest assumes 100% equity deployed |
| Volatility contraction / squeeze detection | **Missing** | No pre-breakout squeeze identification |
| Multi-timeframe confirmation | **Missing** | All analysis is single-timeframe |
| Intraday / tick data | **Not applicable** | Swing system; daily candles sufficient |

---

## 7. Current Decision Logic

```
Stock enters ScreenerService
  → Fails any pre-filter → DROPPED (silent, not scored)
  → Passes all pre-filters → sent to TechnicalAnalysisService

TechnicalAnalysisService
  → Fails any hard filter → REJECT
  → Passes all hard filters → compute 100-point score

Agents run in parallel:
  NewsAnalysisAgent → sentiment score
  FundamentalAnalysisAgent → fundamental score
  BacktestAgent → backtest score (normalized for weighting)

RecommendationAgent checks catalyst trigger:
  → Catalyst active → apply catalyst weights
  → No catalyst → apply standard weights
  → Compute composite score → assign BUY / WATCH / REJECT

Strict Buy Gate (BUY outputs only):
  → Any gate condition fails → downgrade to WATCH
  → All gate conditions pass → BUY confirmed
```

---

## 8. Known Gaps Already Acknowledged

These gaps are **recognized by the system owner**. They must not be re-raised as discoveries. Any future idea that addresses one must explicitly reference the gap by name from this list.

1. No broad market / macro regime filter
2. No sector relative strength model
3. News is headline-only (no article body)
4. No news deduplication
5. No sentiment time-decay
6. No news source credibility weighting
7. No volatility contraction / squeeze detection logic
8. Fixed BUY/WATCH/REJECT thresholds (not regime-adaptive)
9. Limited candlestick pattern library
10. No multi-timeframe confirmation
11. Backtest entry assumes same-candle close execution (look-ahead bias risk)
12. Backtest exit assumes same-candle close execution
13. No slippage in backtest
14. No fees in backtest
15. No realistic position sizing in backtest (assumes 100% equity deployment)

---

## 9. Five Market Situations — Mandatory Tagging

Every future idea, filter, signal, or enhancement **must be explicitly tagged** against one or more of these situations. An idea that cannot be tagged to a situation is not ready to be discussed.

| Tag | Situation | Description |
|---|---|---|
| `SIT-GN` | Good News | Company- or sector-level positive catalyst (earnings beat, contract win, upgrade) |
| `SIT-BN` | Bad News | Company- or sector-level negative event (miss, downgrade, legal issue, macro shock) |
| `SIT-BMR` | Broad Market Regime | Index-level environment: bull, bear, sideways, high volatility |
| `SIT-SR` | Sector Regime | Sector rotating in or out of favour relative to the broad index |
| `SIT-CSE` | Company-Specific Event | Event isolated to one stock: block deal, insider activity, split, bonus |

**Usage rule:** Every proposed idea must state which situations it helps, which it may harm, and which it is neutral to.

---

## 10. Eight Evaluation Axes — Mandatory Scoring

Every future idea must be rated on all eight axes before it is considered for implementation. Ratings are: `High / Medium / Low / None`.

| Axis | Question to Answer |
|---|---|
| **Profitability impact** | Does this increase expected return per trade? Is there evidence? |
| **False positive risk** | Does this increase recommendations that look good but lose money? |
| **False negative risk** | Does this filter out genuinely good trades? |
| **Overfitting risk** | Is this tuned to historical quirks that will not repeat? |
| **Data availability** | Is the required data reliably available now, or must it be sourced? |
| **Implementation complexity** | How many components must change? Is the delta bounded? |
| **Testability** | Can this be backtested or unit-tested in isolation before integration? |
| **Explainability** | Can a human understand and verify why this changed a recommendation? |

---

## 11. Mandatory Output Rules for All Future Sessions

Every idea, proposal, or suggestion in any future session **must comply with all of these rules**. Non-compliant proposals must be flagged and rewritten before discussion proceeds.

1. **No full rewrites.** Propose bounded deltas to named components only.
2. **Component tag required.** Every idea must name the pipeline stage it modifies: `ScreenerService`, `TechnicalAnalysisService`, `NewsAnalysisAgent`, `FundamentalAnalysisAgent`, `BacktestAgent`, `RecommendationAgent`, or `Strict Buy Gate`. *(If introducing a macro/market-level filter like Gap #1, inject it into ScreenerService or RecommendationAgent; do not invent a new agent).*
3. **Situation tag required.** Every idea must be tagged with one or more of the five situations from Section 9.
4. **Eight-axis rating required.** Every idea must be rated on all eight axes from Section 10.
5. **Required data must be stated.** List every data input the idea needs that is not already in Section 5.
6. **Safe fallback must be stated.** If required data is unavailable, what is the graceful degradation behaviour? The system must not fail silently.
7. **Idea type must be declared.** Choose exactly one:
   - `hard-filter` — blocks a stock from advancing
   - `soft-score-factor` — adjusts a numeric score
   - `watch-only-signal` — can only produce WATCH, never BUY
   - `explanation-only` — surfaces information to the human; does not change the decision
   - `reject-or-defer` — idea is not ready; state the reason
8. **Explainability check.** The idea must be describable in one plain-English sentence that a non-technical person could verify manually.
9. **Backtestability check.** The idea must be testable against historical data before any code is written.
10. **No live LLM decisions.** Final implementation is deterministic code. LLMs assist with design only.

---

## 12. Do / Do Not

### ✅ Do

- Propose ideas as bounded deltas to a single named component
- State all required data and its current availability status
- State the safe fallback for every new data dependency
- Tag every idea by situation and rate it on all eight axes
- Declare the idea type before describing the idea
- Reference known gaps by name when addressing them
- Check brownfield safety: does this break existing pipeline behaviour?
- Confirm that an idea is backtestable before recommending implementation

### ❌ Do Not

- Propose a full system redesign
- Introduce live LLM inference into the decision path
- Suggest ideas without stating required data
- Suggest ideas without a fallback if data is missing
- Re-raise known gaps (Section 8) as new discoveries
- Propose thresholds or weights without a backtest rationale
- Assume data is available without verifying against Section 5 and Section 6
- Generate application code — that is the owner's responsibility
- Skip the eight-axis rating for any idea
- Skip the situation tag for any idea

---

*End of SHARED_CONTEXT_PACK v1.1 — FEAT-001 Revised*
