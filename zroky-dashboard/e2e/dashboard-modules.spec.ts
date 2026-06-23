import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectVisibleTexts, readSeed } from "./helpers";

test.describe("dashboard modules", () => {
  test("all primary dashboard routes render with seeded backend data", async ({ page }) => {
    test.setTimeout(180_000);

    const seed = readSeed();
    const routes = [
      { path: "/home", labels: ["Agent action accountability", "Decision queue", "Evidence Pack", "System-of-record health"] },
      { path: "/agents", labels: ["Outcome mismatch", "Needs your decision", "Selected agent proof", "System-of-record health"] },
      { path: "/calls", labels: ["Call Evidence", "refund-support-agent", "failed"] },
      { path: `/calls/${seed.call_id}`, labels: [seed.call_id, "refund-support-agent", "Where is my refund?"] },
      { path: "/issues", labels: ["Failures", "selecting the wrong tool", "Tool Not Called"] },
      { path: `/issues/${seed.issue_id}`, labels: ["selecting the wrong tool", "Tool Not Called", "get_refund_status"] },
      { path: "/goldens", labels: ["Fixtures", "Refund status protected flow"] },
      { path: `/goldens/${seed.golden_set_id}`, labels: ["Refund status protected flow", "RF-1001"] },
      { path: "/ci-gates", labels: ["CI Gates", "demo-break-r"] },
      { path: `/ci-gates/${seed.ci_run_id}`, labels: ["Regression CI", "Regression CI blocked this change.", "demo-break-r"] },
      { path: "/cost", labels: ["Cost", "Budget", "refund-support-agent"] },
      { path: "/trace", labels: ["Traces", seed.trace_id, "refund-support-agent"] },
      { path: `/trace/${seed.trace_id}`, labels: [seed.call_id, "refund-support-agent", "Where is my refund?", "TOOL_NOT_CALLED"] },
      { path: "/replay", labels: ["Replay", "demo-replay-refu", "verified fix"] },
      { path: `/replay/${seed.replay_run_id}`, labels: ["verified", "Refund", "RF-1001"] },
      { path: "/alerts", labels: ["Alerts", "Refund status tool skipped"] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expectDashboardShell(page);
      await expectVisibleTexts(page, route.labels);
    }

    for (const retiredRoute of ["/drift", "/labs", "/labs/agents", "/labs/drift"]) {
      await page.goto(retiredRoute);
      await expect(page).toHaveURL(/\/home$/);
    }
  });
});
