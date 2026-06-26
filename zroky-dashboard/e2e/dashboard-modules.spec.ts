import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectNoHorizontalOverflow, expectVisibleTexts } from "./helpers";

test.describe("dashboard modules", () => {
  test("all primary dashboard routes render with seeded backend data", async ({ page }) => {
    test.setTimeout(180_000);

    const routes = [
      { path: "/home", labels: ["Agent action accountability", "Decision queue", "Evidence Pack", "System-of-record health"] },
      { path: "/agents", labels: ["Outcome mismatch", "Needs review", "Protected agent queue", "System-of-record health"] },
      { path: "/approvals", labels: ["Risky actions held before commit", "Held action queue", "Risky action control"] },
      { path: "/outcomes", labels: ["Every risky action must end", "SDK helper and webhook bridge"] },
      { path: "/evidence", labels: ["Evidence Pack is exportable", "Policy gate recorded"] },
      { path: "/integrations", labels: ["Connector coverage", "Generic REST/OpenAPI verifier", "System-of-record connectors"] },
      { path: "/policies", labels: ["Policies define what an agent may attempt", "Hold sensitive actions"] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expectDashboardShell(page);
      await expectVisibleTexts(page, route.labels);
    }

    for (const retiredRoute of [
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
      "/labs/agents",
      "/labs/drift",
    ]) {
      await page.goto(retiredRoute);
      await expect(page).toHaveURL(/\/home$/);
    }
  });

  test("system-of-record connectors expose PostgreSQL read proof controls", async ({ page }) => {
    test.setTimeout(180_000);

    await page.goto("/integrations");
    await expectDashboardShell(page);

    const postgresCard = page.locator("#postgres-read-connector");
    await expect(postgresCard.getByRole("heading", { name: "PostgreSQL read connector" })).toBeVisible();
    await postgresCard.scrollIntoViewIfNeeded();

    await expect(postgresCard.getByLabel("PostgreSQL read connector status")).toBeVisible();
    await expect(postgresCard.getByLabel("Database URL")).toBeVisible();
    await expect(postgresCard.getByLabel("Read-only query")).toBeVisible();
    await expect(postgresCard.getByLabel("System reference")).toBeVisible();
    await expect(postgresCard.getByLabel("Query params JSON")).toBeVisible();
    await expect(postgresCard.getByLabel("Claimed record JSON")).toBeVisible();
    await expect(postgresCard.getByRole("button", { name: "Save PostgreSQL connector" })).toBeVisible();
    await expect(postgresCard.getByRole("button", { name: "Run PostgreSQL test reconciliation" })).toBeVisible();
    await expect(postgresCard.getByRole("button", { name: "Run saved PostgreSQL proof" })).toBeVisible();
    await expect(postgresCard.getByLabel("PostgreSQL read preflight command")).toContainText(
      "/v1/integrations/system-of-record/postgres-read/test",
    );
    await expect(postgresCard.getByLabel("PostgreSQL read full proof command")).toContainText(
      "/v1/outcomes/reconciliation/postgres-read/saved",
    );
    await expect(postgresCard.getByLabel("PostgreSQL read saved connector test payload")).toContainText(
      "postgres:tickets:TIC-1001",
    );

    const cardFitsViewport = await postgresCard.evaluate((card) => {
      const rect = card.getBoundingClientRect();
      return rect.left >= -2 && rect.right <= window.innerWidth + 2;
    });
    expect(cardFitsViewport).toBeTruthy();
    await expectNoHorizontalOverflow(page);
  });
});
