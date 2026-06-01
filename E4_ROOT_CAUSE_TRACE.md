# PHASE E.4 ROOT CAUSE TRACE

## Objective
Prove the exact deadlock path by tracing a MARKET BUY request and identifying the true source of the system hang.

---

## 1. Trace Path

*   **HTTP Request:** `POST /api/v1/paper-trading/orders`
*   **Route:** `backend/app/routes/paper_trading.py` (Line 161)
    ```python
    @router.post("/orders", response_model=PaperOrderActionResponse)
    def place_order(
        payload: PaperOrderCreateRequest,
        ...
        service: PaperTradingService = Depends(get_service),
    )
    ```
*   **Service:** `backend/app/services/paper_trading_service.py` (Line 144)
    ```python
    def place_order(self, payload: PaperOrderCreateRequest) -> PaperOrderActionResponse:
    ```
*   **Price Snapshot:** `backend/app/services/paper_trading_service.py` (Line 170)
    ```python
    price = self._price_snapshot(payload.symbol)
    ```
*   **Blocking Call:** `backend/app/services/paper_trading_service.py` (Line 1078)
    ```python
    future = asyncio.run_coroutine_threadsafe(self.fyers_service.fetch_ltp(symbol), main_event_loop)
    ltp = future.result(timeout=5)
    ```
*   **FYERS Call:** `backend/app/services/fyers_service.py` (Line 130)
    ```python
    async def fetch_ltp(self, symbol: str) -> float | None:
    ```

---

## 2. Threading & Resource State Analysis

Under a load of 50 concurrent requests, the system state is as follows:

*   **Executing Thread:** Starlette's `anyio.to_thread` worker pool (FastAPI's default thread pool for synchronous routes).
*   **Waiting Thread:** The `anyio` worker thread blocks via `.result(timeout=5)` while keeping the sync database connection checked out.
*   **Event Loop Involved:** The main Uvicorn ASGI event loop (`main_event_loop`).
*   **Resource Blocked:**
    1.  **AnyIO Thread Pool:** Max workers default is 40. 50 incoming requests immediately exhaust the pool.
    2.  **Sync DB Connection Pool:** Size is 30 (20 + 10 overflow). 30 AnyIO workers get a connection, while 10 AnyIO workers permanently block inside `SessionLocal()` waiting for a connection to be returned.
    3.  **PostgreSQL Row Lock:** Inside `_get_or_create_account(for_update=True)`, 1 worker holds the row lock. 29 workers block in PostgreSQL waiting for the transaction to release the lock.

---

## 3. Deadlock Determination

**Question:** Is `run_coroutine_threadsafe(...).result()` the actual deadlock source, or is another layer responsible?

**Determination:** Another layer is responsible. `run_coroutine_threadsafe` is **NOT** the source of a true circular deadlock.

**Proof:**
1.  Thread 1 reaches `run_coroutine_threadsafe` and blocks.
2.  The `main_event_loop` receives the `fetch_ltp` coroutine.
3.  Because `fetch_ltp` uses native `asyncpg` (which has a separate async connection pool of 30) and `FyersService._network_pool` (a separate ThreadPoolExecutor with 20 workers), it **does not require an AnyIO worker thread to complete**.
4.  Therefore, the `main_event_loop` successfully executes the coroutine and returns the result to Thread 1.
5.  Thread 1 unblocks, commits its transaction (freeing the Postgres row lock), and returns the HTTP response (freeing the AnyIO thread and DB connection).

**The Actual Root Cause (Catastrophic Serialization):**
The system is not circularly deadlocked; it is suffering from **Thread Pool Starvation and Extreme Lock Serialization**. Because all concurrent requests are forced to queue sequentially behind the `PaperTradingAccount` row lock, and because the AnyIO thread pool and Sync DB pool are fully exhausted, the requests process linearly.

If Thread 1 takes 500ms to fetch the LTP and commit, Thread 2 takes 1.0s, and Thread 50 takes 25.0 seconds. Because the client HTTP connection has a standard timeout of 10 seconds, the load tester abandons the requests (resulting in 100% timeouts/exceptions), leading to the illusion of a total system hang/deadlock.

---

## FINAL CONCLUSION

**ROOT_CAUSE_CONFIRMED**
