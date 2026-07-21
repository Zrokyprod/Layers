import { spawnSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

test.describe("final product deployment smoke", () => {
  test("passes final API and dashboard smoke checks against production-build web servers", async ({}, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Final deployment smoke runs once in desktop Chromium.");
    test.setTimeout(180_000);

    const rootDir = path.resolve(__dirname, "..", "..");
    const result = spawnSync(
      "python",
      [
        path.join(rootDir, "scripts", "run_final_product_smoke.py"),
        "--api-base-url",
        process.env.ZROKY_E2E_API_BASE_URL ?? "http://127.0.0.1:8010",
        "--dashboard-url",
        process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3010",
        "--dashboard-auth-state",
        path.join(rootDir, "zroky-dashboard", "e2e", ".auth", "user.json"),
        "--allow-skipped-ready-checks",
        "--timeout-seconds",
        "20",
      ],
      {
        cwd: rootDir,
        encoding: "utf8",
        timeout: 120_000,
      },
    );

    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
    expect(result.status, output).toBe(0);
    expect(output).toContain("[final-product-smoke] passed");
  });
});
