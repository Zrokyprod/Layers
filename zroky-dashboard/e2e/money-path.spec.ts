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
    await expectVisibleTexts(page, ["API keys", "Create key", seed.api_key_prefix ?? "zk_live_demo"]);

    const keyName = `Money path capture ${Date.now()}`;
    await page.getByLabel("Key name").fill(keyName);
    await page.getByLabel("Expires in days").fill("30");
    await page.getByRole("button", { name: "Create key" }).click();
    await expect(page.getByRole("heading", { name: "Key created" })).toBeVisible();
    await expect(page.locator(".settings-key-reveal")).toContainText("zk_live_");
    await page.getByRole("button", { name: "Done" }).click();
    await expectVisibleTexts(page, [keyName]);

    const launchSurfaces = [
      { path: "/home", labels: ["Home", "Proof posture", "Proven outcomes"] },
      { path: "/operations", labels: ["Operations", "Runs", "Incidents", "Approvals"] },
      { path: "/approvals", labels: ["Approval control", "Approval queue"] },
      { path: "/evidence", labels: ["Proof records", "Selected proof"] },
      { path: "/integrations", labels: ["Connectors", "Available systems", "Recent test-reads"] },
      { path: "/policies", labels: ["Runtime Action Control", "Set the control level, not every field"] },
      { path: "/workflows", labels: ["Workflows", "Workflow library", "Workflow contract"] },
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
