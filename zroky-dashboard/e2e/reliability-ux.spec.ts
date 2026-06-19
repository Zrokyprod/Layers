import { expect, test, type Page } from "@playwright/test";

import { expectDashboardShell, expectVisibleTexts, readSeed } from "./helpers";

type ReliabilityRoute = {
  path: string;
  heading: string;
  labels: string[];
};

const RELIABILITY_ROUTES: ReliabilityRoute[] = [
  {
    path: "/home",
    heading: "Overview",
    labels: [
      "Highest priority",
      "What needs action now?",
      "Replay pass/fail",
      "Release readiness",
      "Reliability pipeline",
      "CI gate health",
    ],
  },
  {
    path: "/issues",
    heading: "Incidents",
    labels: ["Loaded failures", "Replay gaps", "Verified fixes", "Loaded impact", "Issue queue"],
  },
  {
    path: "/replay",
    heading: "Replay",
    labels: ["Replay proof engine", "Visible runs", "Verified fixes", "Live queue", "Protected spend", "Start replay"],
  },
  {
    path: "/contracts",
    heading: "Contracts",
    labels: ["Regression contracts", "Active", "Draft", "Fixtures", "Import fixtures"],
  },
  {
    path: "/ci-gates",
    heading: "CI Gates",
    labels: ["Failed / blocked", "Not verified", "Running / pending", "Passed", "Protected flows", "Regression CI runs"],
  },
];

function reliabilityDetailRoutes(): ReliabilityRoute[] {
  const seed = readSeed();
  return [
    {
      path: `/issues/${seed.issue_id}`,
      heading: "Refund support agent is selecting the wrong tool",
      labels: [
        "Recommended next action",
        "Executive diagnosis",
        "Evidence workbench",
        "Replay, Contract, and CI readiness",
        "Active Contract linked",
        "CI gate readiness",
      ],
    },
    {
      path: `/replay/${seed.replay_run_id}`,
      heading: "Replay",
      labels: ["Replay setup", "Original Failure", "Candidate Replay", "Verification Result", "RF-1001"],
    },
    {
      path: `/ci-gates/${seed.ci_run_id}`,
      heading: `Run ${seed.ci_run_id}`,
      labels: [
        "Regression rate",
        "Contract gate evidence",
        "Regression CI blocked this change.",
        "Replay evidence",
        "Contract",
      ],
    },
  ];
}

async function expectSinglePageHeading(page: Page, heading: string): Promise<void> {
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
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
  test("renders primary workflow routes with stable headings, shell, and summary copy", async ({ page }) => {
    test.setTimeout(180_000);

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    for (const route of RELIABILITY_ROUTES) {
      await test.step(route.path, async () => {
        await page.goto(route.path);
        await expectDashboardShell(page);
        await expectMainContentFitsViewport(page);
        await expectSinglePageHeading(page, route.heading);
        await expectVisibleTexts(page, route.labels);
      });
    }

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });

  test("renders primary workflow detail pages with stable proof sections", async ({ page }) => {
    test.setTimeout(180_000);

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    for (const route of reliabilityDetailRoutes()) {
      await test.step(route.path, async () => {
        await page.goto(route.path);
        await expectDashboardShell(page);
        await expectMainContentFitsViewport(page);
        await expectSinglePageHeading(page, route.heading);
        await expectVisibleTexts(page, route.labels);
      });
    }

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
