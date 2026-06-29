# Recommendation Engine: Cache Usage

The system utilizes caching heavily to bypass slow external APIs and prevent rate-limiting.

## 1. SQLite Candle Cache (`candle_cache.db`)
While often mistaken for Redis, the primary OHLCV cache is actually a dedicated local SQLite file.
- **Usage:** Stores massive blocks of 1D (daily) candles for the NIFTY 500.
- **Refresh / Invalidation:** Managed by `candle_store.py`. The Orchestrator calls `is_cache_fresh()`. If stale, it triggers a bulk sync via `FyersService`.

## 2. Redis Usage
Redis is configured in the environment (`settings.redis_url`) but is **strictly used for Distributed Locking**.
- **Keys:** e.g., `market_feed:lock`, `token_refresh:fence`
- **Purpose:** Prevents race conditions. For example, if multiple backend instances attempt to start the `MarketEngineService` loop simultaneously, Redis ensures only one instance connects to the Websocket stream.
- **TTL:** Locks are granted with an expiration (e.g. `ex=timeout`) to prevent deadlocks if an instance crashes.

## 3. In-Memory Cache
- `TechnicalAnalysisService` computes everything on-the-fly (no disk cache for indicators) to ensure real-time accuracy based on the latest tick.
- `FyersService` keeps an in-memory dictionary of the most recent access tokens to avoid hitting the Postgres DB on every single API request.
