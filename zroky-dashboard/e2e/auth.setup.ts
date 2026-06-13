import { expect, test as setup } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { authDir, authStatePath, seedStatePath, type E2ESeed } from "./helpers";

setup.setTimeout(120_000);

const backendRoot = path.resolve(__dirname, "..", "..", "zroky-backend");
const defaultDatabasePath = path.join(backendRoot, ".data", "e2e_dashboard.db");
const databaseUrl = process.env.ZROKY_E2E_DATABASE_URL ?? "sqlite:///./.data/e2e_dashboard.db";
const authSecret = process.env.AUTH_JWT_SECRET ?? "zroky-e2e-local-auth-secret-change-me";
const pythonExe = process.env.ZROKY_E2E_PYTHON
  ?? (process.platform === "win32"
    ? path.join(backendRoot, ".venv", "Scripts", "python.exe")
    : path.join(backendRoot, ".venv", "bin", "python"));
const seedScript = path.join(backendRoot, "scripts", "seed_mvp_money_path_demo.py");

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

setup("seed deterministic demo and save authenticated state", async ({ page }) => {
  fs.mkdirSync(authDir, { recursive: true });
  const seed = seedDemo();
  fs.writeFileSync(seedStatePath, JSON.stringify(seed, null, 2));

  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => window.localStorage.clear());

  await page.getByLabel("Email address").fill(seed.email);
  await page.locator("#login-password").fill(seed.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/home/, { timeout: 20_000 });
  const seededProjectButton = page.getByRole("button", { name: new RegExp(seed.project_id) });
  if (await seededProjectButton.waitFor({ state: "visible", timeout: 10_000 }).then(() => true).catch(() => false)) {
    await seededProjectButton.click();
  }
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible({ timeout: 20_000 });
  await page.context().storageState({ path: authStatePath });
});
