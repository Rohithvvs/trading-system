import os

docs_dir = r"F:\trading system01\trading system\docs\deep_dive\news_analysis"
os.makedirs(docs_dir, exist_ok=True)

files = {
    "01_business_problem.md": """# 01 Business Problem

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
""",
    "02_architecture.md": """# 02 Architecture

## Complete News Analysis Architecture
The News Analysis Engine is built as an asynchronous, agent-driven subsystem within the Orchestrator. 

### Components
1. **Agents**:
   - `NewsAnalysisAgent`: Orchestrates the fetching and summarization of news.
   - `RecommendationAgent`: Ingests the news sentiment to calculate final trade scores.
   - `OrchestratorAgent`: Triggers the `NewsAnalysisAgent` concurrently with backtesting and fundamental analysis via `asyncio.gather`.
2. **Services**:
   - `NewsService`: Fetches raw articles from an external API (or DuckDuckGo fallback).
   - `SentimentService`: Processes articles and hands them to the LLM for scoring.
   - `LLMService`: Interfaces with Groq API (or a fallback) to compute a float sentiment score [-1.0, 1.0].
3. **Data Schemas**:
   - `ArticleItem`: Normalizes raw API responses into a structured format.

### Execution Context
- The `OrchestratorAgent._analyze_symbol_post_bulk` method calls `safe_news_run` in a background thread to prevent blocking the async event loop.

## Mermaid Architecture Diagram

```mermaid
graph TD
    O[OrchestratorAgent] -->|asyncio.to_thread| N_A[NewsAnalysisAgent]
    N_A -->|fetch_recent_news| NS[NewsService]
    NS -.->|Primary| API[Configured News API]
    NS -.->|Fallback| DDG[DuckDuckGo API]
    N_A -->|summarize| SS[SentimentService]
    SS -->|analyze_sentiment| LLM[LLMService]
    LLM -.-> Groq[Groq API / Llama]
    N_A -->|returns articles, score, label| O
    O --> RA[RecommendationAgent]
    RA --> Final[Final Recommendation]
```
""",
    "03_execution_flow.md": """# 03 Execution Flow

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
""",
    "04_news_collection_pipeline.md": """# 04 News Collection Pipeline

## Where News Comes From
The pipeline relies on a primary configured News API and a fallback DuckDuckGo instant answers API.
- **Primary**: Endpoint configured via `settings.news_api_url`.
- **Fallback**: `https://api.duckduckgo.com/`

## How APIs are Called
In `NewsService.fetch_recent_news`:
- The primary API is queried using `requests.get` with the query `"q": f"{symbol} NSE news"`.
- If this fails (exception or invalid data), the exception is caught, and the fallback is triggered.
- The fallback queries DDG for related topics.

## Authentication
- Primary API: Uses `settings.news_api_key` injected into the query params.
- Fallback: No authentication required.

## Scheduling
- Fetched on-demand during the scanner's evaluation phase (`OrchestratorAgent.run_full`). No cron jobs or background schedulers are currently implemented for proactive news fetching.

## Rate Limits & Timeouts
- Timeouts: Enforced at `timeout=6` seconds for both APIs to prevent pipeline stalling.
- Rate limits: Handled passively (if rate limited, it raises an exception and hits the fallback).

## Deduplication & Storage
- **Deduplication**: Not implemented natively; relies on upstream uniqueness.
- **Storage**: In-memory only. The retrieved `ArticleItem` list is passed down the pipeline and ultimately returned in the API response, but the articles themselves are not persisted to a database.

## Examples
A query for "TCS" becomes "TCS NSE news", hitting `api.duckduckgo.com/?q=TCS+NSE+news&format=json&no_html=1&skip_disambig=1`.
""",
    "05_news_processing_pipeline.md": """# 05 News Processing Pipeline

## Cleaning and Filtering
- The `NewsService` extracts only the `title`, `description`, `source.name`, `url`, and `published_at` from the upstream API.
- The fallback DuckDuckGo API uses `no_html=1` to ensure raw text without HTML tags.
- Max 10 articles are preserved. 

## Normalization
- Raw JSON is converted into Pydantic `ArticleItem` schemas (`app/schemas/analysis.py`).
- Dates are parsed from ISO format; if missing, they default to `datetime.utcnow()`.
- Sentiment scores at the article level are initialized to `0.0` (overall sentiment is scored at the batch level later).

## Duplicate Detection
- Not implemented in repository.

## Language Handling
- Implicitly expects English. No translation layer exists.

## Ticker/Company Mapping
- The `symbol` is passed directly to the search query appended with `" NSE news"`. (e.g., `RELIANCE NSE news`).
- No explicit mapping from Ticker to formal Company Name (e.g., "TCS" -> "Tata Consultancy Services") is performed before the search.
""",
    "06_sentiment_analysis.md": """# 06 Sentiment Analysis

## How Sentiment is Determined
Sentiment is evaluated at the batch level rather than per-article. `SentimentService.summarize` extracts headlines from all `ArticleItem`s and passes them to `LLMService.analyze_sentiment`.

## Scoring
The LLM returns a single float (`sentiment_score`) between `-1.0` and `1.0`.

## Labeling
In `SentimentService.summarize`, the float score is mapped to a categorical label:
- **Positive**: `score >= 0.2`
- **Negative**: `score <= -0.2`
- **Neutral**: `-0.2 < score < 0.2`

## Keywords
Not implemented. The system relies entirely on the LLM's semantic understanding rather than keyword matching.

## Prompting
The `LLMService` uses the following system prompt for sentiment:
*"You are a quantitative sentiment analyzer. Respond with valid JSON only. Evaluate the following headlines for the given stock symbol and return a clean, minified JSON object containing a numeric 'sentiment_score' strictly bounded between -1.0 (highly catastrophic/bearish) and 1.0 (highly disruptive/bullish)."*

## Model Selection
If `settings.llm_provider` is "groq", it calls Groq's API using `settings.llm_model`.

## Real Examples
If 10 headlines show "Record profits for Q3", the LLM parses the JSON, outputs `{"sentiment_score": 0.85}`, and the label becomes `positive`.
""",
    "07_llm_integration.md": """# 07 LLM Integration

## Provider Configuration
- Uses **Groq** via `https://api.groq.com/openai/v1/chat/completions`.
- Triggered only if `settings.llm_provider.lower() == "groq"` and `settings.llm_api_key` is set.

## Prompt Structure
- **System**: Defines the persona ("quantitative sentiment analyzer" or "trading analysis assistant") and enforces JSON output.
- **User**: Passes the `Symbol` and `Headlines` (as a JSON dumped string).

## Input and Output
- **Input**: A list of strings (headlines).
- **Output**: JSON containing `sentiment_score` (float). For reasoning, it outputs `bullets`, `risk_factors`, `invalidation_signals`, and `summary`.
- **Response Format**: Uses `"response_format": {"type": "json_object"}` to guarantee JSON.

## Response Validation & Fallback Strategy
- The payload is parsed via `json.loads`.
- If the `sentiment_score` key is missing, it defaults to `0.0`.
- The score is clamped using `max(-1.0, min(1.0, score))` to prevent rogue LLM outputs.
- **Fallback**: If the Groq API fails, times out (`timeout=10`), or throws an exception, `LLMService` catches it, logs `"LLM sentiment analysis failed"`, and returns `0.0`. No retry logic is implemented.

## Cost Considerations
- Groq is utilized for fast, low-cost inference. The prompt is kept minimal ("clean, minified JSON object") to reduce token usage.
""",
    "08_news_scoring.md": """# 08 News Scoring

## How News Affects Stock Scores
News sentiment directly impacts the final stock score via the `RecommendationService`.

## Weighting and Thresholds
In `RecommendationService.calculate_dynamic_weights`, a dynamic weighting system is used:
- **Standard Regime**: Technical (50%), Fundamental (25%), Backtest (25%), News (0%).
- **Catalyst Regime**: Triggered if `abs(sentiment_score) >= 0.75` (or high volume).
  - If a catalyst is active, the weights shift to: News (30%), Fundamental (30%), Technical (20%), Backtest (20%).

## Score Calculation
- The raw news score (`sentiment_score * 100`) is multiplied by the dynamic weight (`news_wt`).
- E.g., a sentiment score of `0.80` during a catalyst regime contributes `80 * 0.30 = 24` points to the final 100-point scale.

## Examples
- A stock has a technical score of 80. Sentiment is `0.90` (Catalyst triggered). 
- News Weight becomes 30%. News contributes `90 * 0.30 = 27` points. 
- Technical weight drops to 20%, contributing `80 * 0.20 = 16` points.
- This allows a strong news catalyst to carry a moderately technical setup into a `BUY`.
""",
    "09_signal_generation.md": """# 09 Signal Generation

## Sentiment Contribution
The sentiment score feeds directly into `FinalRecommendation`.

## Dependency Chain
1. `NewsService` fetches raw articles.
2. `SentimentService` calculates float score via `LLMService`.
3. `RecommendationService.build` evaluates:
   - If `sentiment_score >= 0.75` or `<= -0.75`, it triggers **Catalyst Regime**.
   - Applies dynamic weights.
   - Calculates total score out of 100.
4. Thresholds applied to Total Score:
   - `>= 72` -> **BUY**
   - `>= 55` -> **WATCH**
   - `< 55` -> **REJECT**

## Reasoning Generation
The `LLMService.build_reasoning` incorporates the `news_label` (e.g., "positive", "negative") into the prompt context to generate readable risk factors and summaries explaining *why* the signal was generated.
""",
    "10_dependencies.md": """# 10 Dependencies

The News Analysis Engine is deeply integrated into the Orchestrator flow.

## 1. Market Data (FyersService)
News is not processed in isolation. The `RecommendationService` looks at the latest volume from the OHLCV candles (provided by `FyersService`) to see if the news correlates with a volume spike (`current_volume > avg_volume * 3.0`).

## 2. Technical Analysis Engine
News scoring weights are blended with the `TechnicalAnalysisResult`. 

## 3. Recommendation Engine
The final consumer of the News Engine.

## 4. Database
`AnalysisHistory` stores the final `sentiment_score`. (No Redis caching is used).

## 5. Schedulers
Not implemented. Orchestrator triggers news on-the-fly sequentially per symbol.

## 6. External APIs
- Groq API (LLM inference)
- DuckDuckGo (Fallback web search)
- Custom News API endpoint (Configured via env vars)
""",
    "11_edge_cases.md": """# 11 Edge Cases

## No News Available
- **What happened**: APIs return empty results.
- **Expected behavior**: Gracefully continue without news.
- **Actual implementation**: `NewsAnalysisAgent` detects empty lists and returns `[], 0.5, "Neutral", "No recent news found"`.

## API Timeout
- **What happened**: Custom API or DDG takes too long.
- **Expected behavior**: Fast fail.
- **Actual implementation**: Both `requests.get` use `timeout=6`. Exceptions are caught and ignored (returns `[]`).

## Duplicate Articles
- **Actual implementation**: Not implemented in repository. Returns whatever the API provides.

## Conflicting News / Fake News
- **Actual implementation**: Handled implicitly by the LLM which averages sentiment. No specific fake news detection.

## LLM Unavailable
- **Actual implementation**: `requests.post` timeout or 5xx. Exception caught in `LLMService`, logs error, returns `0.0`.

## Ticker Mapping Failures
- **Actual implementation**: Appends " NSE news" to the ticker. If the ticker is obscure, DDG might return irrelevant topics. No rigorous validation exists.
""",
    "12_failure_scenarios.md": """# 12 Failure Scenarios

## Production Failures

### 1. Groq Rate Limiting (HTTP 429)
- **Symptoms**: Sentiment scores consistently default to `0.0`. Logs show `LLM sentiment analysis failed: 429 Client Error`.
- **Root Cause**: Processing a large screener batch concurrently overwhelms the Groq API limits.
- **Recovery**: Automatic fallback to `0.0`. No retry logic exists. 
- **Monitoring**: Check `app.llm_service` logs for exceptions.

### 2. Upstream News API Outage
- **Symptoms**: Pipeline falls back to DuckDuckGo, pulling web search results instead of financial news.
- **Root Cause**: Timeout or 5xx from `settings.news_api_url`.
- **Recovery**: Best-effort degradation to DDG.

### 3. Thread Pool Exhaustion
- **Symptoms**: `asyncio.to_thread` in Orchestrator hangs or is slow.
- **Root Cause**: `safe_news_run` is synchronous and makes HTTP requests. Too many symbols screened simultaneously can exhaust the default thread pool.
- **Recovery**: Restart backend.
""",
    "13_debugging_guide.md": """# 13 Debugging Guide

## Debugging Workflow
If News Analysis behaves incorrectly (e.g., always returning neutral, or crashing the screener):

### 1. Inspect Logs
- Check `logs/` directory (or stdout).
- Grep for `app.sentiment` to see LLM failures.
- Grep for `app.llm_service` to catch 4xx/5xx from Groq.

### 2. Inspect Files
- `app/services/news_service.py`: To verify the API URL and DDG fallback.
- `app/services/llm_service.py`: To check prompt structure and Groq connection.

### 3. Test API Connections
Run manual `requests` calls to:
- `settings.news_api_url`
- `api.duckduckgo.com`
- `api.groq.com`

### 4. Database Verification
- Check the `analysis_history` table:
  `SELECT symbol, sentiment_score FROM analysis_history ORDER BY id DESC LIMIT 10;`
- If scores are all exactly `0.0` or `0.5`, the LLM or News Service is failing silently.
""",
    "14_performance_and_scaling.md": """# 14 Performance & Scaling

## Batch Processing & Concurrency
- Technical Analysis is vectorized and processed in bulk prior to news fetching.
- News fetching runs inside `asyncio.gather` for the shortlisted batch of symbols in `OrchestratorAgent.run_full`.
- `safe_news_run` uses `asyncio.to_thread` to prevent the synchronous `requests.get` from blocking the async event loop.

## Caching
- **Not implemented**. 
- Calling the screener twice for the same symbol will trigger duplicate HTTP requests to the News API and Groq. 

## API Optimization
- The LLM payload uses `response_format: {"type": "json_object"}` to force a fast, minimal JSON output, minimizing token generation time.
- The news APIs are restricted with aggressive timeouts (`6` seconds).

## Future Scaling Needs
- Implement Redis caching (`news:{symbol}`) with a 15-minute TTL to reduce redundant API calls and rate-limit risks on Groq.
""",
    "15_database_interactions.md": """# 15 Database Interactions

## Overview
The News Analysis Engine does not have its own dedicated tables. It persists its output as part of the broader `AnalysisHistory` record.

## Tables

### 1. `analysis_history`
- **Purpose**: Stores the final results of a full analysis run.
- **Queries**: Inserted inside `OrchestratorAgent._persist_analysis`.
- **Columns of Interest**:
  - `sentiment_score` (Float): The final score [-1.0, 1.0] generated by the LLM.
  - `reasoning` (Text): Contains the LLM-generated summary, which incorporates the news label.

### 2. `watched_stocks`
- **Purpose**: Ensures the symbol exists in the system before recording history.
- **Relationships**: `analysis_history` belongs to `watched_stocks` (via `stock_id`).

## Persistence Strategy
Write-only. The system does not currently query the database to retrieve past news or historical sentiment for trend analysis.
""",
    "16_cache_interactions.md": """# 16 Cache Interactions

## Overview
**Not implemented in repository.**

Currently, there are no Redis interactions, cache keys, or TTLs defined for the News Analysis Engine. 
Every time a symbol is analyzed, live HTTP requests are dispatched.
""",
    "17_api_interactions.md": """# 17 API Interactions

## 1. Custom News API
- **URL**: `settings.news_api_url + "/search"`
- **Authentication**: `api_key` in query params.
- **Format**: `GET ?q={symbol} NSE news&api_key={key}`
- **Retries/Timeout**: No retries. 6-second timeout.

## 2. DuckDuckGo API (Fallback)
- **URL**: `https://api.duckduckgo.com/`
- **Authentication**: None.
- **Format**: `GET ?q={symbol} NSE news&format=json&no_html=1&skip_disambig=1`
- **Retries/Timeout**: No retries. 6-second timeout.

## 3. Groq API
- **URL**: `https://api.groq.com/openai/v1/chat/completions`
- **Authentication**: Bearer Token (`settings.llm_api_key`)
- **Format**: `POST` with JSON payload containing `model`, `messages`, and `response_format`.
- **Retries/Timeout**: No retries. 10-second timeout for sentiment, 20-second for reasoning.
""",
    "18_code_walkthrough.md": """# 18 Code Walkthrough

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
""",
    "19_sequence_diagrams.md": """# 19 Sequence Diagrams

## Normal Flow

```mermaid
sequenceDiagram
    participant O as OrchestratorAgent
    participant NA as NewsAnalysisAgent
    participant NS as NewsService
    participant SS as SentimentService
    participant LLM as LLMService
    participant RA as RecommendationAgent

    O->>NA: run(symbol)
    NA->>NS: fetch_recent_news(symbol)
    NS-->>NA: List[ArticleItem]
    NA->>SS: summarize(symbol, articles)
    SS->>LLM: analyze_sentiment(headlines)
    LLM-->>SS: 0.85
    SS-->>NA: (0.85, "positive", "Summary...")
    NA-->>O: Tuple result
    O->>RA: run(..., sentiment_score=0.85, ...)
    RA-->>O: FinalRecommendation
```

## API Failure / Fallback

```mermaid
sequenceDiagram
    participant NS as NewsService
    participant API as Custom API
    participant DDG as DuckDuckGo

    NS->>API: GET /search (timeout=6)
    API--xNS: Timeout Exception
    NS->>DDG: GET /?q=...
    DDG-->>NS: JSON Topics
    NS-->>NewsAnalysisAgent: List[ArticleItem] (from web search)
```
""",
    "20_learning_notes.md": """# 20 Learning Notes for Developers

## Most Important Concepts
- **Dynamic Weighting**: The system does not statically weigh news. If sentiment exceeds `0.75` (catalyst regime), the `RecommendationService` re-allocates weights, allowing news to override mediocre technicals.
- **Fail-Safe Design**: Every component (`NewsService`, `LLMService`) is wrapped in broad `except Exception:` blocks that return safe defaults (`[]` or `0.0`). The system prioritizes keeping the screener alive over perfect data.

## Common Misconceptions
- *Misconception*: "The system parses article bodies." -> *Reality*: It only parses headlines.
- *Misconception*: "News is fetched for every stock." -> *Reality*: Due to API limits, news is only fetched for the shortlisted stocks (top N) *after* technical filtering.

## Architecture Decisions
- **Async via Threading**: Standard `requests` is used instead of `aiohttp`. To prevent blocking the async loop, the orchestrator wraps it in `asyncio.to_thread`.
- **Batch Sentiment vs Item Sentiment**: To save LLM tokens, all 10 headlines are passed to the LLM in one prompt to get a single macro score, rather than scoring each article individually.

## Suggested Learning Order
1. Read `news_service.py` to understand the HTTP gathering.
2. Read `llm_service.py` to see the JSON prompting strategy.
3. Read `recommendation_service.py` -> `calculate_dynamic_weights` to understand the business logic impact.
"""
}

for filename, content in files.items():
    with open(os.path.join(docs_dir, filename), "w", encoding="utf-8") as f:
        f.write(content.strip())

print("Successfully generated all 20 documentation files.")
