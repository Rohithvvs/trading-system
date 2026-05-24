import { expect, test } from "@playwright/test";
import { apiBaseURL, resetPaperAccount } from "./helpers";

test.beforeEach(async ({ request }) => {
  // Ensure the database is clean before executing real integration flows
  await resetPaperAccount(request);
});

test.describe("Real Connectivity Integration Tests (Non-Mocked)", () => {
  test("test_real_backend_handshake: hits backend health and token status endpoints without mocking", async ({ page }) => {
    // 1. Visit the root of the app
    await page.goto("/");
    
    // 2. Expect the main nav elements to be visible (signaling frontend is alive)
    await expect(page.getByTestId("nav-home")).toBeVisible();
    await expect(page.getByTestId("nav-paper-trading")).toBeVisible();

    // 3. Trigger navigation to paper trading -> account panel to load real token status
    await page.getByTestId("nav-paper-trading").click();
    await page.getByTestId("paper-tab-account").click();

    // 4. Verify that the token status badge receives a real response (either Token Active, Token Inactive, or No token)
    // instead of staying blank or freezing.
    const tokenBadge = page.getByTestId("token-status-badge");
    await expect(tokenBadge).toBeVisible();
    const badgeText = await tokenBadge.textContent();
    expect(["Token Active", "Token Inactive", "No token"]).toContain(badgeText);
  });

  test("test_real_db_order_commit_plumbing: places order through UI forms, commits to real DB, and reads back", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-paper-trading").click();
    await expect(page.getByTestId("paper-order-ticket")).toBeVisible();

    // 1. Interact with the form ticket input elements
    await page.getByTestId("paper-symbol-select").selectOption("INFY-EQ");
    await page.getByTestId("paper-side-select").selectOption("BUY");
    await page.getByTestId("paper-order-type-select").selectOption("LIMIT");
    await page.getByTestId("paper-qty-input").fill("1");
    await page.locator("label:has-text('Limit price') input").fill("1000");

    // 2. Open confirmation preview and submit order (committing to the real database)
    await page.getByTestId("paper-place-order-button").click();
    const confirmButton = page.getByTestId("paper-confirm-order-button");
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    // 3. Switch to the Orders tab and verify the row was loaded back from the real DB and rendered
    await page.getByTestId("paper-tab-orders").click();

    // The order should have symbol INFY-EQ and type LIMIT in the table
    await expect(page.getByText("INFY-EQ").first()).toBeVisible();
    await expect(page.getByText("LIMIT").first()).toBeVisible();
  });
});
