# 04 News Collection Pipeline

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