# 14 Performance & Scaling

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