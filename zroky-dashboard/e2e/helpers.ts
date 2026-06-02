import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export type E2ESeed = {
  api_key_id: string;
  call_id: string;
  ci_run_id: string;
  diagnosis_id: string;
  email: string;
  golden_set_id: string;
  golden_trace_id: string;
  invitation_id: string;
  issue_id: string;
  membership_id: string;
  password: string;
  project_id: string;
  replay_run_id: string;
  trace_id: string;
  user_id: string;
};

export const e2eDir = __dirname;
export const authDir = path.join(e2eDir, ".auth");
export const authStatePath = path.join(authDir, "user.json");
export const seedStatePath = path.join(authDir, "seed.json");

export function readSeed(): E2ESeed {
  return JSON.parse(fs.readFileSync(seedStatePath, "utf8")) as E2ESeed;
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const hasNoOverflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth <= window.innerWidth + 2;
  });
  expect(hasNoOverflow).toBeTruthy();
}

export async function expectHealthyPage(page: Page): Promise<void> {
  const body = page.locator("body");
  await expect(body).toBeVisible();
  const bodyText = await body.innerText();
  expect(bodyText).not.toContain("This page could not be found.");
  expect(bodyText).not.toContain("Requested resource was not found");
  expect(bodyText).not.toContain("Backend API is unavailable");
  expect(bodyText).not.toContain("<!DOCTYPE html>");
  await expectNoHorizontalOverflow(page);
}

export async function expectDashboardShell(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Search (Command Palette)" })).toBeVisible();
  const viewport = page.viewportSize();
  if (viewport && viewport.width <= 640) {
    await expect(page.getByRole("button", { name: "Toggle sidebar" })).toBeVisible();
  } else {
    await expect(page.locator("img[alt='Zroky']")).toBeVisible();
  }
  await expectHealthyPage(page);
}

export async function expectAnyVisibleText(page: Page, labels: string[]): Promise<void> {
  await expect
    .poll(
      async () => {
        for (const label of labels) {
          const locator = page.getByText(label, { exact: false });
          const count = await locator.count();
          for (let index = 0; index < count; index += 1) {
            if (await locator.nth(index).isVisible().catch(() => false)) {
              return label;
            }
          }
        }
        return "";
      },
      {
        message: `Expected one of these labels to be visible: ${labels.join(", ")}`,
        timeout: 15_000,
      },
    )
    .not.toBe("");
}
