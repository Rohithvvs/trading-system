# COMPONENT_SITUATION_TAXONOMY — Classification Framework
**Version:** 1.0 — FEAT-002 Baseline  
**Date:** 2026-07-11  
**Scope:** This taxonomy defines the strict classifications that all future feature ideas, indicators, filters, and modifications must be tagged against. This prevents prompt drift, vague recommendations, and architectural regression.

---

## 1. Component Taxonomy

All changes must be mapped to exactly one primary component where the deterministic code change will actually live. "General Strategy" is not a valid component.

| Component Code | Component Name | Maps to Existing Engine Module | Ownership | Non-Ownership | Valid Change Examples | Common Classification Mistakes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **COMP-MD** | Market Data / Data Quality | Data fetching layers / API clients | Fetching raw candles, caching, rate-limiting, error fallbacks, mock data flags. | Performing technical indicator calculations or screening logic. | Adding a yfinance fallback retry delay; catching connection timeouts. | Classifying a volume-based screener rule here just because it uses "data". |
| **COMP-SCR** | ScreenerService | `ScreenerService` | Initial hard filters applied to the NIFTY 500 universe before scoring. | Point scoring, technical indicators used for recommendation weights. | Changing the 20-day average volume filter from 100k to 150k. | Tagging a Supertrend check as Screener when it is computed in the scoring stage. |
| **COMP-TA** | TechnicalAnalysisService | `TechnicalAnalysisService` | 100-point soft-scoring logic, indicators, trend/momentum/structure scores. | Dynamic regime weighting, non-price data (news/fundamentals). | Adding a new candlestick pattern to the library; adjusting RSI scoring curves. | Putting risk/reward gating logic here instead of `COMP-RISK`. |
| **COMP-NEWS** | NewsAnalysisAgent | `NewsAnalysisAgent` | Headline text parsing, sentiment calculations, news pre-processing. | Synthesis of news score with other scores, catalyst weights. | Implementing news headline deduplication; applying sentiment time-decay. | Classifying the news catalyst weight trigger here instead of `COMP-REC`. |
| **COMP-FUND** | FundamentalAnalysisAgent | `FundamentalAnalysisAgent` | Scoring of financial health, balance sheet/earnings ratio calculations. | Stock price action analysis, entry triggers. | Adjusting PE ratio weights; adding debt-to-equity filters. | Putting earnings calendar date checks here when they act as trade blocks. |
| **COMP-BT** | BacktestAgent | `BacktestAgent` | Historical trade simulation execution, performance calculations. | Live recommendation calculations or production output templates. | Adding a 0.05% slippage model; simulating transaction taxes/brokerage fees. | Classifying backtest-driven filter rules that block live trades here. |
| **COMP-REC** | RecommendationAgent | `RecommendationAgent` | Synthesis logic, composite score math, regime detection, thresholds. | Calculation of individual scores (technical, news, fundamentals). | Adjusting standard vs catalyst regime weights; changing the BUY threshold. | Classifying a new technical indicator as `COMP-REC` instead of `COMP-TA`. |
| **COMP-RISK** | Strict Buy Gate / Gating | `Strict Buy Gate` | Failsafe rules that downgrade BUY recommendations *after* synthesis. | Screener filters that drop stocks before scoring occurs. | Changing minimum risk-reward from 1.25 to 1.50; blocking trades near earnings. | Classifying pre-analysis screener filters as Gate rules. |
| **COMP-PLAN** | Trade Planning | Output Formatting / Planning module | Generating trade execution parameters (entry triggers, stop-losses, target levels). | Deciding BUY/WATCH/REJECT recommendation labels. | Modifying stop-loss logic from ATR-based to swing-low pivot-based. | Tagging risk-reward constraints (which live in `COMP-RISK`) here. |
| **COMP-EXP** | Explanation / Audit | Output/Log generation layers | Textual reasoning, audit trails, and factor attribution metrics for human review. | Deciding whether a stock is a BUY, WATCH, or REJECT. | Adding a breakdown of which soft-factors contributed most to a technical score. | Classifying logic that alters the final recommendation as `COMP-EXP`. |

---

## 2. Market Situation Taxonomy

Every idea must be mapped to the primary market situation it addresses. "Market Conditions" is not a valid situation tag.

| Situation Code | Situation Name | Definition | Typical Triggers / Examples | Common Confusions | Tag WHEN | Tag NOT WHEN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SIT-GN** | Good News | Company/sector-specific positive news catalyst. | Earnings beats, contract wins, brokerage upgrades, FDA approvals. | Confused with `SIT-CSE` (corporate actions without news flow). | The logic parses positive textual reports or acts on news-spike volume. | The event is a scheduled corporate action without news sentiment (e.g., split). |
| **SIT-BN** | Bad News | Company/sector-specific negative news catalyst. | Earnings misses, regulatory fines, management exits, litigation. | Confused with general market downtrends (`SIT-BMR`). | The logic handles negative sentiment flow or news panic. | The drop is a result of broad market selling without specific news. |
| **SIT-BMR** | Broad Market Regime | Macro/index-level conditions affecting the entire market. | Nifty 500 trend changes, India VIX spikes, interest rate changes. | Confused with Sector Regime (`SIT-SR`) dynamics. | The filter restricts trading based on index conditions (e.g., bear market). | The condition only affects a specific group of stocks (e.g., IT stocks). |
| **SIT-SR** | Sector Regime | Relative strength or trend changes in a specific industry sector. | Nifty IT outperforming Nifty 500, sector rotation indicators. | Confused with individual stock strength. | The logic measures a stock's behavior relative to its industry peer index. | The strength is isolated to a single stock due to its own news. |
| **SIT-CSE** | Company-Specific Event | Scheduled or corporate actions isolated to a single stock. | Earnings date proximity, dividend releases, stock splits, block deals. | Confused with `SIT-GN` or `SIT-BN` news catalysts. | The logic acts on dates, corporate actions, or insider trading filings. | The catalyst is a subjective news article or general press release. |

---

## 3. How to Tag an Idea

To ensure consistent categorization across different sessions, enforce these structural rules:

### Rule 3.1: Single-Component vs Multi-Component Ideas
- Every idea must have exactly **one Primary Component Tag**. This tag identifies where the actual code delta will be written.
- If the change requires coordination across multiple components (e.g., adding a score in `TechnicalAnalysisService` and using it to trigger a regime change in `RecommendationAgent`), a **Secondary Component Tag** may be specified.
- *Default Action:* If an idea spans the system, anchor the Primary Component Tag to the module where the deterministic logical change takes place, not where the data originates or is printed.

### Rule 3.2: Primary Situation vs Secondary Situations
- Every idea must have exactly **one Primary Situation Tag**. This identifies the specific market environment the change is designed to exploit or protect against.
- Up to two **Secondary Situation Tags** are allowed if the logic dynamically handles different contexts (e.g., a rule that acts on index conditions but behaves differently during earnings season).
- If the change is a pure infrastructure enhancement (e.g., backtest transaction costs), set the Primary Situation to `SIT-BMR` (since transaction drag affects all regimes) and document it as a baseline change.

---

## 4. Decision Trees for Classification

### 4.1 Component Tag Decision Tree

```
Does the change modify raw data retrieval, error handling, or API retries?
 ├── YES ──> Tag COMP-MD
 └── NO
      │
      Does the logic filter out stocks BEFORE any technical scoring takes place?
       ├── YES ──> Tag COMP-SCR
       └── NO
            │
            Does the change calculate indicator scores, trend scores, or price-action patterns?
             ├── YES ──> Tag COMP-TA
             └── NO
                  │
                  Does it change news parsing or headline sentiment analysis?
                   ├── YES ──> Tag COMP-NEWS
                   └── NO
                        │
                        Does it change fundamental scoring or balance sheet checks?
                         ├── YES ──> Tag COMP-FUND
                         └── NO
                              │
                              Does it simulate historical trades, slippage, or backtest metrics?
                               ├── YES ──> Tag COMP-BT
                               └── NO
                                    │
                                    Does it change standard/catalyst weights or threshold synthesis?
                                     ├── YES ──> Tag COMP-REC
                                     └── NO
                                          │
                                          Does it act as a final post-synthesis block (e.g. Risk/Reward, source check)?
                                           ├── YES ──> Tag COMP-RISK
                                           └── NO
                                                │
                                                Does it compute entry, stop-loss, or target price levels?
                                                 ├── YES ──> Tag COMP-PLAN
                                                 └── NO ──> Tag COMP-EXP (Log formatting/explanation rendering)
```

---

### 4.2 Situation Tag Decision Tree

```
Is the change designed to react to index-level indicators, VIX, or macro trends?
 ├── YES ──> Tag SIT-BMR
 └── NO
      │
      Is the logic assessing performance relative to an industry sector index?
       ├── YES ──> Tag SIT-SR
       └── NO
            │
            Is the logic driven by scheduled corporate actions, earnings dates, or splits?
             ├── YES ──> Tag SIT-CSE
             └── NO
                  │
                  Does the change react to news sentiment (Positive/Earnings Beat/Contract)?
                   ├── YES ──> Tag SIT-GN
                   └── NO ──> Tag SIT-BN (Negative news, litigation, earnings miss)
```

---

## 5. Worked Examples

### Example 1: News Deduplication
- **One-line idea:** Strip out duplicate news headlines for a stock within a 24-hour window to prevent sentiment inflation.
- **Primary Component Tag:** `COMP-NEWS`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-CSE` (Company-Specific Event)
- **Secondary Situation Tags:** `SIT-GN`, `SIT-BN`
- **Why this classification is correct:** Deduplication occurs during headline pre-processing inside the news parsing module (`COMP-NEWS`). It targets company-specific headline feeds (`SIT-CSE`) which directly feed into good/bad news sentiment analysis.
- **Likely misclassification:** `COMP-REC` / `SIT-GN`. *Why it is wrong:* The RecommendationAgent does not see individual headlines; it only receives the synthesized news score.

### Example 2: Sentiment Time-Decay
- **One-line idea:** Apply an exponential decay function to news sentiment scores so older news has less impact on recommendation synthesis.
- **Primary Component Tag:** `COMP-NEWS`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-GN`
- **Secondary Situation Tags:** `SIT-BN`
- **Why this classification is correct:** Time-decay calculations directly alter how the raw sentiment score is generated within `NewsAnalysisAgent`. News triggers positive or negative catalysts (`SIT-GN`/`SIT-BN`).
- **Likely misclassification:** `COMP-REC` / `SIT-CSE`. *Why it is wrong:* Decay belongs to the sentiment processor, not the weighted synthesiser. Proximity of news is a sentiment factor, not a scheduled corporate event.

### Example 3: Market Breadth Soft Factor
- **One-line idea:** Compute the percentage of NIFTY 500 stocks trading above their SMA50 and add it as a soft scoring factor to the Technical score.
- **Primary Component Tag:** `COMP-TA`
- **Secondary Component Tag:** `COMP-REC`
- **Primary Situation Tag:** `SIT-BMR`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** Calculating the market breadth metric is a technical indicator calculation (`COMP-TA`) that explicitly measures the Broad Market Regime (`SIT-BMR`).
- **Likely misclassification:** `COMP-SCR` / `SIT-SR`. *Why it is wrong:* This does not screen out individual stocks; it modifies the technical score. It measures the broad market index, not sector rotations.

### Example 4: Sector-Strength Watch-Only Signal
- **One-line idea:** Downgrade any BUY recommendation to WATCH if the stock's underlying sector index relative strength is in the bottom quartile.
- **Primary Component Tag:** `COMP-RISK`
- **Secondary Component Tag:** `COMP-TA`
- **Primary Situation Tag:** `SIT-SR`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** This rule acts as a final filter that downgrades BUY to WATCH (`COMP-RISK`) based on sector index performance (`SIT-SR`).
- **Likely misclassification:** `COMP-TA` / `SIT-BMR`. *Why it is wrong:* While sector indices use technical data, a hard rule that downgrades recommendations behaves as a Gate. It targets industry sectors, not the broad market index.

### Example 5: Pre-Earnings Caution Rule
- **One-line idea:** Downgrade BUY recommendations to WATCH if the stock's scheduled earnings release is within 5 trading days.
- **Primary Component Tag:** `COMP-RISK`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-CSE`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** This is a hard gating constraint that intercepts and downgrades recommendations (`COMP-RISK`) triggered by a scheduled corporate action (`SIT-CSE`).
- **Likely misclassification:** `COMP-FUND` / `SIT-BN`. *Why it is wrong:* It does not score financial statements; it reads the calendar. The rule fires before the news is known, so it is a corporate event block, not a bad news response.

### Example 6: Slippage Modeling in Backtest
- **One-line idea:** Apply a flat 0.05% price penalty to all entry and exit fills in the BacktestAgent.
- **Primary Component Tag:** `COMP-BT`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-BMR`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** Changes the execution physics of the simulator (`COMP-BT`). It applies to all simulated market environments, so it is marked under `SIT-BMR` (broad execution drag).
- **Likely misclassification:** `COMP-PLAN` / `SIT-CSE`. *Why it is wrong:* Trade planning calculates current parameters for live trade entries; it does not simulate historical trade drag.

### Example 7: Adaptive BUY Threshold Idea
- **One-line idea:** Dynamically increase the composite RecommendationAgent score threshold for BUY recommendations from 72 to 78 when the broad market is in a downtrend.
- **Primary Component Tag:** `COMP-REC`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-BMR`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** Modifies the synthesis thresholds inside `RecommendationAgent` based on broad index conditions (`SIT-BMR`).
- **Likely misclassification:** `COMP-RISK` / `SIT-SR`. *Why it is wrong:* This changes the RecommendationAgent's primary categorization logic (BUY vs WATCH), rather than applying a downstream filter gate. It acts on the whole market, not a sector.

### Example 8: Candlestick Library Expansion
- **One-line idea:** Add support for detecting the "Three Inside Up" reversal pattern in the technical analysis scoring module.
- **Primary Component Tag:** `COMP-TA`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-CSE` (Company-Specific Event)
- **Secondary Situation Tags:** None
- **Why this classification is correct:** Adding technical patterns belongs inside the technical calculations module (`COMP-TA`). Candlesticks are isolated to a single stock's price action chart (`SIT-CSE`).
- **Likely misclassification:** `COMP-SCR` / `SIT-BMR`. *Why it is wrong:* Candlestick patterns are used for scoring, not for filtering out stocks in the pre-analysis screener. They are stock-specific, not market-wide.

### Example 9: Explanation-Only Catalyst Warning
- **One-line idea:** Display a high-volume warning flag in the human-facing console output if volume spike exceeds 5x normal.
- **Primary Component Tag:** `COMP-EXP`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-CSE`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** This is an explanation-only warning flag that does not alter recommendation labels (`COMP-EXP`), triggered by stock-specific volume changes (`SIT-CSE`).
- **Likely misclassification:** `COMP-RISK` / `SIT-GN`. *Why it is wrong:* Warnings that do not downgrade recommendations are explanations, not risk gates.

### Example 10: Stricter Liquidity Filter
- **One-line idea:** Increase the minimum pre-analysis volume filter from 100k to 150k.
- **Primary Component Tag:** `COMP-SCR`
- **Secondary Component Tag:** None
- **Primary Situation Tag:** `SIT-BMR`
- **Secondary Situation Tags:** None
- **Why this classification is correct:** Modifies a hard universe filter in the pre-analysis ScreenerService (`COMP-SCR`). It filters stocks based on broad liquidity standards (`SIT-BMR`).
- **Likely misclassification:** `COMP-TA` / `SIT-CSE`. *Why it is wrong:* This filter drops stocks before scoring occurs, making it a screener change.

---

*End of COMPONENT_SITUATION_TAXONOMY v1.0 — FEAT-002 Baseline*
