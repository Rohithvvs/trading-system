# 01 Business Problem

## Why News Analysis Exists
In professional trading systems, analyzing price and volume (Technical Analysis) is insufficient. Prices are ultimately driven by fundamentals, catalysts, and news. The News Analysis Engine exists to ingest these catalysts (news headlines and articles) to understand the underlying sentiment driving a stock's movement.

## Why Technical Analysis Alone is Insufficient
Technical analysis tells us *what* the price is doing, but not *why*. 
- A stock breaking out on no news might be a false breakout.
- A stock breaking down on fake or insignificant news might be a buy opportunity (a trap).
- Over-relying on indicators without context leads to lower win rates.

## Why Professional Trading Systems Combine Technical and Fundamental/News Data
By combining technical signals with news sentiment, the system can dynamically adjust its scoring and risk parameters. For instance, `RecommendationService` heavily penalizes or rewards a stock depending on whether there is a significant news catalyst. 

## Business Purpose
To increase the win rate of the advisory engine by filtering out low-conviction setups and doubling down on catalyst-driven setups.

## Engineering Purpose
To build a scalable, asynchronous pipeline (`NewsService`, `SentimentService`, `LLMService`) that fetches recent articles, deduplicates/cleans them (partially implemented), and scores them via a Large Language Model (LLM) before the `RecommendationAgent` makes a final call.

## Real-World Examples
- **Positive Catalyst**: A stock breaks its 200 EMA resistance. Simultaneously, the News Analysis Engine detects a positive sentiment score (e.g., > 0.75) due to an earnings beat. The dynamic weights in `RecommendationService` shift to favor the news, upgrading the setup from WATCH to BUY.
- **Negative Divergence**: A stock looks technically bullish, but news indicates a regulatory probe (Sentiment < -0.80). The engine flags the invalidation risk and rejects the trade.