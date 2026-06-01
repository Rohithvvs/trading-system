# E4.1 Risk Analysis

## Risks Introduced
1. **Database Resource Pressure**: By increasing the SQLAlchemy sync engine's connection pool size to 80 and maximum overflow to 20, the system may open up to 100 concurrent connections to PostgreSQL. If the PostgreSQL server's `max_connections` configuration is not suitably high (e.g., >= 200, allowing headroom for async connections and other services), this can lead to connection exhaustion at the database level. Additionally, 100 concurrent active transactions will increase the memory footprint of the database.
2. **Aggressive Pricing Fallbacks**: Reducing the timeout in `_price_snapshot` from 5 seconds to 2 seconds means that minor network latency spikes or transient FYERS API degradation will more frequently trigger the timeout. 
3. **Increased Backend CPU Load**: Allowing 100 AnyIO threads to process concurrently increases the CPU overhead on the backend host during peak burst traffic.

## Mitigations
1. **Database Capacity Check**: PostgreSQL settings should be validated to ensure `max_connections` allows for the 100 sync connections plus all async connections. A pooler like `PgBouncer` could be introduced in the future if limits are reached.
2. **Pricing Resilience**: The paper trading service natively includes failover paths when `fetch_ltp` fails (e.g., falling back to the close price of the most recent candle). This ensures that while we may miss the absolute live tick during a 2-second timeout, the system remains functionally stable and gracefully falls back to the most recent known data point.
3. **Hardware Provisioning**: Monitor the host's CPU usage to ensure it can comfortably handle 100 concurrent execution threads without thermal or CPU throttling.

## Expected Performance Gain
- **Elimination of Starvation**: The 1:1 synchronization between AnyIO and the DB pool acts as a hard guarantee that AnyIO threads will not be starved waiting for a database connection.
- **Reduction in Idle-in-Transaction Time**: The 2-second timeout fail-fast mechanism substantially trims the maximum duration of the `FOR UPDATE` lock held during market order execution, unlocking massive concurrency throughput gains even before Phase E4.3 is implemented.
- **Predictable Degradation**: By eliminating random 10-second client timeouts and lockups during burst traffic, the system will degrade predictably and reliably handle up to 100 concurrent requests smoothly.
