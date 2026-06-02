import { test } from "@playwright/test";

import { expectAnyVisibleText, expectDashboardShell, readSeed } from "./helpers";

test.describe("dashboard modules", () => {
  test("all primary dashboard routes render with seeded backend data", async ({ page }) => {
    test.setTimeout(180_000);

    const seed = readSeed();
    const routes = [
      { path: "/home", labels: ["Failure Inbox", "refund-support-agent"] },
      { path: "/calls", labels: ["Calls", "refund-support-agent"] },
      { path: `/calls/${seed.call_id}`, labels: [seed.call_id, "refund-support-agent", "Where is my refund?"] },
      { path: "/issues", labels: ["Issues", "TOOL_SELECTION_FAILURE", "Refund"] },
      { path: `/issues/${seed.issue_id}`, labels: ["Refund", "TOOL_NOT_CALLED", "Release"] },
      { path: "/goldens", labels: ["Goldens", "Refund status protected flow"] },
      { path: `/goldens/${seed.golden_set_id}`, labels: ["Refund status protected flow", "RF-1001"] },
      { path: "/ci-gates", labels: ["CI Gates", "demo-break-refund-tool"] },
      { path: `/ci-gates/${seed.ci_run_id}`, labels: ["Regression CI", "blocked this PR", "demo-break-refund-tool"] },
      { path: "/cost", labels: ["Cost", "Budget", "refund-support-agent"] },
      { path: "/trace", labels: ["Traces", seed.trace_id, "refund-support-agent"] },
      { path: `/trace/${seed.trace_id}`, labels: [seed.trace_id, "refund-support-agent", "Where is my refund?"] },
      { path: "/replay", labels: ["Replay", "demo-fixed-refund-tool"] },
      { path: `/replay/${seed.replay_run_id}`, labels: ["verified", "Refund", "RF-1001"] },
      { path: "/agents", labels: ["Agent", "Reliability"] },
      { path: "/alerts", labels: ["Alerts", "Refund status tool skipped"] },
      { path: "/drift", labels: ["Provider Drift", "fake-provider"] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expectDashboardShell(page);
      await expectAnyVisibleText(page, route.labels);
    }
  });
});
