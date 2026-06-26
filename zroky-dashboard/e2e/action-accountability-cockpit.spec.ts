import { expect, test, type Page } from "@playwright/test";

import { expectDashboardShell, expectNoHorizontalOverflow, expectVisibleTexts, readSeed } from "./helpers";

async function expectNoConsoleErrors(page: Page, action: () => Promise<void>): Promise<void> {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await action();

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
}

test.describe("action accountability cockpits", () => {
  test("renders agents, approvals, and outcomes with seeded proof data", async ({ page }) => {
    test.setTimeout(180_000);
    const seed = readSeed();

    await expectNoConsoleErrors(page, async () => {
      await page.goto("/agents");
      await expectDashboardShell(page);
      await expectNoHorizontalOverflow(page);
      await expectVisibleTexts(page, [
        "Outcome mismatch",
        "Protected agents",
        "Needs review",
        "Protected agent queue",
        "refund-support-agent",
        seed.runtime_policy_decision_id ?? "demo-runtime-refund-hold",
        "HOLD",
        "mismatched",
        "ledger_refund_api - ledger:RF-1001",
        "Evidence Pack",
      ], 120_000);
      const expectedEvidenceHref = `/evidence?decision_id=${encodeURIComponent(
        seed.runtime_policy_decision_id ?? "demo-runtime-refund-hold",
      )}`;
      const protectedMatrix = page.locator("article").filter({ hasText: "Protected agent queue" });
      await expect(protectedMatrix.getByRole("link", { name: "Evidence Pack" })).toHaveAttribute(
        "href",
        expectedEvidenceHref,
      );

      await page.goto(expectedEvidenceHref);
      await expectDashboardShell(page);
      await expectNoHorizontalOverflow(page);
      await expectVisibleTexts(page, [
        "Evidence Pack ledger",
        "Selected Evidence Pack",
        "Evidence Pack detail",
        "Print report",
        seed.runtime_policy_decision_id ?? "demo-runtime-refund-hold",
        "Evidence hash",
        "Mandate snapshot",
        "Approval audit",
        "Real outcome reconciliation",
      ], 120_000);

      await page.goto("/approvals");
      await expectDashboardShell(page);
      await expectNoHorizontalOverflow(page);
      await expectVisibleTexts(page, [
        "Risky actions held before commit",
        "Held action queue",
        "Risky action control",
        seed.runtime_policy_decision_id ?? "demo-runtime-refund-hold",
        "Refund RF-1001 for customer cus_demo_001",
        "Outcome failed",
        "refund amount requires owner approval",
        "Runtime kill switch",
      ]);
      await expect(page.getByRole("button", { name: "Arm kill switch confirmation" })).toBeVisible();

      await page.goto("/outcomes");
      await expectDashboardShell(page);
      await expectNoHorizontalOverflow(page);
      await expectVisibleTexts(page, [
        "Outcome verification",
        "Real outcome queue",
        "Agent claim vs real outcome",
        seed.outcome_mismatch_id ?? "demo-outcome-refund-mismatch",
        "Refund RF-1001 for customer cus_demo_001",
        "Outcome mismatch",
        "1 field mismatch",
        "Refund status follow-up email delivered",
      ]);
      await expect(page.getByRole("button", { name: "Mismatched", exact: true })).toBeVisible();
    });
  });
});
