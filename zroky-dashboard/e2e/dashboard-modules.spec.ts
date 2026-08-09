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

  test("connector inventory and detail panels stay accessible at the viewport width", async ({ page }) => {
    await page.goto("/integrations");
    await expectDashboardShell(page);
    await expectNoHorizontalOverflow(page);

    const inventory = page.getByLabel("Connector inventory");
    const selected = inventory.locator(".connector-inventory-row[data-selected='true']");
    await expect(selected).toHaveAttribute("aria-pressed", "true");

    const inspector = page.getByLabel("Selected connector");
    await expect.poll(() => inspector.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return [...element.children].flatMap((child) => {
        const childBounds = child.getBoundingClientRect();
        if (childBounds.width === 0 && childBounds.height === 0) return [];
        if (childBounds.left >= bounds.left - 1 && childBounds.right <= bounds.right + 1) return [];
        return [{
          className: child.className,
          inspector: { left: bounds.left, right: bounds.right },
          child: { left: childBounds.left, right: childBounds.right },
        }];
      });
    })).toEqual([]);

    const auditTable = page.locator(".connectors-source-audit-table");
    await expect.poll(() => auditTable.evaluate((element) => getComputedStyle(element).overflowX)).toBe("auto");
  });

  test("workflow library and JSON editor stay usable at the viewport width", async ({ page }) => {
    await page.goto("/workflows");
    await expectDashboardShell(page);
    await expectNoHorizontalOverflow(page);

    const library = page.getByLabel("Workflow library");
    await expect(library).toBeVisible();
    await expect.poll(() => library.evaluate((element) => getComputedStyle(element).overflowX)).toBe("auto");
    const packRows = library.getByRole("button");
    if (await packRows.count()) {
      await expect(packRows.first()).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByRole("button", { name: "Publish" })).toBeDisabled();
    } else {
      await expect(library.getByText(/No Assurance Packs published/)).toBeVisible();
    }

    const editor = page.getByLabel("Assurance Pack JSON");
    await expect(editor).toBeVisible();
    await expect(editor).toHaveAttribute("rows", "12");
  });

  test("evidence ledger and effect proof stay readable at the viewport width", async ({ page }) => {
    const classificationCases = [
      { classification: "verified", reason: null, tone: "success" },
      { classification: "wrong", reason: null, tone: "danger" },
      { classification: "missing", reason: null, tone: "danger" },
      { classification: "forbidden", reason: null, tone: "danger" },
      { classification: "duplicate", reason: null, tone: "danger" },
      { classification: "pending", reason: "runner_offline", tone: "warning" },
      { classification: "stale", reason: null, tone: "warning" },
      { classification: "conflicted", reason: null, tone: "warning" },
      { classification: "unknown", reason: "no_connector", tone: "warning" },
    ] as const;
    await page.route("**/outcome-graphs**", async (route) => {
      if (route.request().url().includes("coverage-summary")) {
        await route.fulfill({
          json: {
            counts: { conflicted: 1, duplicate: 1, forbidden: 1, missing: 1, pending: 1, stale: 1, unknown: 1, verified: 1, wrong: 1 },
            coverage_percent: 11.11,
            total: 9,
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          items: classificationCases.map(({ classification, reason }) => ({
            id: `graph-${classification}`,
            project_id: "demo-refund-money-path",
            environment: "production",
            intent_id: `intent-${classification}`,
            graph_digest: `sha256:graph-${classification}`,
            graph: {
              workflow_key: `${classification}_workflow`,
              expected_effects: [{ effect_key: "refund_posted", object_type: "refund" }],
              actual_effects: [{
                effect_key: "refund_posted",
                object_type: "refund",
                observed: classification !== "missing" && classification !== "pending" && classification !== "unknown",
                matched: classification === "verified",
                stale: classification === "stale",
                conflicted: classification === "conflicted",
                observation_digest: `sha256:observation-${classification}`,
              }],
            },
            verification_status: classification === "verified" ? "verified" : classification === "pending" ? "pending" : "inconclusive",
            classification,
            reason_code: reason,
            last_checked_at: "2026-08-09T07:00:00Z",
            next_check_at: classification === "pending" || classification === "unknown" ? "2026-08-09T08:00:00Z" : null,
            verified_at: classification === "verified" ? "2026-08-09T07:00:00Z" : null,
            created_at: "2026-08-09T06:59:00Z",
          })),
          total: classificationCases.length,
          limit: 100,
          offset: 0,
        },
      });
    });
    await page.goto("/evidence");
    await expectDashboardShell(page);
    await expectNoHorizontalOverflow(page);

    const ledger = page.getByLabel("Evidence ledger");
    const tableWrap = ledger.locator(".ev-ledger-table-wrap");
    await expect(tableWrap).toBeVisible();
    await expect.poll(() => tableWrap.evaluate((element) => getComputedStyle(element).overflowX)).toBe("auto");

    const viewportWidth = page.viewportSize()?.width ?? 1280;
    if (viewportWidth <= 640) {
      await expect.poll(() => tableWrap.evaluate((element) => element.scrollWidth - element.clientWidth)).toBeGreaterThan(200);
    }

    const headers = await ledger.locator("th").evaluateAll((elements) => elements.map((element) => {
      const bounds = element.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right };
    }));
    expect(headers.every((header, index) => index === 0 || header.left >= headers[index - 1].right - 1)).toBe(true);

    const selectedProof = ledger.locator(".ev-proof-name[aria-pressed='true']");
    await expect(selectedProof).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    for (const { classification, tone } of classificationCases) {
      const row = ledger.getByRole("row").filter({ hasText: `${classification}_workflow` });
      await expect(row.locator(".status-pill")).toHaveAttribute("data-tone", tone);
    }
    await expect(page.getByRole("link", { name: "Open intent intent-verified in Operations" })).toHaveAttribute(
      "href",
      "/operations?intent_id=intent-verified",
    );

    const allFilter = ledger.getByRole("button", { name: "All" });
    const provenFilter = ledger.getByRole("button", { name: "Proven" });
    await allFilter.focus();
    await page.keyboard.press("Tab");
    await expect(provenFilter).toBeFocused();
    expect(await provenFilter.evaluate((element) => {
      const style = getComputedStyle(element);
      return style.outlineStyle !== "none" || style.boxShadow !== "none";
    })).toBe(true);

    const unknownProof = ledger.getByRole("button", { name: "Inspect unknown_workflow proof" });
    await unknownProof.focus();
    await expect(unknownProof).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(unknownProof).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("link", { name: "Open integrations" })).toHaveAttribute("href", "/integrations");

    const effect = page.locator(".ev-effect-card").first();
    await expect(effect).toBeVisible();
    const comparison = effect.locator(".ev-effect-comparison");
    await expect(comparison.getByText("Expected")).toBeVisible();
    await expect(comparison.getByText("Observed")).toBeVisible();
    await expect(effect.getByText("Proof reference")).toBeVisible();
  });
});
