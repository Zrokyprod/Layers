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

async function expectHomeCockpitLayout(page: Page): Promise<void> {
  await expect(page.locator(".fi-a-verdict")).toBeVisible();
  await expect(page.locator(".fi-a-snapshot-grid")).toBeVisible();
  await expect(page.locator(".fi-a-workspace")).toBeVisible();
  await expect(page.locator(".fi-a-loop")).toBeVisible();
  await expect(page.locator(".fi-a-proof-panel")).toBeVisible();

  const layout = await page.evaluate(() => {
    function gridColumnCount(value: string): number {
      return value.split(" ").filter(Boolean).length;
    }

    const verdict = document.querySelector<HTMLElement>(".fi-a-verdict");
    const snapshots = document.querySelector<HTMLElement>(".fi-a-snapshot-grid");
    const firstSnapshot = document.querySelector<HTMLElement>(".fi-a-snapshot-card");
    const workspace = document.querySelector<HTMLElement>(".fi-a-workspace");
    const loop = document.querySelector<HTMLElement>(".fi-a-loop");
    const proofPanel = document.querySelector<HTMLElement>(".fi-a-proof-panel");

    if (!verdict || !snapshots || !firstSnapshot || !workspace || !loop || !proofPanel) {
      return null;
    }

    const verdictStyle = window.getComputedStyle(verdict);
    const snapshotsStyle = window.getComputedStyle(snapshots);
    const firstSnapshotStyle = window.getComputedStyle(firstSnapshot);
    const workspaceStyle = window.getComputedStyle(workspace);
    const loopStyle = window.getComputedStyle(loop);
    const proofPanelRect = proofPanel.getBoundingClientRect();

    return {
      firstSnapshotDisplay: firstSnapshotStyle.display,
      loopColumns: gridColumnCount(loopStyle.gridTemplateColumns),
      loopDisplay: loopStyle.display,
      proofPanelWidth: proofPanelRect.width,
      snapshotColumns: gridColumnCount(snapshotsStyle.gridTemplateColumns),
      snapshotsDisplay: snapshotsStyle.display,
      verdictDisplay: verdictStyle.display,
      viewportWidth: window.innerWidth,
      workspaceColumns: gridColumnCount(workspaceStyle.gridTemplateColumns),
      workspaceDisplay: workspaceStyle.display,
    };
  });

  expect(layout).not.toBeNull();
  expect(layout?.verdictDisplay).toBe("grid");
  expect(layout?.snapshotsDisplay).toBe("grid");
  expect(layout?.firstSnapshotDisplay).toBe("grid");
  if ((layout?.viewportWidth ?? 0) <= 620) {
    expect(layout?.snapshotColumns).toBe(1);
  } else {
    expect(layout?.snapshotColumns).toBeGreaterThanOrEqual(3);
  }
  expect(layout?.workspaceDisplay).toBe("grid");
  expect(layout?.workspaceColumns).toBeGreaterThanOrEqual(1);
  expect(layout?.loopDisplay).toBe("grid");
  if ((layout?.viewportWidth ?? 0) <= 620) {
    expect(layout?.loopColumns).toBe(1);
  } else {
    expect(layout?.loopColumns).toBeGreaterThanOrEqual(3);
  }
  expect(layout?.proofPanelWidth).toBeGreaterThanOrEqual(300);
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
        if (route.path === "/home") {
          await expectHomeCockpitLayout(page);
        }
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
