# Feature Inventory And Test Coverage

Coverage status is intentionally conservative. A check means this foundation includes at least one focused test for that level.

| Feature | Persistence | Unit | Integration/API | E2E | Persistence Verified | Live FYERS |
|---|---|---:|---:|---:|---:|---:|
| App shell and navigation | React memory |  |  | Yes | N/A | N/A |
| FYERS access token save/status/history | SQLite: `fyers_tokens`, `fyers_token_history` | Yes | Yes | Yes | Yes | Optional |
| FYERS live quote check | External FYERS API |  |  |  | N/A | Yes, manual |
| Scanner run flow | API response plus React memory |  | Yes with mocked agent | Yes with mocked browser response | Partial |
| Latest scanner result restore | SQLite: `latest_scan` in `scan_result.db` |  | Yes |  | Yes | N/A |
| Scan history snapshots | SQLite: `scan_history_snapshots` |  | Yes |  | Yes | N/A |
| Saved scanner presets | SQLite: `saved_scans` |  | Planned |  | Planned | N/A |
| Browser scan history | Browser `localStorage.scanHistory` |  |  | Yes | Yes | N/A |
| Paper trading account reset/dashboard | SQLite: `paper_trading_accounts` |  | Yes | Yes | Yes | Uses mocked/isolated pricing in normal tests |
| Paper trading order placement | SQLite: `paper_trading_orders`, `paper_trading_positions`, `paper_trading_transactions` |  | Yes | Yes | Yes | Optional via app pricing services |
| Paper position update/close/square-off | SQLite paper trading tables |  | Planned |  | Planned | Optional |
| Paper alerts/notifications | SQLite: `paper_trading_alerts`, `paper_trading_notifications` |  | Planned |  | Planned | Optional |
| Paper analytics/transactions | SQLite: `paper_trading_trade_history`, `paper_trading_transactions` |  | Planned |  | Planned | N/A |
| Workstation market overview | Derived service response |  | Planned |  | N/A | Optional |
| Workstation alerts/risk settings | SQLite: `workstation_alerts`, `risk_settings` |  | Planned |  | Planned | N/A |
| Gap replay after restart | SQLite paper trading tables plus backend state file | Existing focused tests | Existing tests |  | Yes | Uses fake FYERS candles |

## Known Gaps

- The normal E2E scanner test mocks the browser response to stay deterministic. Backend integration separately verifies that `/analysis/screener/full` persists scan history and latest scan data.
- Full restart persistence is represented by reload-level E2E checks and SQLite diagnostics. A future release can add a Playwright global setup that stops and restarts the backend process mid-test.
- SQLite is supported now. The test helpers inspect through SQLAlchemy and test diagnostics so a future Postgres migration can keep similar test contracts with different database plumbing.
