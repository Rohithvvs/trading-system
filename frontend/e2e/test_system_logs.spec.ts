import { expect, test } from "@playwright/test";

test("terminal reconnects after websocket close, expands traceback, and clears logs", async ({ page }) => {
  let deleteCalled = false;

  await page.route("**/api/logs?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 100,
          timestamp: "2026-05-25T09:00:00Z",
          level: "ERROR",
          source: "API",
          module: "BrokerGateway",
          endpoint: "POST /orders",
          message: "Broker order rejected",
          error_hash: "err-hash-100",
          traceback: "Traceback (most recent call last):\nZeroDivisionError: division by zero",
          structured_data: { symbol: "HINDALCO-EQ", retryable: false },
          correlationId: "cid-playwright",
          environment: "TEST",
        },
      ]),
    });
  });

  await page.route("**/api/logs/clear?**", async (route) => {
    deleteCalled = true;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ deleted: 1 }) });
  });

  await page.addInitScript(() => {
    class DroppingWebSocket {
      static instances: DroppingWebSocket[] = [];
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      readyState = 0;
      url: string;

      constructor(url: string) {
        this.url = url;
        DroppingWebSocket.instances.push(this);
        window.setTimeout(() => {
          this.readyState = 1;
          this.onopen?.(new Event("open"));
          this.readyState = 3;
          this.onclose?.(new CloseEvent("close"));
        }, 25);
      }

      close() {
        this.readyState = 3;
      }

      send() {}
    }

    (window as any).__systemLogSockets = DroppingWebSocket.instances;
    (window as any).WebSocket = DroppingWebSocket;
  });

  await page.goto("/logs");

  await expect(page.getByText("Broker order rejected")).toBeVisible();
  await expect(page.locator(".logs-connection")).toContainText(/reconnecting|connecting|live/);
  await page.waitForFunction(() => (window as any).__systemLogSockets.length >= 2, null, { timeout: 5000 });

  await page.getByRole("button", { name: /View Stacktrace for Broker order rejected/i }).click();
  await expect(page.getByTestId("log-details")).toContainText("ZeroDivisionError");
  await expect(page.getByTestId("log-details")).toContainText("HINDALCO-EQ");

  await page.getByRole("button", { name: "Clear Logs" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Confirm Clear" }).click();

  await expect.poll(() => deleteCalled).toBe(true);
  await expect(page.getByText("No logs match the current filters.")).toBeVisible();
});
