import { defineConfig, devices } from "@playwright/test";

const authStatePath = "e2e/.auth/user.json";
const runAllBrowsers = process.env.E2E_ALL_BROWSERS === "1";
const dashboardPort = process.env.ZROKY_E2E_DASHBOARD_PORT ?? "3010";
const apiPort = process.env.ZROKY_E2E_API_PORT ?? "8010";
const dashboardBaseUrl = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${dashboardPort}`;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const e2eDatabaseUrl = process.env.ZROKY_E2E_DATABASE_URL ?? "sqlite:///./.data/e2e_dashboard.db";
const e2eAuthSecret = process.env.AUTH_JWT_SECRET ?? "zroky-e2e-local-auth-secret-change-me";
const dashboardCommand = process.env.ZROKY_E2E_DASHBOARD_COMMAND
  ?? `npm run build && npm run start -- -p ${dashboardPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "html",
  use: {
    baseURL: dashboardBaseUrl,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "setup",
      testMatch: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      dependencies: ["setup"],
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: authStatePath },
    },
    {
      name: "mobile-chromium",
      dependencies: ["setup"],
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices["Pixel 5"], storageState: authStatePath },
    },
    ...(runAllBrowsers
      ? [
          {
            name: "firefox",
            dependencies: ["setup"],
            testIgnore: /.*\.setup\.ts/,
            use: { ...devices["Desktop Firefox"], storageState: authStatePath },
          },
          {
            name: "webkit",
            dependencies: ["setup"],
            testIgnore: /.*\.setup\.ts/,
            use: { ...devices["Desktop Safari"], storageState: authStatePath },
          },
        ]
      : []),
  ],
  webServer: [
    {
      command: `.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../zroky-backend",
      url: `${apiBaseUrl}/health/live`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: e2eDatabaseUrl,
        AUTH_JWT_SECRET: e2eAuthSecret,
        OAUTH_STATE_SECRET: e2eAuthSecret,
        ENABLE_READY_REDIS_CHECK: "false",
        PROVIDER_KEY_VAULT_KEK: process.env.PROVIDER_KEY_VAULT_KEK ?? "zroky-e2e-provider-key-vault-kek-32-chars",
        PROVIDER_KEY_VAULT_KEY_ID: process.env.PROVIDER_KEY_VAULT_KEY_ID ?? "zroky-e2e-local-kek-v1",
        ZROKY_DISABLE_SLOWAPI_LIMITS: "1",
        TESTING: "true",
      },
    },
    {
      command: dashboardCommand,
      url: dashboardBaseUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 900_000,
      env: {
        ZROKY_API_BASE_URL: process.env.ZROKY_API_BASE_URL ?? apiBaseUrl,
        ZROKY_ALLOW_LOCAL_API_BASE_URL: "1",
        ZROKY_API_PROXY_TIMEOUT_MS: process.env.ZROKY_API_PROXY_TIMEOUT_MS ?? "30000",
      },
    },
  ],
});
