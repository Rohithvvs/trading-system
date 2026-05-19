# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.spec.ts >> app loads and main navigation is available
- Location: e2e\app.spec.ts:9:1

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1   | import { expect, type APIRequestContext, type Page } from "@playwright/test";
  2   | 
  3   | export const apiBaseURL = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8002";
  4   | 
  5   | export async function resetPaperAccount(request: APIRequestContext) {
  6   |   const reset = await request.post(`${apiBaseURL}/test-diagnostics/reset`);
  7   |   expect(reset.ok()).toBeTruthy();
  8   | 
  9   |   const response = await request.post(`${apiBaseURL}/paper-trading/account/reset`, {
  10  |     data: { starting_balance: 1000000 },
  11  |   });
> 12  |   expect(response.ok()).toBeTruthy();
      |                         ^ Error: expect(received).toBeTruthy()
  13  | }
  14  | 
  15  | export async function tableDump(request: APIRequestContext, table: string) {
  16  |   const response = await request.get(`${apiBaseURL}/test-diagnostics/sqlite/table/${table}`);
  17  |   expect(response.ok()).toBeTruthy();
  18  |   return response.json();
  19  | }
  20  | 
  21  | export async function mockScannerResponse(page: Page) {
  22  |   await page.route(`${apiBaseURL}/analysis/screener/full`, async (route) => {
  23  |     const generatedAt = new Date().toISOString();
  24  |     await route.fulfill({
  25  |       status: 200,
  26  |       contentType: "application/json",
  27  |       body: JSON.stringify({
  28  |         scanned_symbols: 1,
  29  |         screener_name: "E2E Mock Scanner",
  30  |         data_valid_symbols: ["INFY-EQ"],
  31  |         eligible_symbols: ["INFY-EQ"],
  32  |         shortlisted_symbols: ["INFY-EQ"],
  33  |         buy_candidate_symbols: ["INFY-EQ"],
  34  |         watch_candidate_symbols: [],
  35  |         matched_symbols: ["INFY-EQ"],
  36  |         matches: [
  37  |           {
  38  |             symbol: "INFY-EQ",
  39  |             close: 100,
  40  |             ema_20: 99,
  41  |             sma_30: 98,
  42  |             sma_50: 97,
  43  |             sma_100: 96,
  44  |             sma_200: 95,
  45  |             macd: 1,
  46  |             macd_signal: 0.5,
  47  |             supertrend: 94,
  48  |             volume: 100000,
  49  |             previous_volume: 90000,
  50  |             screener_score: 82,
  51  |             technical_signal: "bullish",
  52  |             technical_score: 80,
  53  |             candles_fetched: 90,
  54  |             conditions: { close_above_ema20: true },
  55  |             matched: true,
  56  |           },
  57  |         ],
  58  |         all_analyzed_stocks: [],
  59  |         analysis: {
  60  |           items: [],
  61  |           rankings: {
  62  |             rankings: [],
  63  |             buy_rankings: [],
  64  |             watch_rankings: [],
  65  |             best_intraday_candidate: null,
  66  |             best_swing_candidate: null,
  67  |             disclaimer: "test",
  68  |           },
  69  |           disclaimer: "test",
  70  |           generated_at: generatedAt,
  71  |         },
  72  |         disclaimer: "test",
  73  |         data_source: "e2e-mock",
  74  |         market_context: {},
  75  |         scan_stages: [],
  76  |         duplicate_symbols_skipped: 0,
  77  |       }),
  78  |     });
  79  |   });
  80  | }
  81  | 
  82  | export async function mockEngineStatus(page: Page, overrides: Record<string, unknown> = {}) {
  83  |   const payload = {
  84  |     status: "RUNNING",
  85  |     market_hours_active: true,
  86  |     websocket_connected: true,
  87  |     token_status: "VALID",
  88  |     paused_reason: null,
  89  |     last_heartbeat_at: new Date().toISOString(),
  90  |     last_tick_at: new Date().toISOString(),
  91  |     active_monitored_symbols_count: 1,
  92  |     active_symbols: ["INFY-EQ"],
  93  |     trading_date: "2026-05-18",
  94  |     ...overrides,
  95  |   };
  96  |   await page.route(`${apiBaseURL}/paper-trading/engine/status`, (route) =>
  97  |     route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }),
  98  |   );
  99  |   await page.route(`${apiBaseURL}/paper-trading/engine/start`, (route) =>
  100 |     route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }),
  101 |   );
  102 | }
  103 | 
  104 | export async function mockUnreadNotification(page: Page, message: string) {
  105 |   await page.route(`${apiBaseURL}/paper-trading/notifications/unread`, (route) =>
  106 |     route.fulfill({
  107 |       status: 200,
  108 |       contentType: "application/json",
  109 |       body: JSON.stringify([{ id: 9001, message, level: "success", is_read: false, created_at: new Date().toISOString() }]),
  110 |     }),
  111 |   );
  112 |   await page.route(`${apiBaseURL}/paper-trading/notifications/mark-read`, (route) =>
```