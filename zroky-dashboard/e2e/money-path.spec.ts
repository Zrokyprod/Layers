import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectHealthyPage, expectVisibleTexts, readSeed } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("dashboard money path", () => {
  test("proves provider key to failed call to issue to replay to Golden to CI gate", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Mutation proof path runs once in the desktop Chromium project.");
    test.setTimeout(180_000);

    const seed = readSeed();

    await page.goto("/settings/keys");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["API Keys", "Create project key", seed.api_key_prefix ?? "zk_live_demo"]);

    const keyName = `Money path capture ${Date.now()}`;
    await page.getByLabel("Key name").fill(keyName);
    await page.getByLabel("Expires in days").fill("30");
    await page.getByRole("button", { name: "Create project key" }).click();
    await expect(page.getByRole("heading", { name: "Copy this project key now." })).toBeVisible();
    await expect(page.locator(".settings-key-reveal")).toContainText("zroky_api_");
    await page.getByRole("button", { name: "Done" }).click();
    await expectVisibleTexts(page, [keyName]);

    await page.goto("/settings/providers");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "BYOK replay",
      "Save provider key for verified replay",
      "Provider key vault",
      "Vault state",
      "Reachable",
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

    await page.goto("/calls");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["Flight Recorder", seed.call_id.slice(0, 12), "refund-support-agent", "TOOL_NOT_CALLED"]);

    await page.goto(`/calls/${seed.call_id}`);
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [seed.call_id, "Where is my refund?", "TOOL_NOT_CALLED", "failed"]);

    await page.goto("/issues");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["Failures", "selecting the wrong tool", "Tool Not Called"]);

    await page.goto(`/issues/${seed.issue_id}`);
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "selecting the wrong tool",
      "Tool Not Called",
      "get_refund_status",
      "Trusted",
      "Active Golden linked",
      "Gate linked",
    ]);

    await page.goto("/replay");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "Replay proof engine",
      seed.replay_run_id.slice(0, 16),
      seed.issue_id,
      "Refund status tool skipped",
      "verified fix",
      "mocked-tool",
    ]);
    await expect(page.getByRole("link", { name: seed.issue_id }).first()).toHaveAttribute("href", `/issues/${seed.issue_id}`);

    const replayDispatchResponsePromise = page.waitForResponse((response) => {
      return response.url().includes(`/v1/replay/runs/from-issue/${seed.issue_id}`)
        && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start replay" }).click();
    await expect(page.getByRole("dialog", { name: "Connect provider key" })).toHaveCount(0);
    const replayDispatchResponse = await replayDispatchResponsePromise;
    expect(replayDispatchResponse.ok()).toBeTruthy();

    await page.goto(`/replay/${seed.replay_run_id}`);
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [seed.replay_run_id, seed.issue_id, "verified_fix", "RF-1001"]);
    await expect(page.getByRole("link", { name: seed.issue_id }).first()).toHaveAttribute("href", `/issues/${seed.issue_id}`);

    await page.goto("/goldens");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["Goldens", "Refund status protected flow", "Blocks CI"]);
    await expect(page.getByRole("link", { name: "Refund status protected flow" })).toHaveAttribute(
      "href",
      `/goldens/${seed.golden_set_id}`,
    );

    await page.goto(`/goldens/${seed.golden_set_id}`);
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "Refund status protected flow",
      seed.call_id,
      "RF-1001",
      "Blocks CI",
      "verified_fix",
    ]);
    await expect(page.getByRole("link", { name: "View call" }).first()).toHaveAttribute(
      "href",
      `/calls/${seed.call_id}`,
    );

    await page.goto("/ci-gates");
    await expectDashboardShell(page);
    await expectVisibleTexts(page, ["CI Gates", seed.ci_run_id, "demo-break-r", "Failed"]);

    await page.goto(`/ci-gates/${seed.ci_run_id}`);
    await expectDashboardShell(page);
    await expectVisibleTexts(page, [
      "Regression CI blocked this change.",
      seed.ci_run_id,
      "demo-break-r",
      "refund status tool not called",
      seed.golden_trace_id,
      "View Golden set",
    ]);
    await expectHealthyPage(page);
  });
});
