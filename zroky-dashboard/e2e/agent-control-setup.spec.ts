import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectNoHorizontalOverflow } from "./helpers";

test.describe("agent control setup wizard", () => {
  test("renders the guided protected-agent setup flow", async ({ page }) => {
    await page.goto("/agents/setup?intent=protect-agent&source=e2e");
    await expectDashboardShell(page);

    const quickstart = page.getByLabel("Protect an agent");

    await expect(page.getByText("Agent Control Setup")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Protect an agent|Waiting for the first protected action|Agent is live/i })).toBeVisible();
    await expect(quickstart.locator('[data-step="key"]')).toContainText("Project key");
    await expect(quickstart.locator('[data-step="connect"]')).toContainText("Connect");
    await expect(quickstart.locator('[data-step="run"]')).toContainText("Run");
    await expect(quickstart.locator('[data-step="live"]')).toContainText(/What's next|You're live/);

    const createProjectKey = page.getByRole("button", { name: "Create project key" });
    if (await createProjectKey.isVisible().catch(() => false)) {
      await createProjectKey.click();
      await expect(page.getByText("Runtime environment")).toBeVisible({ timeout: 30_000 });
    } else {
      await expect(page.getByText("Runtime key ready")).toBeVisible();
    }
    await expect(page.getByLabel("Agent name")).toBeVisible();
    await expect(page.getByLabel("Framework")).toBeVisible();
    await expect(quickstart.getByLabel("Environment", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Zroky control loop")).toContainText("Propose");
    await expect(page.getByLabel("Zroky control loop")).toContainText("Receipt");

    await quickstart.getByLabel("Agent name").fill("E2E Setup Agent");
    await page.getByRole("button", { name: /Create & enable protection/i }).click();
    await expect(page.getByText(/is protected with the safe default policy/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Minimal SDK starter")).toBeVisible();
    await expect(page.getByLabel("Live capture status")).toContainText("SDK ready");

    await expectNoHorizontalOverflow(page);
  });
});
