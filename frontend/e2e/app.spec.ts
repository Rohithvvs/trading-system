import { expect, test } from "@playwright/test";

import { apiBaseURL, mockEngineStatus, mockScannerResponse, mockUnreadNotification, resetPaperAccount, tableDump } from "./helpers";

test.beforeEach(async ({ request }) => {
  await resetPaperAccount(request);
});

test("app loads and main navigation is available", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-home")).toBeVisible();
  await expect(page.getByTestId("nav-scanner")).toBeVisible();
  await expect(page.getByTestId("nav-paper-trading")).toBeVisible();
});

test("token management saves a token and backend confirms SQLite persistence", async ({ page, request }) => {
  await page.goto("/");
  await page.getByTestId("nav-paper-trading").click();
  await page.getByTestId("paper-tab-account").click();
  await expect(page.getByTestId("token-management-panel")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Access token saved");
    await dialog.accept();
  });

  await page.getByTestId("access-token-input").fill("e2e-access-token-1234567890");
  await page.getByTestId("save-access-token-button").click();
  await expect(page.getByTestId("token-status-badge")).toContainText("Token Active");

  const diagnostic = await request.get(`${apiBaseURL}/test-diagnostics/token`);
  expect(diagnostic.ok()).toBeTruthy();
  const body = await diagnostic.json();
  expect(body.stored_in_sqlite).toBe(true);
  expect(JSON.stringify(body)).not.toContain("e2e-access-token-1234567890");
});

test("scanner flow renders results and records browser localStorage history", async ({ page }) => {
  await mockScannerResponse(page);
  await page.goto("/");
  await page.getByTestId("nav-scanner").click();
  await page.getByTestId("run-scanner-button").click();

  await expect(page.getByText("INFY-EQ").first()).toBeVisible();
  const scanHistory = await page.evaluate(() => window.localStorage.getItem("scanHistory"));
  expect(scanHistory).toContain("INFY-EQ");
});

test("scanner Buy action prefills paper trading flow", async ({ page }) => {
  await mockScannerResponse(page);
  await page.goto("/");
  await page.getByTestId("nav-scanner").click();
  await page.getByTestId("run-scanner-button").click();
  await page.getByText("Buy", { exact: true }).click();
  await expect(page.getByTestId("paper-symbol-select")).toHaveValue("INFY-EQ");
});

test("paper trading flow creates an order row that survives page reload", async ({ page, request }) => {
  await page.goto("/");
  await page.getByTestId("nav-paper-trading").click();
  await expect(page.getByTestId("paper-order-ticket")).toBeVisible();

  await page.getByTestId("paper-symbol-select").selectOption("INFY-EQ");
  await page.getByTestId("paper-order-type-select").selectOption("MARKET");
  await page.getByTestId("paper-qty-input").fill("1");

  const order = await request.post(`${apiBaseURL}/paper-trading/orders`, {
    data: { symbol: "INFY-EQ", side: "BUY", type: "MARKET", qty: 1, notes: "e2e paper trade" },
  });
  expect(order.ok()).toBeTruthy();

  const dump = await tableDump(request, "paper_trading_orders");
  expect(dump.rows.some((row: any) => row.symbol === "INFY-EQ")).toBe(true);

  await page.reload();
  await page.getByTestId("nav-paper-trading").click();
  await page.getByTestId("paper-tab-orders").click();
  await expect(page.getByText("INFY-EQ").first()).toBeVisible();
});

test("engine status, notification, and paused state render from backend truth", async ({ page }) => {
  await mockEngineStatus(page, {
    status: "PAUSED_TOKEN_EXPIRED",
    websocket_connected: false,
    token_status: "EXPIRED",
    paused_reason: "TOKEN_EXPIRED",
  });
  await mockUnreadNotification(page, "INFY-EQ paper buy auto-filled at Rs 95.");
  await page.goto("/");
  await page.getByTestId("nav-paper-trading").click();
  await page.getByTestId("start-market-engine-button").click();
  await expect(page.getByText(/Engine: PAUSED_TOKEN_EXPIRED/)).toBeVisible();
  await expect(page.getByText(/TOKEN_EXPIRED/)).toBeVisible();
  await expect(page.getByText(/paper buy auto-filled/)).toBeVisible();
});
