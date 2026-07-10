import { test, expect, devices } from "@playwright/test";

/**
 * Android Chrome-style viewport checks for auth screens.
 * Serves production build (vite preview) with VITE_API_URL baked to Render.
 */

const androidChrome = devices["Pixel 5"];

test.use({
  ...androidChrome,
  storageState: undefined,
});

test.describe("Auth mobile (Android Chrome viewport)", () => {
  test("Login page renders and posts to production API (not localhost)", async ({ page }) => {
    const loginRequests: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/auth/login")) {
        loginRequests.push(req.url());
      }
    });

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();

    const email = page.locator('input[name="email"]');
    const password = page.locator('input[name="password"]');
    await expect(email).toHaveCount(1);
    await expect(email).toBeVisible();

    await email.fill("mobile-test@example.com");
    await password.fill("WrongPassword123!");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Allow network round-trip to Render (may cold-start)
    await page.waitForTimeout(8000);

    expect(loginRequests.length).toBeGreaterThan(0);
    for (const url of loginRequests) {
      expect(url).not.toMatch(/127\.0\.0\.1|localhost/);
      expect(url).toMatch(/^https:\/\//);
    }

    const errorBanner = page.getByTestId("auth-error");
    // Wrong password should produce a server/auth error, not a raw network failure
    if (await errorBanner.isVisible().catch(() => false)) {
      const text = (await errorBanner.innerText()).toLowerCase();
      expect(text).not.toContain("failed to fetch");
    }
  });

  test("Signup page renders on mobile viewport", async ({ page }) => {
    await page.goto("/signup");
    await expect(page.getByRole("heading", { name: /create an account/i })).toBeVisible();
    await expect(page.locator('input[name="fullName"]')).toHaveCount(1);
    await expect(page.locator('input[name="fullName"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.getByRole("button", { name: /sign up/i })).toBeVisible();
  });

  test("Forgot Password page renders on mobile viewport", async ({ page }) => {
    await page.goto("/auth/forgot-password");
    await expect(page.getByRole("heading", { name: /forgot password/i })).toBeVisible();
    await expect(page.locator('input[name="email"]')).toHaveCount(1);
    await expect(page.locator('input[name="email"]')).toBeVisible();
  });

  test("Signup network failure shows friendly message (not Failed to fetch)", async ({ page }) => {
    await page.route("**/auth/signup", (route) => route.abort("failed"));

    await page.goto("/signup");
    await page.locator('input[name="fullName"]').fill("Mobile Tester");
    await page.locator('input[name="email"]').fill("mobile-signup@example.com");
    await page.locator('input[name="password"]').fill("SecurePass123!");
    await page.locator('input[name="confirmPassword"]').fill("SecurePass123!");

    const submit = page.getByRole("button", { name: /sign up/i });
    await expect(submit).toBeEnabled({ timeout: 5000 });
    await submit.click();

    const banner = page.getByTestId("auth-error");
    await expect(banner).toBeVisible({ timeout: 10000 });
    const text = (await banner.innerText()).toLowerCase();
    expect(text).not.toContain("failed to fetch");
    expect(
      text.includes("cannot connect") ||
        text.includes("network") ||
        text.includes("unreachable") ||
        text.includes("server"),
    ).toBeTruthy();
  });

  test("Desktop Chrome Login also posts to HTTPS API", async ({ browser }) => {
    const context = await browser.newContext({
      ...devices["Desktop Chrome"],
    });
    const page = await context.newPage();
    const loginRequests: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/auth/login")) {
        loginRequests.push(req.url());
      }
    });

    await page.goto("/login");
    await page.locator('input[name="email"]').fill("desktop-test@example.com");
    await page.locator('input[name="password"]').fill("WrongPassword123!");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForTimeout(8000);

    expect(loginRequests.length).toBeGreaterThan(0);
    expect(loginRequests[0]).toMatch(/^https:\/\/.*onrender\.com\/auth\/login/);
    await context.close();
  });
});
