# 03 Execution Flow

## Overview
The execution flow is triggered per symbol after the bulk technical analysis completes.

## Step-by-Step Flow

1. **News Source (`OrchestratorAgent` -> `NewsAnalysisAgent`)**
   - **Purpose**: Initiates the news gathering for a given symbol.
   - **Input**: `symbol` (e.g., "RELIANCE")
   - **Output**: Tuple of `(articles, score, label, summary)`
   - **Dependencies**: `NewsService`, `SentimentService`

2. **API Call (`NewsService.fetch_recent_news`)**
   - **Purpose**: Fetch raw news articles.
   - **Input**: `symbol`
   - **Output**: List of `ArticleItem`
   - **Details**: Tries custom news API (`/search` endpoint). If it fails, falls back to DuckDuckGo instant answers.

3. **Validation & Cleaning**
   - **Implementation**: Handled minimally in `NewsService`. It maps JSON responses to `ArticleItem` schemas, truncating to a maximum of 10 articles. Missing dates default to `datetime.utcnow()`.
   
4. **Deduplication**
   - **Implementation**: Not explicitly implemented in repository beyond trusting the upstream API's top 10 results.

5. **Sentiment Analysis (`SentimentService.summarize`)**
   - **Purpose**: Convert headlines to a score and label.
   - **Input**: List of `ArticleItem`
   - **Output**: `score` (float), `label` (string), `summary` (string)
   - **Dependencies**: `LLMService.analyze_sentiment`

6. **Scoring (`LLMService.analyze_sentiment`)**
   - **Purpose**: Query the LLM to rate sentiment.
   - **Input**: List of headlines.
   - **Output**: `sentiment_score` (-1.0 to 1.0)
   
7. **Recommendation Engine (`RecommendationAgent.run`)**
   - **Purpose**: Combine news sentiment with technicals to make a BUY/WATCH/REJECT decision.
   - **Input**: `sentiment_score`, `sentiment_label`, technicals, backtests.
   - **Output**: `FinalRecommendation`