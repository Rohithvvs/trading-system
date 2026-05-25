import { test, expect, type Page } from "@playwright/test";

// Mock helper to define consistent responses for standard endpoints
async function setupMocks(
  page: Page,
  dashboardPayload: any,
  enginePayload: any,
  tokenStatusPayload: any
) {
  // Mock token status endpoint
  await page.route("**/api/token/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(tokenStatusPayload),
    });
  });

  // Mock token history
  await page.route("**/api/token/history**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ history: [] }),
    });
  });

  // Mock dashboard payload
  await page.route("**/paper-trading/dashboard**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboardPayload),
    });
  });

  // Mock account summary payload (uses dashboard.account)
  await page.route("**/paper-trading/account/summary**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboardPayload.account),
    });
  });

  // Mock matching engine status
  await page.route("**/paper-trading/engine/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(enginePayload),
    });
  });

  // Mock notifications, alerts, and workstation settings
  await page.route("**/paper-trading/notifications/unread", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/paper-trading/alerts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/workstation/alerts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/workstation/risk-settings", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        profile: "moderate",
        default_position_size_pct: 10.0,
        max_risk_per_trade_pct: 2.0,
      }),
    });
  });
}

test.describe("Trading Flow E2E Tests", () => {
  test("test_token_status_indicator_sync: verifies active status badge styling and content", async ({ page }) => {
    const dashboardPayload = {
      account: {
        account_id: 1,
        account_name: "Primary Paper Account",
        base_currency: "INR",
        starting_balance: 1000000.0,
        balance: 1000000.0,
        equity: 1000000.0,
        realized_pnl: 0.0,
        unrealized_pnl: 0.0,
        total_invested: 0.0,
        reserved_cash: 0.0,
        available_cash: 1000000.0,
        open_positions_count: 0,
        open_orders_count: 0,
        max_risk_per_trade: 0.02,
        updated_at: new Date().toISOString(),
      },
      positions: [],
      open_orders: [],
      order_history: [],
      trades: [],
      symbols: ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"],
      selected_workspace: null,
    };

    const enginePayload = {
      status: "RUNNING",
      market_hours_active: true,
      websocket_connected: true,
      token_status: "VALID",
      paused_reason: null,
      last_heartbeat_at: new Date().toISOString(),
      last_tick_at: new Date().toISOString(),
      active_monitored_symbols_count: 0,
      active_symbols: [],
      trading_date: "2026-05-23",
    };

    const tokenStatusPayload = {
      status: "active",
      access_token_saved_at: "2026-05-23T10:00:00Z",
      last_error: null,
    };

    // Apply the Playwright mock interception routes
    await setupMocks(page, dashboardPayload, enginePayload, tokenStatusPayload);

    await page.goto("/");
    await page.getByTestId("nav-paper-trading").click();
    await page.getByTestId("paper-tab-account").click();

    // Verify token active badge shows valid text and green active state class
    const badge = page.getByTestId("token-status-badge");
    await expect(badge).toBeVisible();
    await expect(badge).toContainText("Token Active");
    await expect(badge).toHaveClass(/green/);
  });

  test("test_order_placement_table_flow: places a limit buy order and verifies its UI updates", async ({ page }) => {
    // Initial stateful dashboard payload
    const dashboardPayload = {
      account: {
        account_id: 1,
        account_name: "Primary Paper Account",
        base_currency: "INR",
        starting_balance: 1000000.0,
        balance: 1000000.0,
        equity: 1000000.0,
        realized_pnl: 0.0,
        unrealized_pnl: 0.0,
        total_invested: 0.0,
        reserved_cash: 0.0,
        available_cash: 1000000.0,
        open_positions_count: 0,
        open_orders_count: 0,
        max_risk_per_trade: 0.02,
        updated_at: new Date().toISOString(),
      },
      positions: [],
      open_orders: [],
      order_history: [],
      trades: [],
      symbols: ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"],
      selected_workspace: null,
    };

    const enginePayload = {
      status: "RUNNING",
      market_hours_active: true,
      websocket_connected: true,
      token_status: "VALID",
      paused_reason: null,
      last_heartbeat_at: new Date().toISOString(),
      last_tick_at: new Date().toISOString(),
      active_monitored_symbols_count: 1,
      active_symbols: ["INFY-EQ"],
      trading_date: "2026-05-23",
    };

    const tokenStatusPayload = {
      status: "active",
      access_token_saved_at: "2026-05-23T10:00:00Z",
      last_error: null,
    };

    await setupMocks(page, dashboardPayload, enginePayload, tokenStatusPayload);

    // Mock the POST request when order is placed, and dynamically update the dashboard payload
    await page.route("**/paper-trading/orders", async (route) => {
      if (route.request().method() === "POST") {
        // Recalculate summary metrics for state update simulation
        dashboardPayload.account.reserved_cash = 5000.0;
        dashboardPayload.account.available_cash = 995000.0;
        dashboardPayload.account.open_orders_count = 1;

        const newOrder = {
          id: 101,
          symbol: "INFY-EQ",
          side: "BUY",
          type: "LIMIT",
          qty: 5,
          price: 1000.0,
          status: "PENDING",
          lifecycle_state: "PENDING_ENTRY",
          created_at: new Date().toISOString(),
        };

        dashboardPayload.open_orders.push(newOrder as any);
        dashboardPayload.order_history.push(newOrder as any);

        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            account: dashboardPayload.account,
            order: newOrder,
            position: null,
            trade: null,
            message: "Limit buy order placed and kept pending.",
          }),
        });
      }
    });

    await page.goto("/");
    await page.getByTestId("nav-paper-trading").click();

    // Fill the Order Form
    await page.getByTestId("paper-symbol-select").selectOption("INFY-EQ");
    await page.getByTestId("paper-side-select").selectOption("BUY");
    await page.getByTestId("paper-order-type-select").selectOption("LIMIT");
    await page.getByTestId("paper-qty-input").fill("5");
    await page.locator("label:has-text('Limit price') input").fill("1000");

    // Click submit order and confirm order in preview modal
    await page.getByTestId("paper-place-order-button").click();
    const confirmButton = page.getByTestId("paper-confirm-order-button");
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    // Switch to orders tab
    await page.getByTestId("paper-tab-orders").click();

    // Confirm that the INFY-EQ limit order is added and displays correctly in the order table
    await expect(page.getByText("INFY-EQ").first()).toBeVisible();
    await expect(page.getByText("PENDING ENTRY").first()).toBeVisible();
    await expect(page.getByText("1000.00").first()).toBeVisible();
  });

  test("test_dashboard_persistence_on_reload: verifies reload preserves positions and portfolio metrics", async ({ page }) => {
    // Dashboard containing 1 active position with positive P&L
    const dashboardPayload = {
      account: {
        account_id: 1,
        account_name: "Primary Paper Account",
        base_currency: "INR",
        starting_balance: 1000000.0,
        balance: 970000.0,
        equity: 1005000.0,
        realized_pnl: 0.0,
        unrealized_pnl: 5000.0,
        total_invested: 30000.0,
        reserved_cash: 0.0,
        available_cash: 970000.0,
        open_positions_count: 1,
        open_orders_count: 0,
        max_risk_per_trade: 0.02,
        updated_at: new Date().toISOString(),
      },
      positions: [
        {
          id: 201,
          symbol: "INFY-EQ",
          qty: 30,
          avg_entry_price: 1000.0,
          current_price: 1166.67,
          unrealized_pnl: 5000.0,
          unrealized_pnl_percent: 16.67,
          invested_value: 30000.0,
          stop_loss: 950.0,
          target: 1200.0,
          lifecycle_state: "OPEN_POSITION",
          monitor_enabled: true,
          paused_reason: null,
          risk_reward_ratio: 4.0,
          source_signal: "bullish",
          source_score: 85.0,
          source_confidence: 0.9,
          price_source: "FYERS_QUOTE",
          price_fetched_at: new Date().toISOString(),
          is_price_stale: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      open_orders: [],
      order_history: [],
      trades: [],
      symbols: ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"],
      selected_workspace: null,
    };

    const enginePayload = {
      status: "RUNNING",
      market_hours_active: true,
      websocket_connected: true,
      token_status: "VALID",
      paused_reason: null,
      last_heartbeat_at: new Date().toISOString(),
      last_tick_at: new Date().toISOString(),
      active_monitored_symbols_count: 1,
      active_symbols: ["INFY-EQ"],
      trading_date: "2026-05-23",
    };

    const tokenStatusPayload = {
      status: "active",
      access_token_saved_at: "2026-05-23T10:00:00Z",
      last_error: null,
    };

    await setupMocks(page, dashboardPayload, enginePayload, tokenStatusPayload);

    await page.goto("/");
    await page.getByTestId("nav-paper-trading").click();

    // 1. Verify metrics show the correct initial values
    await expect(page.locator(".metric-card:has-text('Invested') strong").first()).toContainText("30,000");
    await expect(page.locator(".metric-card:has-text('Available cash') strong").first()).toContainText("9,70,000");
    await expect(page.locator(".metric-card:has-text('Equity') strong").first()).toContainText("10,05,000");
    await expect(page.locator(".metric-card:has-text('Unrealized P&L') strong").first()).toContainText("5,000");

    // 2. Perform a hard browser refresh
    await page.reload();

    // 3. Re-navigate to paper trading page if necessary
    await page.getByTestId("nav-paper-trading").click();

    // 4. Verify metrics are correctly loaded back up after reload
    await expect(page.locator(".metric-card:has-text('Invested') strong").first()).toContainText("30,000");
    await expect(page.locator(".metric-card:has-text('Available cash') strong").first()).toContainText("9,70,000");
    await expect(page.locator(".metric-card:has-text('Equity') strong").first()).toContainText("10,05,000");
    await expect(page.locator(".metric-card:has-text('Unrealized P&L') strong").first()).toContainText("5,000");
  });
});
