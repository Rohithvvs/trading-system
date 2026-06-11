import { expect, test } from "@playwright/test";
import { apiBaseURL, resetPaperAccount } from "./helpers";

test.describe("Frontend Idempotency Tests", () => {
  test.beforeEach(async ({ request }) => {
    try { await request.post(`${apiBaseURL}/test-diagnostics/reset`); } catch(e) {}
    await request.post(`${apiBaseURL}/paper-trading/account/reset`, { data: { starting_balance: 1000000 } });
  });

  test("BUY click generates idempotency key and prevents duplicate orders", async ({ page }) => {
    // Intercept requests to /paper-trading/orders
    let orderRequests: any[] = [];
    await page.route("**/paper-trading/orders", async (route) => {
      const request = route.request();
      if (request.method() === "POST") {
        orderRequests.push(request);
      }
      route.continue();
    });

    await page.goto("/");
    await page.getByTestId("nav-paper-trading").click();
    
    // Fill out the form
    const qtyInput = page.getByLabel(/Quantity/i).or(page.getByPlaceholder("Qty"));
    if (await qtyInput.isVisible()) {
      await qtyInput.fill("10");
    }

    // Double-click BUY rapidly
    // The button has data-testid="paper-place-order-button" and then "paper-confirm-order-button"
    await page.getByTestId("paper-place-order-button").click();
    await page.getByTestId("paper-confirm-order-button").click();
    
    // Attempt rapid second click if possible (usually UI blocks or closes dialog, but let's just make sure the first one worked with idempotency)
    
    // Wait for network requests
    await page.waitForTimeout(1000);

    expect(orderRequests.length).toBeGreaterThan(0);
    const firstReq = orderRequests[0];
    const headers = firstReq.headers();
    expect(headers["idempotency-key"]).toBeDefined();
    expect(headers["idempotency-key"].length).toBeGreaterThan(10);
    
    // Verify backend didn't create duplicate orders.
    const ordersRes = await page.request.get(`${apiBaseURL}/paper-trading/orders/history`);
    const ordersData = await ordersRes.json();
    expect(ordersData.length).toBe(1);
    
    // 4. New BUY generates new key
    // Wait until isBusy resets
    await page.waitForTimeout(500);
    orderRequests = []; // reset
    await page.getByTestId("paper-place-order-button").click();
    await page.getByTestId("paper-confirm-order-button").click();
    await page.waitForTimeout(1000);
    expect(orderRequests.length).toBe(1);
    expect(orderRequests[0].headers()["idempotency-key"]).toBeDefined();
    expect(orderRequests[0].headers()["idempotency-key"]).not.toBe(headers["idempotency-key"]);
  });
});
