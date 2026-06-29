# Recommendation Engine: API Dependencies

The engine relies on external data providers to feed its algorithms.

## 1. FYERS API
- **Purpose:** The primary source of truth for market data (Historical OHLCV and Live Websocket Ticks).
- **Service:** `FyersService`, `MarketDataFeed`.
- **Rate Limits & Retries:** FYERS has strict limits on historical data calls (e.g., max 100 days per call for 1-minute data, rate limits per second). The system handles this using local caching (`candle_cache.db`) and exponential backoff retry loops.
- **Timeout:** Highly responsive, but timeouts trigger the system to fall back to `mock_warning=True`.

## 2. Yahoo Finance (yfinance)
- **Purpose:** Fetches fundamental financial data (PE ratio, revenue growth, debt-to-equity).
- **Service:** `FundamentalAnalysisAgent`.
- **Rate Limits & Retries:** Subject to Yahoo's unlisted rate limits. If a 404 is encountered (e.g. symbol mismatch), it catches the exception and returns a neutral fundamental score (`0.0`). No aggressive retries are implemented to avoid IP bans.
- **Timeout:** Standard HTTP timeouts apply.

## 3. Groq (OpenAI Compatible LLM API)
- **Purpose:** Analyzes news sentiment and generates human-readable reasoning paragraphs.
- **Service:** `LLMService`.
- **Timeout:** Sentiment analysis has a hard `10s` timeout; Reasoning generation has a `20s` timeout. 
- **Retry Strategy:** Fails fast. If the API times out, the system instantly falls back to a deterministic text generator (`_fallback_reasoning()`) rather than pausing the recommendation pipeline.
