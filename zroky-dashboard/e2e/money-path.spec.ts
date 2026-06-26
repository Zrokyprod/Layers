import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectHealthyPage, expectVisibleTexts, readSeed } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("dashboard money path", () => {
  test("proves paid MVP control surfaces without legacy dashboard routes", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Mutation proof path runs once in the desktop Chromium project.");
    test.setTimeout(180_000);

    const seed = readSeed();

    await page.goto("/settings/keys");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["Project key setup", "Create project key", seed.api_key_prefix ?? "zk_live_demo"]);

    const keyName = `Money path capture ${Date.now()}`;
    await page.getByLabel("Key name").fill(keyName);
    await page.getByLabel("Expires in days").fill("30");
    await page.getByRole("button", { name: "Create project key" }).click();
    await expect(page.getByRole("heading", { name: "Copy this project key now." })).toBeVisible();
    await expect(page.locator(".settings-key-reveal")).toContainText("zk_live_");
    await page.getByRole("button", { name: "Done" }).click();
    await expectVisibleTexts(page, [keyName]);

    await page.goto("/settings/providers");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "BYOK replay",
      "Save provider keys only when replay needs real provider access.",
      "Save provider key",
      "Provider key vault",
      "Vault state",
      "Priority providers",
    ]);

    const providerLabel = `money-path-e2e-${Date.now()}`;
    await page.locator("#providerKeyProvider").selectOption("openai");
    await page.locator("#providerKeyLabel").fill(providerLabel);
    await page.locator("#providerKeyPlaintext").fill("sk-e2e-provider-key-not-real-1234567890");
    const providerKeyResponsePromise = page.waitForResponse((response) => {
      return response.url().includes("/v1/providers/keys") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Save provider key" }).click();
    const providerKeyResponse = await providerKeyResponsePromise;
    expect(providerKeyResponse.status()).toBe(201);
    await expect(page.locator("#providerKeyPlaintext")).toHaveValue("");
    const providerRow = page.locator(".providers-vault-panel tbody tr").filter({ hasText: providerLabel });
    await expect(providerRow).toBeVisible();
    await expect(providerRow.getByText("Active", { exact: true })).toBeVisible();

    const launchSurfaces = [
      { path: "/home", labels: ["Agent action accountability", "Decision queue", "Evidence Pack", "System-of-record health"] },
      { path: "/agents", labels: ["Outcome mismatch", "Needs review", "Protected agent queue", "System-of-record health"] },
      { path: "/approvals", labels: ["Risky actions held before commit", "Held action queue", "Risky action control"] },
      { path: "/outcomes", labels: ["Every risky action must end", "SDK helper and webhook bridge"] },
      {
        path: seed.runtime_policy_decision_id
          ? `/evidence?decision_id=${encodeURIComponent(seed.runtime_policy_decision_id)}`
          : "/evidence",
        labels: ["Evidence Pack is exportable", "Policy gate recorded"],
      },
      { path: "/integrations", labels: ["Connector coverage", "Generic REST/OpenAPI verifier", "System-of-record connectors"] },
      { path: "/policies", labels: ["Policies define what an agent may attempt", "Hold sensitive actions"] },
    ];

    for (const route of launchSurfaces) {
      await page.goto(route.path);
      await expectDashboardShell(page);
      await expectVisibleTexts(page, route.labels);
      await expectHealthyPage(page);
    }

    for (const retiredRoute of [
      "/calls",
      `/calls/${seed.call_id}`,
      "/issues",
      `/issues/${seed.issue_id}`,
      "/replay",
      `/replay/${seed.replay_run_id}`,
      "/goldens",
      `/goldens/${seed.golden_set_id}`,
      "/ci-gates",
      `/ci-gates/${seed.ci_run_id}`,
      "/cost",
      "/trace",
      `/trace/${seed.trace_id}`,
      "/alerts",
    ]) {
      await page.goto(retiredRoute);
      await expect(page).toHaveURL(/\/home$/);
    }
  });
});
