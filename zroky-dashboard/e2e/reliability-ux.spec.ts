import { expect, test, type Page } from "@playwright/test";

import { expectDashboardShell } from "./helpers";

const canonicalRoutes = [
  "/home",
  "/operations",
  "/workflows",
  "/integrations",
  "/evidence",
  "/approvals",
  "/policies",
  "/projects",
  "/settings/keys",
  "/settings/team",
  "/settings/billing",
  "/settings/workspace",
  "/account",
  "/integrations/slack",
] as const;

async function expectAccessiblePageStructure(page: Page): Promise<void> {
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const unnamedControls = await page.locator("input:visible, select:visible, textarea:visible").evaluateAll((controls) =>
    controls.filter((control) => {
      if (control.getAttribute("aria-label") || control.getAttribute("aria-labelledby")) return false;
      const id = control.getAttribute("id");
      if (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) return false;
      return !control.closest("label");
    }).map((control) => control.outerHTML.slice(0, 180)),
  );
  expect(unnamedControls).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
}

test.describe("dashboard release structure", () => {
  test("every canonical page has one main landmark, one page heading, named forms, and no overflow", async ({ page }) => {
    test.setTimeout(240_000);
    const consoleErrors: string[] = [];
    const failedResponses: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(`${page.url()}: ${message.text()}`);
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
    });

    for (const route of canonicalRoutes) {
      await test.step(route, async () => {
        await page.goto(route, { waitUntil: "networkidle" });
        await expectDashboardShell(page);
        await expectAccessiblePageStructure(page);
      });
    }

    expect(pageErrors).toEqual([]);
    expect({ consoleErrors, failedResponses }).toEqual({ consoleErrors: [], failedResponses: [] });
  });

  test("project details preserve the same page structure", async ({ page }) => {
    await page.goto("/projects");
    await expectDashboardShell(page);
    const projectLink = page.locator('a[href^="/projects/"]').first();
    await expect(projectLink).toBeVisible();
    await projectLink.click();
    await expect(page).toHaveURL(/\/projects\/[^/?#]+$/);
    await expectDashboardShell(page);
    await expectAccessiblePageStructure(page);
  });

  test("retired routes return to Home instead of exposing stale product surfaces", async ({ page }) => {
    for (const route of [
      "/actions",
      "/agents",
      "/agents/setup",
      "/alerts",
      "/calls",
      "/ci-gates",
      "/contracts",
      "/cost",
      "/goldens",
      "/issues",
      "/replay",
      "/trace",
      "/drift",
      "/labs",
    ]) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/home$/);
    }
  });
});
