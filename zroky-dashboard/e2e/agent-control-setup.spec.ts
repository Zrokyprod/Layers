import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectNoHorizontalOverflow } from "./helpers";

test.describe("agent control setup wizard", () => {
  test("renders the protected-action setup flow and local readiness simulation", async ({ page }) => {
    await page.goto("/agents/setup");
    await expectDashboardShell(page);

    await expect(page.getByText("Agent Control Setup")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Protect your first agent action/i })).toBeVisible();
    await expect(page.getByLabel("Protection plan")).toContainText("Internal API change");
    await expect(page.getByLabel("Setup checklist")).toContainText("2 items left");

    await page.getByRole("button", { name: /Protected Action/i }).click();
    await expect(page.getByRole("heading", { name: "Protected Action" })).toBeVisible();
    await page.getByLabel("Agent tools or function names").fill("stripe.refunds.create, zendesk.tickets.update, sendgrid.messages.send, deploy.service");
    await page.getByRole("button", { name: /Detect risky actions/i }).click();
    await expect(page.getByLabel("Detected risky actions")).toContainText("Refund customer payment");
    await expect(page.getByLabel("Detected risky actions")).toContainText("Update or close support ticket");
    await expect(page.getByLabel("Available launch tools")).toContainText("Dashboard approvals");

    await page.getByRole("button", { name: /Proof & Readiness Test/i }).click();
    await page.getByRole("button", { name: /Run local readiness test/i }).click();
    await expect(page.getByRole("button", { name: /Local readiness test passed/i })).toBeVisible();
    await expect(page.getByLabel("Sample Action Receipt")).toContainText("Preview generated");
    await page.getByText("Advanced implementation snippets").click();
    await expect(page.getByText("SDK capture starter")).toBeVisible();
    await expect(page.getByText("Mandate starter")).toBeVisible();

    await expectNoHorizontalOverflow(page);
  });
});
