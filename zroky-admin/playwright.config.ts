import { defineConfig, devices } from "@playwright/test";

const runAllBrowsers = process.env.E2E_ALL_BROWSERS === "1";
const adminPort = process.env.ZROKY_E2E_ADMIN_PORT ?? "3001";
const adminBaseUrl = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${adminPort}`;
const adminCommand = process.env.ZROKY_E2E_ADMIN_COMMAND
  ?? `npm run build && npm run start -- -p ${adminPort}`;
const startWebServer = process.env.ZROKY_E2E_SKIP_WEBSERVER !== "1" && !process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "html",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: adminBaseUrl,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    ...(runAllBrowsers
      ? [
          { name: "firefox", use: { ...devices["Desktop Firefox"] } },
          { name: "webkit", use: { ...devices["Desktop Safari"] } },
        ]
      : []),
  ],
  ...(startWebServer
    ? {
        webServer: {
          command: adminCommand,
          url: adminBaseUrl,
          reuseExistingServer: !process.env.CI,
          timeout: 420_000,
          env: {
            NEXT_TELEMETRY_DISABLED: "1",
            ZROKY_API_BASE_URL: process.env.ZROKY_API_BASE_URL ?? "https://admin-e2e-api.invalid",
          },
        },
      }
    : {}),
});
