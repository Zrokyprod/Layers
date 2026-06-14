import { expect, test, type Page } from "@playwright/test";

import { expectDashboardShell, expectVisibleTexts } from "./helpers";

type ReliabilityRoute = {
  path: string;
  heading: string;
  labels: string[];
};

const RELIABILITY_ROUTES: ReliabilityRoute[] = [
  {
    path: "/home",
    heading: "Command Center",
    labels: [
      "Critical & high",
      "Needs trusted replay",
      "Failure queue",
      "Replay proof",
      "Failed/not_verified CI gates",
      "Goldens needing review",
    ],
  },
  {
    path: "/issues",
    heading: "Failures",
    labels: ["Loaded failures", "Replay gaps", "Verified fixes", "Loaded impact", "Issue queue"],
  },
  {
    path: "/replay",
    heading: "Replay",
    labels: ["Replay proof engine", "Visible runs", "Verified fixes", "Live queue", "Protected spend", "Start replay"],
  },
  {
    path: "/goldens",
    heading: "Goldens",
    labels: ["Active Goldens", "Blocking CI", "Need review", "Last pass rate", "Golden sets"],
  },
  {
    path: "/ci-gates",
    heading: "CI Gates",
    labels: ["Failed / blocked", "Not verified", "Running / pending", "Passed", "Protected flows", "Regression CI runs"],
  },
];

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
});
