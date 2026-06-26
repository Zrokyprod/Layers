import { expect, test, type Page } from "@playwright/test";

import { expectDashboardShell, expectVisibleTexts, readSeed } from "./helpers";

type ReliabilityRoute = {
  path: string;
  labels: string[];
};

function reliabilityRoutes(): ReliabilityRoute[] {
  const seed = readSeed();
  return [
    {
      path: "/home",
      labels: ["Agent action accountability", "Decision queue", "Evidence Pack", "System-of-record health"],
    },
    {
      path: "/agents",
      labels: ["Protected agents", "Outcome mismatch", "Needs review", "System-of-record health"],
    },
    {
      path: "/approvals",
      labels: ["Risky actions held before commit", "Held action queue", "Risky action control"],
    },
    {
      path: "/outcomes",
      labels: ["Every risky action must end", "SDK helper and webhook bridge", "Agent claim vs real outcome"],
    },
    {
      path: seed.runtime_policy_decision_id
        ? `/evidence?decision_id=${encodeURIComponent(seed.runtime_policy_decision_id)}`
        : "/evidence",
      labels: ["Evidence Pack is exportable", "Policy gate recorded", "Real system checked"],
    },
    {
      path: "/integrations",
      labels: ["Connector coverage", "Generic REST/OpenAPI verifier", "System-of-record connectors"],
    },
    {
      path: "/policies",
      labels: ["Policies define what an agent may attempt", "Hold sensitive actions", "Block unsafe paths"],
    },
  ];
}

function retiredDetailRoutes(): string[] {
  const seed = readSeed();
  return [
    `/issues/${seed.issue_id}`,
    `/replay/${seed.replay_run_id}`,
    `/ci-gates/${seed.ci_run_id}`,
    `/calls/${seed.call_id}`,
    `/goldens/${seed.golden_set_id}`,
    `/trace/${seed.trace_id}`,
  ];
}

async function expectPageHeading(page: Page): Promise<void> {
  await expect(page.locator("h1").first()).toBeVisible();
}

async function expectMainContentFitsViewport(page: Page): Promise<void> {
  await expect(page.getByRole("main")).toBeVisible();
  const mainFitsViewport = await page.getByRole("main").evaluate((main) => {
    const rect = main.getBoundingClientRect();
    return rect.left >= -2 && rect.right <= window.innerWidth + 2;
  });
  expect(mainFitsViewport).toBeTruthy();
}

test.describe("reliability loop UX", () => {
  test("renders paid MVP control surfaces with stable shell and summary copy", async ({ page }) => {
    test.setTimeout(180_000);

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    for (const route of reliabilityRoutes()) {
      await test.step(route.path, async () => {
        await page.goto(route.path);
        await expectDashboardShell(page);
        await expectMainContentFitsViewport(page);
        await expectPageHeading(page);
        await expectVisibleTexts(page, route.labels);
      });
    }

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });

  test("redirects retired legacy detail routes to the new dashboard home", async ({ page }) => {
    for (const route of retiredDetailRoutes()) {
      await test.step(route, async () => {
        await page.goto(route);
        await expect(page).toHaveURL(/\/home$/);
      });
    }
  });
});
