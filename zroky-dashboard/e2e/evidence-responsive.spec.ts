import { expect, test } from "@playwright/test";

import { expectDashboardShell } from "./helpers";

test("keeps the evidence ledger inside the mobile viewport", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Responsive evidence check runs in mobile Chromium.");

  await page.goto("/evidence");
  await expectDashboardShell(page);
  await expect(page.locator(".evidence-page")).toBeVisible();

  const overflow = await page.locator(".evidence-page").evaluate((root) => {
    const selectors = [
      ".evidence-page",
      ".ev-operator-hero",
      ".ev-proof-summary-strip",
      ".dashboard-workspace",
      ".ev-ledger-panel",
      ".ev-focused-card",
    ];
    return selectors.filter((selector) => {
      const element = root.matches(selector) ? root : root.querySelector(selector);
      if (!element) return false;
      const rect = element.getBoundingClientRect();
      return rect.left < -1 || rect.right > window.innerWidth + 1;
    });
  });

  expect(overflow).toEqual([]);
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
});
