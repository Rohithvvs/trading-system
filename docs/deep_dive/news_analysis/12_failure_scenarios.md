# 12 Failure Scenarios

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