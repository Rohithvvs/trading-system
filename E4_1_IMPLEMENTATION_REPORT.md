# E4.1 Implementation Report

## Files Changed
1. `backend/app/main.py`
2. `backend/app/db/session.py`
3. `backend/app/services/paper_trading_service.py`

## Exact Changes
1. **AnyIO Thread Pool Synchronization**:
   In `backend/app/main.py`, updated the `anyio` default thread limiter to 100 tokens inside the `lifespan` context manager:
   ```python
   limiter = anyio.to_thread.current_default_thread_limiter()
   limiter.total_tokens = 100
   ```
2. **SQLAlchemy Connection Pool Sizing**:
   In `backend/app/db/session.py`, updated the `sync_engine` connection pool size to match the thread pool capacity (Total 100):
   ```python
   sync_pool_kwargs["pool_size"] = 80
   sync_pool_kwargs["max_overflow"] = 20
   ```
3. **Fail-fast Market Data Timeout**:
   In `backend/app/services/paper_trading_service.py`, reduced the timeout for fetching live prices in `_price_snapshot` from 5 seconds to 2 seconds:
   ```python
   future = asyncio.run_coroutine_threadsafe(self.fyers_service.fetch_ltp(symbol), main_event_loop)
   ltp = future.result(timeout=2)
   ```

## Rationale
- **Thread Pool & DB Connection Parity**: FastAPI routes executing synchronous operations use the AnyIO thread pool. If the thread pool is larger than the available DB connections, or traffic spikes, threads will block indefinitely waiting for a database connection to become free, leading to thread pool starvation. Synchronizing both the AnyIO thread limit and the SQLAlchemy connection pool to exactly 100 ensures a 1:1 parity so that no AnyIO thread ever blocks waiting for a DB connection.
- **Database Contention Mitigation**: In the paper trading system, market data fetches currently execute inside the scope of a PostgreSQL lock. Reducing the timeout to 2 seconds ensures the system fails fast during FYERS API degradation, thereby preventing prolonged transaction times and severe database contention. 

## Rollback Steps
1. Revert `backend/app/main.py` to remove the manual `total_tokens` override on the `current_default_thread_limiter()`.
2. Revert `backend/app/db/session.py` by removing `sync_pool_kwargs["pool_size"] = 80` and `sync_pool_kwargs["max_overflow"] = 20`.
3. Revert `backend/app/services/paper_trading_service.py` to restore `future.result(timeout=5)`.
