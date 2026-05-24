# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: paper-trading-read-architecture.spec.ts >> Paper Trading Read Architecture >> price source and staleness metadata display correctly
- Location: e2e\paper-trading-read-architecture.spec.ts:160:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e5]:
    - button "Scanner" [ref=e6] [cursor=pointer]
    - button "Home" [ref=e7] [cursor=pointer]
    - button "Paper Trading" [active] [ref=e8] [cursor=pointer]
  - main [ref=e11]:
    - generic [ref=e12]:
      - generic [ref=e13]:
        - paragraph [ref=e14]: Paper Trading
        - heading "Cash-only execution simulator" [level=1] [ref=e15]
        - paragraph [ref=e16]: TradingView-style practice flow for Nifty 500 cash stocks, connected to your analysis and trade-plan outputs.
      - generic [ref=e17]:
        - generic "SBIN-EQ" [ref=e18]: "Engine: STOPPED | Feed: disconnected | Symbols: 1"
        - button "Start Market Engine" [ref=e19] [cursor=pointer]
        - button "Stop Engine" [ref=e20] [cursor=pointer]
        - generic [ref=e21]:
          - generic [ref=e22]: Reset balance
          - spinbutton "Reset balance" [ref=e23]: "1000000"
        - button "Refresh" [ref=e24] [cursor=pointer]
        - button "Live price on" [ref=e25] [cursor=pointer]
        - button "Reset account" [ref=e26] [cursor=pointer]
    - generic [ref=e27]:
      - article [ref=e28]:
        - generic [ref=e29]:
          - text: Balance
          - button "More information" [ref=e31]: ℹ️
        - strong [ref=e32]: "--"
        - paragraph [ref=e33]: Paper account metric.
      - article [ref=e34]:
        - generic [ref=e35]:
          - text: Equity
          - button "More information" [ref=e37]: ℹ️
        - strong [ref=e38]: "--"
        - paragraph [ref=e39]: Paper account metric.
      - article [ref=e40]:
        - generic [ref=e41]:
          - text: Realized P&L
          - button "More information" [ref=e43]: ℹ️
        - strong [ref=e44]: "--"
        - paragraph [ref=e45]: Paper account metric.
      - article [ref=e46]:
        - generic [ref=e47]:
          - text: Unrealized P&L
          - button "More information" [ref=e49]: ℹ️
        - strong [ref=e50]: "--"
        - paragraph [ref=e51]: Paper account metric.
      - article [ref=e52]:
        - generic [ref=e53]:
          - text: Invested
          - button "More information" [ref=e55]: ℹ️
        - strong [ref=e56]: "--"
        - paragraph [ref=e57]: Paper account metric.
      - article [ref=e58]:
        - generic [ref=e59]:
          - text: Available cash
          - button "More information" [ref=e61]: ℹ️
        - strong [ref=e62]: "--"
        - paragraph [ref=e63]: Balance after reserving pending buy orders.
      - article [ref=e64]:
        - generic [ref=e65]:
          - text: Open positions
          - button "More information" [ref=e67]: ℹ️
        - strong [ref=e68]: "--"
        - paragraph [ref=e69]: Paper account metric.
      - article [ref=e70]:
        - text: Open orders
        - strong [ref=e71]: "--"
        - paragraph [ref=e72]: Paper account metric.
    - generic [ref=e74]:
      - generic [ref=e75]:
        - generic [ref=e76]:
          - text: Total capital
          - strong [ref=e77]: "--"
          - paragraph [ref=e78]: Virtual account value
        - generic [ref=e79]:
          - generic [ref=e80]:
            - text: Available funds
            - button "More information" [ref=e82]: ℹ️
          - strong [ref=e83]: "--"
          - paragraph [ref=e84]: Cash available to place buys
        - generic [ref=e85]:
          - text: Invested value
          - strong [ref=e86]: "--"
          - paragraph [ref=e87]: Sum of open positions
        - generic [ref=e88]:
          - generic [ref=e89]:
            - text: Total P&L
            - button "More information" [ref=e91]: ℹ️
          - strong [ref=e92]: "--"
          - paragraph [ref=e93]: Unrealized + realized
        - generic [ref=e94]:
          - generic [ref=e95]:
            - text: Daily P&L
            - button "More information" [ref=e97]: ℹ️
          - strong [ref=e98]: "--"
          - paragraph [ref=e99]: "--"
        - generic [ref=e100]:
          - generic [ref=e101]:
            - text: Market status
            - button "More information" [ref=e103]: ℹ️
          - strong [ref=e104]: "--"
          - paragraph [ref=e105]: Based on IST clock
      - generic [ref=e106]:
        - button "Quick Buy" [ref=e107] [cursor=pointer]
        - button "Quick Sell" [ref=e108] [cursor=pointer]
    - generic [ref=e109]:
      - generic [ref=e111]:
        - tablist "Paper trading data tabs" [ref=e112]:
          - button "Positions" [ref=e113] [cursor=pointer]
          - button "Open Orders" [ref=e114] [cursor=pointer]
          - button "History" [ref=e115] [cursor=pointer]
          - button "Analytics" [ref=e116] [cursor=pointer]
          - button "Alerts" [ref=e117] [cursor=pointer]
          - button "Account" [ref=e118] [cursor=pointer]
        - generic [ref=e119]:
          - button "Square Off ALL" [disabled] [ref=e120] [cursor=pointer]
          - button "More information" [ref=e122]: ℹ️
        - generic [ref=e123]: Loading positions...
      - generic [ref=e124]:
        - generic [ref=e125]:
          - generic [ref=e126]:
            - generic [ref=e127]:
              - paragraph [ref=e128]: Order ticket
              - heading "Place paper order" [level=2] [ref=e129]
            - generic [ref=e130]: Cash only
          - generic [ref=e131]:
            - generic [ref=e132]:
              - generic [ref=e133]:
                - text: Symbol
                - button "More information" [ref=e135]: ℹ️
              - combobox [ref=e136]
            - generic [ref=e137]:
              - generic [ref=e138]:
                - text: Side
                - button "More information" [ref=e140]: ℹ️
              - combobox [ref=e141]:
                - option "Buy" [selected]
                - option "Sell"
            - generic [ref=e142]:
              - generic [ref=e143]:
                - text: Order type
                - button "More information" [ref=e145]: ℹ️
              - combobox [ref=e146]:
                - option "Market"
                - option "Limit" [selected]
                - option "Stop-Loss (market on trigger)"
                - option "Stop-Limit"
                - option "GTT (Good Till Triggered)"
            - generic [ref=e147]:
              - generic [ref=e148]:
                - text: Product
                - button "More information" [ref=e150]: ℹ️
              - combobox [ref=e151]:
                - option "MIS (Intraday)"
                - option "CNC (Delivery)" [selected]
                - option "NRML (Carry)"
            - generic [ref=e152]:
              - generic [ref=e153]:
                - text: Quantity
                - button "More information" [ref=e155]: ℹ️
              - spinbutton [ref=e156]: "1"
            - generic [ref=e157]:
              - generic [ref=e158]:
                - text: Limit price
                - button "More information" [ref=e160]: ℹ️
              - spinbutton [ref=e161]
            - generic [ref=e162]:
              - generic [ref=e163]:
                - text: Stop-loss
                - button "More information" [ref=e165]: ℹ️
              - spinbutton [ref=e166]
            - generic [ref=e167]:
              - generic [ref=e168]:
                - text: Target
                - button "More information" [ref=e170]: ℹ️
              - spinbutton [ref=e171]
          - generic [ref=e172]:
            - generic [ref=e173]: Notes
            - textbox "Notes" [ref=e174]
          - generic [ref=e175]:
            - generic [ref=e176]:
              - generic [ref=e177]:
                - text: Trailing stop %
                - button "More information" [ref=e179]: ℹ️
              - spinbutton [ref=e180]: "2"
            - generic [ref=e181]:
              - generic [ref=e182]:
                - text: Cash allocation %
                - button "More information" [ref=e184]: ℹ️
              - spinbutton [ref=e185]: "10"
            - button "Apply trailing SL" [ref=e186] [cursor=pointer]
            - button "Use suggested qty 1 More information" [ref=e187] [cursor=pointer]:
              - text: Use suggested qty 1
              - button "More information" [ref=e189]: ℹ️
          - generic [ref=e190]:
            - generic [ref=e191]:
              - generic [ref=e192]: Current
              - strong [ref=e193]: "--"
            - generic [ref=e194]:
              - generic [ref=e195]: Estimated cost
              - strong [ref=e196]: ₹0.00
            - generic [ref=e197]:
              - generic [ref=e198]: Risk amount
              - strong [ref=e199]: ₹0.00
            - generic [ref=e200]:
              - generic [ref=e201]: Risk / Reward
              - strong [ref=e202]: "--"
          - paragraph [ref=e203]: "Account rule: avoid risking more than 2.0% per trade and prefer setups with at least 1:2 risk-reward."
          - generic [ref=e204]:
            - generic [ref=e205]: Risk 0.00% of account
            - button "Place paper order" [ref=e207] [cursor=pointer]
        - generic [ref=e208]:
          - generic [ref=e209]:
            - generic [ref=e210]:
              - paragraph [ref=e211]: Selected symbol
              - heading "INFY-EQ" [level=2] [ref=e212]
            - generic [ref=e214]: Current ₹--
          - generic [ref=e215]:
            - heading "No chart data" [level=2] [ref=e216]
            - paragraph [ref=e217]: Select a symbol or refresh the workspace to load candles.
        - generic [ref=e218]:
          - heading "No position selected" [level=2] [ref=e219]
          - paragraph [ref=e220]: Select a symbol with an active position to adjust stop-loss or target in the trade details panel.
```

# Test source

```ts
  75  |     const posCountAfterReload = await page.locator('[data-testid="position-row"]').count();
  76  |     expect(posCountAfterReload).toBeGreaterThanOrEqual(0); // May be 0 if order is still PENDING
  77  | 
  78  |     // 9. Verify DB still shows the order after reload
  79  |     const dbOrdersAfterReload = await tableDump(request, "paper_trading_orders");
  80  |     const persistedOrder = dbOrdersAfterReload.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "BUY");
  81  |     expect(persistedOrder).toBeDefined();
  82  |     expect(["PENDING", "FILLED"]).toContain(persistedOrder.status);
  83  |   });
  84  | 
  85  |   test("open orders and history tabs are separated correctly", async ({ page, request }) => {
  86  |     await page.goto("/");
  87  |     await page.getByTestId("nav-paper-trading").click();
  88  | 
  89  |     // Place a BUY order
  90  |     const buyRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  91  |       data: {
  92  |         symbol: "INFY-EQ",
  93  |         side: "BUY",
  94  |         type: "MARKET",
  95  |         qty: 5,
  96  |         price: 100.0,
  97  |         notes: "open order test",
  98  |       },
  99  |     });
  100 |     expect(buyRes.ok()).toBeTruthy();
  101 | 
  102 |     // Place a SELL order (should close the position)
  103 |     const sellRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  104 |       data: {
  105 |         symbol: "INFY-EQ",
  106 |         side: "SELL",
  107 |         type: "MARKET",
  108 |         qty: 5,
  109 |         price: 105.0,
  110 |         notes: "close position",
  111 |       },
  112 |     });
  113 |     expect(sellRes.ok()).toBeTruthy();
  114 | 
  115 |     // 1. Check Open Orders tab (should be empty after both buy and sell)
  116 |     await page.getByTestId("paper-tab-orders").click();
  117 |     await page.waitForTimeout(500);
  118 |     const pendingOrderCount = await page.locator('[data-testid="pending-order-row"]').count();
  119 |     // After BUY + SELL, there should be no pending orders (both filled)
  120 |     expect(pendingOrderCount).toBe(0);
  121 | 
  122 |     // 2. Check History tab (should have both BUY and SELL)
  123 |     await page.getByTestId("paper-tab-history").click();
  124 |     await page.waitForTimeout(500);
  125 |     const historyRows = await page.locator('[data-testid="history-row"]').count();
  126 |     expect(historyRows).toBeGreaterThanOrEqual(2); // At least BUY and SELL
  127 | 
  128 |     // 3. Verify via DB that trade history contains both trades
  129 |     const dbHistory = await tableDump(request, "paper_trading_orders");
  130 |     const buyTrade = dbHistory.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "BUY");
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
> 175 |     expect(orderRes.ok()).toBeTruthy();
      |                           ^ Error: expect(received).toBeTruthy()
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
  231 |     expect(dashboard).toHaveProperty("selected_workspace");
  232 |     expect(dashboard).toHaveProperty("positions");
  233 |     expect(dashboard).toHaveProperty("open_orders");
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