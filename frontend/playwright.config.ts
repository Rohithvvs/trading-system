import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 5175);
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 8002);
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${frontendPort}`;
const apiBaseURL = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "../tests/artifacts/playwright/html-report", open: "never" }],
    ["json", { outputFile: "../tests/artifacts/playwright/results.json" }],
  ],
  outputDir: "../tests/artifacts/playwright/test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER ? undefined : [
    {
      command: `venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: "..",
      env: {
        APP_ENV: "test",
        DATABASE_URL: "sqlite:///./tests/artifacts/e2e_app.db",
        NIFTY500_SYMBOLS: "INFY-EQ,TCS-EQ,RELIANCE-EQ",
        // Ensure backend writes logs into the Playwright artifacts folder for this run
        TEST_ARTIFACT_DIR: process.env.TEST_ARTIFACT_DIR ?? "tests/artifacts/playwright/backend",
        RUN_ID: process.env.RUN_ID ?? new Date().toISOString().replace(/[:.-]/g, ""),
      },
      url: apiBaseURL + "/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      gracefulShutdown: { signal: "SIGINT", timeout: 1000 },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      env: {
        VITE_API_BASE_URL: apiBaseURL,
      },
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      gracefulShutdown: { signal: "SIGINT", timeout: 1000 },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
