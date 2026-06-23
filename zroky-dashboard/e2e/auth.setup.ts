import { expect, test as setup } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { authDir, authStatePath, seedStatePath, type E2ESeed } from "./helpers";

setup.setTimeout(240_000);

const backendRoot = path.resolve(__dirname, "..", "..", "zroky-backend");
const defaultDatabasePath = path.join(backendRoot, ".data", "e2e_dashboard.db");
const databaseUrl = process.env.ZROKY_E2E_DATABASE_URL ?? "sqlite:///./.data/e2e_dashboard.db";
const authSecret = process.env.AUTH_JWT_SECRET ?? "zroky-e2e-local-auth-secret-change-me";
const pythonExe = process.env.ZROKY_E2E_PYTHON
  ?? (process.platform === "win32"
    ? path.join(backendRoot, ".venv", "Scripts", "python.exe")
    : path.join(backendRoot, ".venv", "bin", "python"));
const seedScript = path.join(backendRoot, "scripts", "seed_mvp_money_path_demo.py");

type AuthTokens = {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
  email_verified?: boolean;
};

function seedDemo(): E2ESeed {
  if (!process.env.ZROKY_E2E_DATABASE_URL && fs.existsSync(defaultDatabasePath)) {
    fs.rmSync(defaultDatabasePath);
  }

  const output = execFileSync(pythonExe, [seedScript, "--json", "--create-schema"], {
    cwd: backendRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      DATABASE_URL: databaseUrl,
      AUTH_JWT_SECRET: authSecret,
      OAUTH_STATE_SECRET: authSecret,
    },
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
  const jsonLine = output.split(/\r?\n/).at(-1);
  if (!jsonLine) {
    throw new Error("Seed script did not return JSON output.");
  }
  return JSON.parse(jsonLine) as E2ESeed;
}

setup("seed deterministic demo and save authenticated state", async ({ page, request }) => {
  fs.mkdirSync(authDir, { recursive: true });
  const seed = seedDemo();
  fs.writeFileSync(seedStatePath, JSON.stringify(seed, null, 2));

  await page.context().clearCookies();

  const login = await request.post("/api/zroky/v1/auth/login", {
    data: { email: seed.email, password: seed.password },
    timeout: 20_000,
  });
  expect(login.status(), await login.text()).toBe(200);
  const tokens = await login.json() as AuthTokens;

  const setSession = await request.post("/api/auth/set-session", {
    data: {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      access_max_age_seconds: tokens.access_expires_in_seconds,
      refresh_max_age_seconds: tokens.refresh_expires_in_seconds,
    },
    timeout: 20_000,
  });
  expect(setSession.status(), await setSession.text()).toBe(200);

  const requestState = await request.storageState();
  await page.context().addCookies(requestState.cookies);
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ emailVerified, projectId, accessMaxAgeSeconds, refreshMaxAgeSeconds }) => {
      const nowEpochSeconds = Math.floor(Date.now() / 1000);
      window.localStorage.clear();
      window.localStorage.setItem("zroky_ev", String(emailVerified));
      window.localStorage.setItem(
        "zroky_auth_session",
        JSON.stringify({
          accessToken: null,
          refreshToken: null,
          accessTokenExpiresAtEpochSeconds: nowEpochSeconds + accessMaxAgeSeconds,
          refreshTokenExpiresAtEpochSeconds: nowEpochSeconds + refreshMaxAgeSeconds,
        }),
      );
      window.localStorage.setItem(
        "dashboard-store",
        JSON.stringify({
          state: {
            sidebarOpen: true,
            keyboardShortcutsEnabled: true,
            realTimeEnabled: true,
            lastVisitedPage: "/home",
            selectedProject: projectId,
            assignments: {},
            snoozes: {},
            dismissed: {},
          },
          version: 0,
        }),
      );
    },
    {
      emailVerified: tokens.email_verified ?? true,
      projectId: seed.project_id,
      accessMaxAgeSeconds: tokens.access_expires_in_seconds,
      refreshMaxAgeSeconds: tokens.refresh_expires_in_seconds,
    },
  );

  await page.goto("/home", { waitUntil: "domcontentloaded", timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Search (Command Palette)" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Agent safety status" }).first()).toBeVisible({ timeout: 60_000 });
  await page.context().storageState({ path: authStatePath });
});
