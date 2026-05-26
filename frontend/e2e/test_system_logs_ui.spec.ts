import { expect, test } from "@playwright/test";

test("system logs terminal renders colors, expands payloads, clears, and reconnects websocket", async ({ page }) => {
  await page.route("**/api/logs?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 1,
          timestamp: "2026-05-25T08:00:00Z",
          level: "ERROR",
          source: "API",
          module: "OrderService",
          endpoint: "POST /orders",
          message: "Order failed",
          error_hash: "abc123",
          traceback: "Traceback\nValueError: failed",
          structured_data: { symbol: "INFY-EQ", retries: 2 },
          correlationId: "cid-1",
          environment: "TEST",
        },
      ]),
    });
  });
  await page.route("**/api/logs/clear?**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ deleted: 1 }) });
  });

  await page.addInitScript(() => {
    class MockWebSocket {
      static instances: MockWebSocket[] = [];
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      readyState = 0;
      url: string;

      constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
        window.setTimeout(() => {
          this.readyState = 1;
          this.onopen?.(new Event("open"));
          this.onmessage?.(
            new MessageEvent("message", {
              data: JSON.stringify({
                id: 2,
                timestamp: "2026-05-25T08:00:01Z",
                level: "INFO",
                source: "SYSTEM",
                module: "LoggingService",
                message: "live log",
                structured_data: { ok: true },
              }),
            }),
          );
          this.readyState = 3;
          this.onclose?.(new CloseEvent("close"));
        }, 50);
      }

      close() {
        this.readyState = 3;
      }

      send() {}
    }

    (window as any).__mockSockets = MockWebSocket.instances;
    (window as any).WebSocket = MockWebSocket;
  });

  await page.goto("/logs");

  await expect(page.getByTestId("system-logs-page")).toBeVisible();
  await expect(page.getByText("Order failed")).toBeVisible();
  await expect(page.getByText("live log").first()).toBeVisible();
  await expect(page.locator(".log-level.text-red-500").first()).toHaveText("ERROR");
  await expect(page.locator(".log-level.text-green-500").first()).toContainText(/INFO|ERROR/);

  await page.getByText("Order failed").click();
  await expect(page.getByTestId("log-details").first()).toContainText("Traceback");
  await expect(page.getByTestId("log-details").first()).toContainText("INFY-EQ");

  await expect(page.locator(".logs-connection")).toContainText(/reconnecting|live|connecting/);
  await page.waitForFunction(() => (window as any).__mockSockets.length >= 2);

  await page.getByRole("button", { name: "Clear Logs" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Confirm Clear" }).click();
  await expect(page.getByText("No logs match the current filters.")).toBeVisible();
});
