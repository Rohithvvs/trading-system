# Business Problem

## Why Scanner Exists
The Scanner Engine exists to programmatically filter through thousands of stocks in the market to find a high-probability shortlist of candidates that exhibit strong momentum, clear trend alignment, and sufficient liquidity. It eliminates the manual effort and cognitive bias of staring at charts for hours.

## Business Problem
In the stock market, opportunities are transient. A human trader cannot physically monitor all 500+ Nifty stocks, let alone the entire BSE index, in real time. 
Without an automated scanner:
1. Traders miss early entry points.
2. Emotional biases lead to chasing low-probability, low-liquidity stocks.
3. Time is wasted analyzing stocks that are not structurally ready for a move.

## Engineering Problem
Scanning hundreds of stocks requires fetching historical price data (OHLCV) concurrently, applying complex mathematical transformations (moving averages, MACD, RSI, Supertrend), and ranking them in near real-time without exceeding API rate limits or blowing up memory. The engineering challenge is building a pipeline that is:
1. **Resilient**: Handles missing data, API rate limits, and network timeouts.
2. **Performant**: Uses vectorized operations (Pandas DataFrames) to compute indicators in bulk instead of looping sequentially.
3. **Deterministic**: Given the same price data, the scanner must consistently produce the same scores and recommendations.

## Why Scanner comes before Technical Analysis
The Scanner acts as the **funnel**. 
1. **Scanner**: Operates on raw historical data for the entire universe (e.g., NIFTY 500). Its job is lightweight filtering (Hard Filters, Broad Trend Eligibility).
2. **Technical Analysis (Deep)**: Operates only on the shortlisted candidates (e.g., top 10). It computes advanced indicators, backtests strategies, gathers news sentiment, and uses LLM agents to generate a final `BUY`, `WATCH`, or `REJECT` recommendation.
Running deep technical and fundamental analysis on 500 stocks would be prohibitively slow and expensive. The scanner solves this by reducing the universe to a manageable subset.

## Why Professional Trading Systems Use Scanners
Professional systems require edge. Edge comes from discipline and math. Scanners enforce rules mathematically (e.g., `close > EMA20`, `MACD > Signal`) with zero emotion, ensuring that capital is only deployed into setups with a positive expected value.

## Real-World Analogy
Think of the Scanner as a **Recruitment ATS (Applicant Tracking System)**. 
- 10,000 resumes arrive (Market Universe).
- The ATS filters out those without a degree or 5 years of experience (Scanner: Hard Filters).
- Only 50 resumes make it to the hiring manager for a deep 1-on-1 interview (Deep Technical/Fundamental Analysis).
