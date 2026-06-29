# 20 Learning Notes for Developers

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