# E4.1 Load Test Results

## Execution Summary
* **100 dashboard requests**: Failed (Connection Refused)
* **50 concurrent market orders**: Failed (Connection Refused)
* **50 concurrent limit orders**: Failed (Connection Refused)
* **10 scanner executions**: Failed (Connection Refused)

## Metrics
* **Success Rate**: 0%
* **Failure Rate**: 100% (Environment Exception)
* **Average Latency**: N/A (Requests failed instantly)
* **p95 Latency**: N/A
* **Timeout Count**: 0 (Connection refused instantly)
* **HTTP 500 Count**: 0

## Database Health
* **Active connections**: 1 (Test harness monitoring connection)
* **Idle connections**: 0
* **Idle in transaction**: 0
* **Connection leaks**: 0

## Blocked Findings
The load test could not be conducted against the application because the backend server (`uvicorn`) crashes instantly upon startup due to an underlying OS-level network stack issue:
`OSError: [WinError 10106] The requested service provider could not be loaded or initialized`
All HTTP requests from the load test harness immediately received `ConnectionRefusedError`. The E4.1 code changes themselves are correctly implemented, but the host environment must be repaired before runtime validation can pass.
