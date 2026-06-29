# Recommendation Engine: Business Problem

## Why Recommendation Engine Exists

In modern financial markets, there is an overwhelming amount of data available—from real-time price ticks to broad macroeconomic indicators. A typical trader faces decision fatigue when processing thousands of symbols. 

The Recommendation Engine exists to synthesize multiple dimensions of analysis (Technical, Fundamental, Sentiment, and Historical Backtesting) into a single, actionable score and clear recommendation (BUY, WATCH, HOLD, REJECT). It converts raw mathematical data into human-understandable trading decisions, acting as an automated quantitative analyst.

## Why Scanner Alone Is Insufficient

A scanner (like the `ScreenerService`) is a filtering tool. It rapidly reduces a universe of thousands of stocks (e.g., NIFTY500) down to a manageable shortlist (e.g., top 10 stocks matching a specific technical setup like a MACD crossover). 
However, a scanner is binary and uni-dimensional; it merely checks if conditions are met. It does not weigh risk against reward, consider breaking news, or analyze historical backtest performance for the specific setup on that specific stock.

## Why Technical Analysis Alone Is Insufficient

Technical analysis looks only at price action and volume. While a stock might show a perfect "Bullish Engulfing" pattern on the chart, it might simultaneously have catastrophic fundamental debt or highly negative breaking news. Relying solely on technicals leads to false positives, often causing traders to enter "value traps" or trade against strong macro headwinds.

## Why Professional Platforms Combine Multiple Engines

Professional trading platforms recognize that markets are complex adaptive systems. By combining multiple engines, the system achieves:
1. **Confirmation:** Technicals provide the entry timing, fundamentals provide the long-term viability, and news sentiment provides the immediate catalyst.
2. **Risk Mitigation:** Backtesting proves if the current setup has historically worked for this specific asset, avoiding historically unprofitable patterns.
3. **Strict Gating:** A "BUY" is only issued when all dimensions align, heavily filtering out subpar trades.

## Perspectives

### Business Perspective
The business goal is to provide retail or institutional traders with high-conviction, low-risk trade setups, reducing their cognitive load and increasing their win rate. A reliable recommendation builds trust and user retention.

### Engineering Perspective
From an engineering standpoint, the Recommendation Engine acts as the final aggregator (a Reducer) in a map-reduce style pipeline. It consumes the outputs of independent micro-agents (`TechnicalAnalysisAgent`, `FundamentalAnalysisAgent`, `NewsAnalysisAgent`, `BacktestAgent`) and normalizes them into a standardized schema (`FinalRecommendation`).

## Real-World Analogy
Think of the Recommendation Engine as the **Chief Medical Officer (CMO)** in a hospital.
- The **Scanner** is the triage nurse, identifying patients who need attention.
- The **Technical Engine** is the heart monitor (vital signs).
- The **Fundamental Engine** is the patient's long-term medical history.
- The **News Engine** is asking the patient how they feel today.
- The **Backtest Engine** looks at clinical trial data for similar patients.
- Finally, the **Recommendation Engine (CMO)** looks at all these reports and makes the final decision: "Proceed with Surgery" (BUY), "Keep in Observation" (WATCH), or "Discharge" (REJECT).
