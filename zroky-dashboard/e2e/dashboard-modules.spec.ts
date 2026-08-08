import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectNoHorizontalOverflow, expectVisibleTexts } from "./helpers";

const currentRoutes = [
  { path: "/home", labels: ["Home", "Proof posture", "Proven outcomes"] },
  { path: "/operations", labels: ["Operations", "Runs", "Incidents", "Approvals"] },
  { path: "/workflows", labels: ["Workflows", "Workflow library", "Workflow contract"] },
  { path: "/integrations", labels: ["Connectors", "Available systems", "Recent test-reads"] },
  { path: "/evidence", labels: ["Proof records", "Selected proof"] },
  { path: "/approvals", labels: ["Approval control", "Approval queue"] },
  { path: "/policies", labels: ["Runtime Action Control", "Set the control level, not every field", "Create a clear WHEN / IN / THEN rule"] },
  { path: "/projects", labels: ["Projects", "Accessible projects"] },
  { path: "/settings/keys", labels: ["API keys", "Project keys", "Create key"] },
  { path: "/settings/team", labels: ["Members", "Invite member", "Project members"] },
  { path: "/settings/billing", labels: ["Plan & Billing", "Usage this month", "Available plans"] },
  { path: "/settings/workspace", labels: ["Workspace", "Workspace details"] },
  { path: "/account", labels: ["Personal account", "Plan and workspace access"] },
  { path: "/integrations/slack", labels: ["Slack notifications", "Connected channel", "Test message"] },
] as const;

test.describe("dashboard modules", () => {
  test("all current dashboard routes render with seeded backend data", async ({ page }) => {
    test.setTimeout(240_000);

    for (const route of currentRoutes) {
      await test.step(route.path, async () => {
        await page.goto(route.path);
        await expectDashboardShell(page);
        await expectVisibleTexts(page, [...route.labels]);
      });
    }
  });

  test("compatibility routes resolve to the current information architecture", async ({ page }) => {
    const aliases = [
      { from: "/incidents", to: /\/operations\?view=incidents$/ },
      { from: "/outcomes", to: /\/evidence$/ },
      { from: "/settings", to: /\/settings\/keys$/ },
      { from: "/settings/profile", to: /\/account$/ },
      { from: "/settings/providers", to: /\/settings\/keys$/ },
      { from: "/settings/integrations", to: /\/integrations$/ },
      { from: "/settings/integrations/slack", to: /\/integrations\/slack$/ },
    ];

    for (const route of aliases) {
      await page.goto(route.from);
      await expect(page).toHaveURL(route.to);
      await expectDashboardShell(page);
    }
  });

  test("SQL connector setup exposes the current read-only proof controls", async ({ page }) => {
    await page.goto("/integrations");
    await expectDashboardShell(page);
    await page.getByRole("button", { name: /SQL database/ }).click();
    await expect(page.getByRole("heading", { name: "SQL database" })).toBeVisible();
    await page.getByRole("button", { name: "Connect database" }).click();

    await expect(page.getByLabel("Read-only database URL")).toBeVisible();
    await expect(page.getByLabel("Parameterized SELECT query")).toBeVisible();
    await expect(page.getByLabel("System reference")).toBeVisible();
    await expect(page.getByLabel("Query params JSON")).toBeVisible();
    await expect(page.getByLabel("Database claimed JSON")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save database access" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Run database preflight" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});
