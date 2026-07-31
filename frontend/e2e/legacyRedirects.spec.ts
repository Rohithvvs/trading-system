import { test, expect } from "@playwright/test";

test.describe("Legacy Route Redirect Aliases", () => {
  test("redirects /home to /", async ({ page }) => {
    await page.goto("/home");
    await expect(page).toHaveURL("/");
  });

  test("redirects /scanner to /research/scanner", async ({ page }) => {
    await page.goto("/scanner");
    await expect(page).toHaveURL("/research/scanner");
  });

  test("redirects /paper to /trading/paper-desk", async ({ page }) => {
    await page.goto("/paper");
    await expect(page).toHaveURL("/trading/paper-desk");
  });

  test("redirects /logs to /system/logs", async ({ page }) => {
    await page.goto("/logs");
    await expect(page).toHaveURL("/system/logs");
  });
});
