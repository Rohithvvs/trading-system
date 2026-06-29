# 18 Code Walkthrough

## 1. `backend/app/agents/news_analysis_agent.py`
- **Purpose**: Facade for news operations.
- **Classes**: `NewsAnalysisAgent`
- **Methods**: `run(symbol)`
- **Flow**: Called by Orchestrator. Calls `NewsService`, then `SentimentService`.

## 2. `backend/app/services/news_service.py`
- **Purpose**: Network I/O for raw articles.
- **Classes**: `NewsService`
- **Methods**: `fetch_recent_news(symbol)`
- **Flow**: Returns list of `ArticleItem`.

## 3. `backend/app/services/sentiment_service.py`
- **Purpose**: Business logic mapping LLM floats to labels.
- **Classes**: `SentimentService`
- **Methods**: `summarize(symbol, articles)`
- **Flow**: Calls `LLMService.analyze_sentiment`. Converts to `positive/negative/neutral`.

## 4. `backend/app/services/llm_service.py`
- **Purpose**: AI model interaction.
- **Classes**: `LLMService`
- **Methods**: `analyze_sentiment`, `build_reasoning`
- **Flow**: Executes Groq HTTP requests. Returns floats and JSON dicts.

## 5. `backend/app/agents/recommendation_agent.py`
- **Purpose**: The final consumer. Calculates dynamic weights using sentiment score.