import { test } from "@playwright/test";

import { expectDashboardShell, expectHealthyPage, expectVisibleTexts, readSeed } from "./helpers";

test.describe("final product flow surfaces", () => {
  test("renders policy, verification, incident, recovery, and evidence surfaces", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Final-flow browser gate runs once in desktop Chromium.");
    test.setTimeout(180_000);

    const seed = readSeed();
    const routes = [
      {
        path: "/operations",
        labels: [
          "Final runs, incidents, and approval requirements",
          "Outcome incidents",
          "Approval requirements",
          "Runs, approvals, and recovery",
          "Recovery dispatch stays approval-controlled",
        ],
      },
      {
        path: "/approvals",
        labels: ["Risky actions held before commit", "Held action queue", "Approval required", "Evidence matches request"],
      },
      {
        path: "/outcomes",
        labels: ["Verified action mismatch", "proof checks", "Mismatched", "Not verified"],
      },
      {
        path: seed.runtime_policy_decision_id
          ? `/evidence?decision_id=${encodeURIComponent(seed.runtime_policy_decision_id)}`
          : "/evidence",
        labels: ["Exception needs review", "Proof records", "Runtime decision proof", "Approval audit"],
      },
      {
        path: "/policies",
        labels: [
          "Runtime Action Control",
          "Scoped policy rules",
          "Effective policy",
          "Policy dry-run",
          "Latest runtime decisions",
          "Evidence path",
        ],
      },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expectDashboardShell(page);
      await expectVisibleTexts(page, route.labels);
      await expectHealthyPage(page);
    }
  });
});
