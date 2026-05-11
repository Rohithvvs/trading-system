import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const apiBaseURL = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8002";

export async function resetPaperAccount(request: APIRequestContext) {
  const reset = await request.post(`${apiBaseURL}/test-diagnostics/reset`);
  expect(reset.ok()).toBeTruthy();

  const response = await request.post(`${apiBaseURL}/paper-trading/account/reset`, {
    data: { starting_balance: 1000000 },
  });
  expect(response.ok()).toBeTruthy();
}

export async function tableDump(request: APIRequestContext, table: string) {
  const response = await request.get(`${apiBaseURL}/test-diagnostics/sqlite/table/${table}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function mockScannerResponse(page: Page) {
  await page.route(`${apiBaseURL}/analysis/screener/full`, async (route) => {
    const generatedAt = new Date().toISOString();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        scanned_symbols: 1,
        screener_name: "E2E Mock Scanner",
        data_valid_symbols: ["INFY-EQ"],
        eligible_symbols: ["INFY-EQ"],
        shortlisted_symbols: ["INFY-EQ"],
        buy_candidate_symbols: ["INFY-EQ"],
        watch_candidate_symbols: [],
        matched_symbols: ["INFY-EQ"],
        matches: [
          {
            symbol: "INFY-EQ",
            close: 100,
            ema_20: 99,
            sma_30: 98,
            sma_50: 97,
            sma_100: 96,
            sma_200: 95,
            macd: 1,
            macd_signal: 0.5,
            supertrend: 94,
            volume: 100000,
            previous_volume: 90000,
            screener_score: 82,
            technical_signal: "bullish",
            technical_score: 80,
            candles_fetched: 90,
            conditions: { close_above_ema20: true },
            matched: true,
          },
        ],
        all_analyzed_stocks: [],
        analysis: {
          items: [],
          rankings: {
            rankings: [],
            buy_rankings: [],
            watch_rankings: [],
            best_intraday_candidate: null,
            best_swing_candidate: null,
            disclaimer: "test",
          },
          disclaimer: "test",
          generated_at: generatedAt,
        },
        disclaimer: "test",
        data_source: "e2e-mock",
        market_context: {},
        scan_stages: [],
        duplicate_symbols_skipped: 0,
      }),
    });
  });
}
