# API Interactions

The Scanner Engine is heavily dependent on external APIs, primarily the FYERS API for market data.

## 1. FYERS API (Market Data)
The entire scanner relies on accurate historical OHLCV (Open, High, Low, Close, Volume) data.

- **Component**: `FyersService`
- **Authentication**: Requires an Access Token passed in the `Authorization` header.
- **Request Format**: 
  - Resolves symbol formats (e.g., `NSE:RELIANCE-EQ`).
  - Fetches historical data endpoints (e.g., `history/`).
- **Rate Limiting**: 
  - FYERS imposes strict rate limits on historical data requests.
  - The scanner uses a `TokenBucketRateLimiter` (`_rate_limiter`) configured to 5 calls per second in `ScreenerService`.
- **Timeout Handling**: API calls are wrapped in `asyncio.wait_for` to prevent hanging requests.
- **Retry Logic**: If the API returns a transient error or timeout, the service may attempt a retry or gracefully degrade the symbol to `data_source_failed`.
- **Error Handling**: Custom exceptions are raised (`FyersAuthExpiredError`, `FyersRateLimitError`, `FyersAPIError`).

## 2. Yahoo Finance (Fallback API)
If the FYERS API fails or is unconfigured, the system attempts to fetch data from Yahoo Finance.

- **Component**: `ScreenerService.fallback_fetch_yfinance()`
- **Request Format**: Translates symbols (e.g., `NSE:RELIANCE-EQ` to `RELIANCE.NS`).
- **Execution**: Uses `asyncio.to_thread` to wrap the synchronous `yfinance` library call.
- **Limitations**: Slower, subject to strict IP bans if overused, and sometimes inaccurate for Indian market volume data.

## 3. News APIs
Used during the deep analysis phase for shortlisted stocks.

- **Component**: `NewsAnalysisAgent`
- **Request Format**: Fetches recent articles based on the stock ticker.
- **Handling**: Wraps calls in `try/except`. If the API fails or times out, it degrades gracefully by returning a neutral sentiment score (`0.5`) and an empty article list, allowing the scanner to complete without crashing.
