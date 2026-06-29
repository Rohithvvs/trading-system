# Technical Analysis Engine: Business Problem

## Why Technical Analysis Exists
In a quantitative trading system, finding assets to trade is only half the battle. While a scanner or screener can filter thousands of symbols based on broad criteria (e.g., "is the price above the 50-day moving average" or "is the volume above 100k"), it lacks the nuance required to execute a statistically sound trade. 

Technical Analysis (TA) exists to answer the critical questions of *when* to buy, *when* to sell, and *when* to stay away. It quantifies market psychology, price action structure, and momentum into mathematical rules that a machine can execute without emotion.

## Why the Scanner Alone is Insufficient
The Scanner (`ScreenerService`) is responsible for reducing the universe of stocks to a manageable shortlist (e.g., from 500 stocks down to 10). It uses broad eligibility criteria:
- Is the stock liquid enough? (`avg_volume > 100000`)
- Is it generally in an uptrend? (`latest_close > sma_50` and `sma_50 > sma_200`)

However, the Scanner does not know if the stock is overbought, if momentum is fading, or if a precise candlestick pattern (like a Hammer) has formed at a key support level. Without the Technical Analysis Engine, the Scanner would simply buy blindly into a trend, often right before a pullback.

## Why Institutions Use Technical Analysis
Institutions use Technical Analysis not as a crystal ball, but as a risk management and probability framework:
1. **Risk Definition:** TA identifies key support and resistance levels, allowing institutions to calculate a precise risk-to-reward ratio before entering a trade.
2. **Momentum Quantification:** Indicators like MACD and RSI quantify whether buying pressure is accelerating or decelerating, helping institutions enter during momentum bursts and exit when momentum fades.
3. **Execution Edge:** By identifying precise setups (e.g., a stock pulling back to its 20 EMA while maintaining a positive Supertrend), institutions can execute at optimal prices rather than chasing extended moves.
4. **Algorithmic Standardization:** TA converts visual chart patterns into strict mathematical rules, enabling algorithmic execution at scale across thousands of assets simultaneously.

## Business Purpose
The business purpose of the Technical Analysis Engine is to **maximize the probability of a profitable trade by ensuring entries and exits are mathematically justified.** It acts as the final gatekeeper before capital is deployed. If a symbol passes the Scanner but fails the Technical Analysis filters, the system stays in cash, protecting the portfolio from sub-optimal setups.

## Engineering Purpose
From an engineering perspective, the Technical Analysis Engine (`TechnicalAnalysisService`) must:
1. **Process Data at Scale:** Calculate complex indicators (EMA, MACD, RSI, VWAP) across hundreds of symbols simultaneously using vectorized operations (Pandas).
2. **Standardize Signals:** Normalize disparate indicator values into a unified scoring system (0 to 100) and discrete signals (`bullish`, `neutral`, `bearish`).
3. **Provide Determinism:** Ensure that given the same historical OHLCV (Open, High, Low, Close, Volume) data, the engine will always produce the exact same technical score and signal, enabling accurate backtesting and reliable live execution.
4. **Isolate Logic:** Separate the mathematical calculation of indicators from the business logic of filtering and routing, ensuring the engine remains a pure function of its inputs.
