# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: paper-trading-read-architecture.spec.ts >> Paper Trading Read Architecture >> dashboard endpoint aggregates all data correctly
- Location: e2e\paper-trading-read-architecture.spec.ts:211:3

# Error details

```
Error: expect(received).toHaveProperty(path)

Expected path: "workspace"
Received path: []

Received value: {"account": {"account_id": 1, "account_name": "Primary Paper Account", "available_cash": 1000000, "balance": 1000000, "base_currency": "INR", "equity": 1000000, "max_risk_per_trade": 0.02, "open_orders_count": 1, "open_positions_count": 0, "realized_pnl": 0, "reserved_cash": 0, "starting_balance": 1000000, "total_invested": 0, "unrealized_pnl": 0, "updated_at": "2026-05-19T04:05:54.791597Z"}, "open_orders": [{"created_at": "2026-05-19T04:05:54.439539", "filled_at": null, "filled_price": null, "id": 1, "is_price_stale": true, "last_evaluated_at": "2026-05-19T04:05:54.717487", "last_seen_ltp": 0, "lifecycle_state": "PENDING_ENTRY", "monitor_enabled": true, "notes": "dashboard test buy", "paused_reason": null, "price": 0, "price_fetched_at": "2026-05-19T04:05:54.788943Z", "price_source": "NO_DATA", "product_type": "CNC", "qty": 3, "requested_entry_price": 0, "side": "BUY", "source_confidence": null, "source_score": null, "source_signal": null, "status": "PENDING", "stop_loss": null, "stop_price": null, "symbol": "INFY-EQ", "target": null, "type": "MARKET"}], "order_history": [{"created_at": "2026-05-19T04:05:54.439539", "filled_at": null, "filled_price": null, "id": 1, "is_price_stale": true, "last_evaluated_at": "2026-05-19T04:05:54.717487", "last_seen_ltp": 0, "lifecycle_state": "PENDING_ENTRY", "monitor_enabled": true, "notes": "dashboard test buy", "paused_reason": null, "price": 0, "price_fetched_at": "2026-05-19T04:05:54.788943Z", "price_source": "NO_DATA", "product_type": "CNC", "qty": 3, "requested_entry_price": 0, "side": "BUY", "source_confidence": null, "source_score": null, "source_signal": null, "status": "PENDING", "stop_loss": null, "stop_price": null, "symbol": "INFY-EQ", "target": null, "type": "MARKET"}], "positions": [], "selected_workspace": {"candles": [], "current_price": 0, "ema_20": null, "is_price_stale": true, "price_fetched_at": "2026-05-19T04:05:54.788943Z", "price_source": "NO_DATA", "source_confidence": null, "source_score": null, "source_signal": null, "supertrend": null, "symbol": "INFY-EQ"}, "symbols": ["360ONE-EQ", "3MINDIA-EQ", "ABB-EQ", "ACC-EQ", "ACMESOLAR-EQ", "AIAENG-EQ", "APLAPOLLO-EQ", "ASKAUTOLTD-EQ", "AUBANK-EQ", "AWL-EQ", …], "trades": []}
```

# Test source

```ts
  131 |     const sellTrade = dbHistory.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "SELL");
  132 |     expect(buyTrade).toBeDefined();
  133 |     expect(sellTrade).toBeDefined();
  134 |   });
  135 | 
  136 |   test("lifecycle state and paused labels render from API response", async ({ page, request }) => {
  137 |     await page.goto("/");
  138 |     await page.getByTestId("nav-paper-trading").click();
  139 | 
  140 |     // Fetch the dashboard/account to check lifecycle metadata and balances
  141 |     const dashRes = await request.get(`${apiBaseURL}/paper-trading/dashboard`);
  142 |     expect(dashRes.ok()).toBeTruthy();
  143 |     const dashboard = await dashRes.json();
  144 |     const account = dashboard.account;
  145 | 
  146 |     // Verify account has expected fields (updated API shape)
  147 |     expect(account).toHaveProperty("starting_balance");
  148 |     expect(account).toHaveProperty("balance");
  149 |     expect(account).toHaveProperty("realized_pnl");
  150 | 
  151 |     // Check Account tab for workspace display
  152 |     await page.getByTestId("paper-tab-account").click();
  153 |     await page.waitForTimeout(500);
  154 | 
  155 |     // Verify account info displays
  156 |     const balanceText = await page.locator('[data-testid="account-balance"]').textContent();
  157 |     expect(balanceText).toBeTruthy();
  158 |   });
  159 | 
  160 |   test("price source and staleness metadata display correctly", async ({ page, request }) => {
  161 |     await page.goto("/");
  162 |     await page.getByTestId("nav-paper-trading").click();
  163 | 
  164 |     // Place an order
  165 |     const orderRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  166 |       data: {
  167 |         symbol: "SBIN-EQ",
  168 |         side: "BUY",
  169 |         type: "MARKET",
  170 |         qty: 2,
  171 |         price: 500.0,
  172 |         notes: "price metadata test",
  173 |       },
  174 |     });
  175 |     expect(orderRes.ok()).toBeTruthy();
  176 | 
  177 |     // Fetch positions via the dedicated endpoint
  178 |     const posRes = await request.get(`${apiBaseURL}/paper-trading/positions`);
  179 |     expect(posRes.ok()).toBeTruthy();
  180 |     const positions = await posRes.json();
  181 | 
  182 |     // Verify position has price metadata
  183 |     if (positions.length > 0) {
  184 |       const pos = positions[0];
  185 |       expect(pos).toHaveProperty("price_source");
  186 |       expect(pos).toHaveProperty("price_fetched_at");
  187 |       expect(pos).toHaveProperty("is_price_stale");
  188 |       expect(["LIVE", "CACHE", "FALLBACK"]).toContain(pos.price_source);
  189 |     }
  190 | 
  191 |     // Also check open orders endpoint
  192 |     const ordersRes = await request.get(`${apiBaseURL}/paper-trading/orders/pending`);
  193 |     expect(ordersRes.ok()).toBeTruthy();
  194 |     const pendingOrders = await ordersRes.json();
  195 |     // Should be empty if all orders filled
  196 |     expect(Array.isArray(pendingOrders)).toBe(true);
  197 | 
  198 |     // Check history endpoint
  199 |     const historyRes = await request.get(`${apiBaseURL}/paper-trading/orders/history`);
  200 |     expect(historyRes.ok()).toBeTruthy();
  201 |     const history = await historyRes.json();
  202 |     expect(Array.isArray(history)).toBe(true);
  203 | 
  204 |     // Check trades endpoint
  205 |     const tradesRes = await request.get(`${apiBaseURL}/paper-trading/trades`);
  206 |     expect(tradesRes.ok()).toBeTruthy();
  207 |     const trades = await tradesRes.json();
  208 |     expect(Array.isArray(trades)).toBe(true);
  209 |   });
  210 | 
  211 |   test("dashboard endpoint aggregates all data correctly", async ({ request }) => {
  212 |     // Place orders to create a dashboard state
  213 |     const orderRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  214 |       data: {
  215 |         symbol: "INFY-EQ",
  216 |         side: "BUY",
  217 |         type: "MARKET",
  218 |         qty: 3,
  219 |         price: 100.0,
  220 |         notes: "dashboard test buy",
  221 |       },
  222 |     });
  223 |     expect(orderRes.ok()).toBeTruthy();
  224 | 
  225 |     // Fetch the full dashboard
  226 |     const dashRes = await request.get(`${apiBaseURL}/paper-trading/dashboard`);
  227 |     expect(dashRes.ok()).toBeTruthy();
  228 |     const dashboard = await dashRes.json();
  229 | 
  230 |     // Verify dashboard has all required sections
> 231 |     expect(dashboard).toHaveProperty("workspace");
      |                       ^ Error: expect(received).toHaveProperty(path)
  232 |     expect(dashboard).toHaveProperty("positions");
  233 |     expect(dashboard).toHaveProperty("pending_orders");
  234 |     expect(dashboard).toHaveProperty("order_history");
  235 |     expect(dashboard).toHaveProperty("trades");
  236 | 
  237 |     // Verify positions in dashboard match dedicated endpoint
  238 |     const posRes = await request.get(`${apiBaseURL}/paper-trading/positions`);
  239 |     const positions = await posRes.json();
  240 |     expect(dashboard.positions.length).toBe(positions.length);
  241 | 
  242 |     // Verify history in dashboard matches dedicated endpoint
  243 |     const historyRes = await request.get(`${apiBaseURL}/paper-trading/orders/history`);
  244 |     const history = await historyRes.json();
  245 |     expect(dashboard.order_history.length).toBe(history.length);
  246 |   });
  247 | });
  248 | 
```