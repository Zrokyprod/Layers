import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectHealthyPage, expectVisibleTexts, readSeed } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("settings and account", () => {
  test("workspace settings pages render cleanly", async ({ page }) => {
    test.setTimeout(180_000);

    const pages = [
      { path: "/settings", labels: ["Settings", "Workspace control plane", "Create project key"] },
      { path: "/settings/keys", labels: ["Project API keys", "Create project key"] },
      { path: "/settings/providers", labels: ["Settings", "Workspace control plane", "API Keys"] },
      { path: "/settings/team", labels: ["Project Members", "teammate@zroky.local"] },
      { path: "/settings/billing", labels: ["Plan", "Billing", "Pro"] },
      { path: "/settings/evaluation", labels: ["Settings", "Workspace control plane", "Plan & Billing"] },
      { path: "/settings/integrations", labels: ["Connectors", "Slack"] },
      { path: "/settings/integrations/slack", labels: ["Slack", "Not connected", "Connect Slack"] },
      { path: "/settings/workspace", labels: ["Workspace boundary", "Workspace identity", "Manage members"] },
      { path: "/account", labels: ["Your identity", "Account security"] },
    ];

    for (const item of pages) {
      await page.goto(item.path);
      await expectDashboardShell(page);
      await expectVisibleTexts(page, item.labels);
    }
  });

  test("settings profile compatibility route redirects to account", async ({ page }) => {
    await page.goto("/settings/profile");
    await expect(page).toHaveURL(/\/account/);
    await expectDashboardShell(page);
    await expect(page.getByText("Your identity", { exact: false })).toBeVisible();
  });

  test("API key create, rotate, and revoke flow works", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Mutation flow runs once in the desktop Chromium project.");

    await page.goto("/settings/keys");
    await expectDashboardShell(page);

    const keyName = `E2E key ${Date.now()}`;
    await page.getByLabel("Key name").fill(keyName);
    await page.getByLabel("Expires in days").fill("30");
    await page.getByRole("button", { name: "Create project key" }).click();
    await expect(page.getByRole("heading", { name: "Copy this project key now." })).toBeVisible();
    await expect(page.locator(".settings-key-reveal")).toContainText("zk_live_");
    await page.getByRole("button", { name: "Done" }).click();

    await page.getByRole("button", { name: "Rotate" }).first().click();
    await expect(page.getByRole("dialog", { name: "Rotate API key" })).toBeVisible();
    await page.getByRole("button", { name: "Rotate and show replacement" }).click();
    await expect(page.getByRole("heading", { name: "Copy this project key now." })).toBeVisible();
    await page.getByRole("button", { name: "Done" }).click();

    await page.getByRole("button", { name: "Revoke" }).first().click();
    await expect(page.getByRole("dialog", { name: "Revoke API key" })).toBeVisible();
    await page.getByRole("button", { name: "Yes, revoke key" }).click();
    await expect(page.getByText("Revoked", { exact: true })).toBeVisible();
    await expectHealthyPage(page);
  });

  test("members invite and revoke flow works", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Mutation flow runs once in the desktop Chromium project.");

    await page.goto("/settings/team");
    await expectDashboardShell(page);

    const seed = readSeed();
    const inviteEmail = `e2e-${Date.now()}@zroky.local`;
    await page.getByLabel("Email").fill(inviteEmail);
    await page.locator("#invite-role").selectOption("member");
    const inviteResponsePromise = page.waitForResponse((response) => {
      return response.url().includes(`/v1/invitations/projects/${seed.project_id}/invitations`)
        && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Send invite" }).click();
    const inviteResponse = await inviteResponsePromise;
    expect(inviteResponse.status()).toBe(201);
    const row = page.locator(".team-member-row").filter({ hasText: inviteEmail });
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row.getByText("Pending", { exact: true })).toBeVisible();

    await row.getByTitle("Revoke invitation").click();
    await expect(page.locator(".team-member-row").filter({ hasText: inviteEmail })).toHaveCount(0);
    await expectHealthyPage(page);
  });

  test("account profile, password, sessions, and delete confirmation are wired", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Password mutation runs once in the desktop Chromium project.");
    test.setTimeout(60_000);

    const seed = readSeed();
    const temporaryPassword = "ZrokyDemo124!";
    const submitPasswordChange = async () => {
      const responsePromise = page.waitForResponse((response) => {
        return response.url().includes("/v1/auth/me/password") && response.request().method() === "PATCH";
      });
      await page.getByRole("button", { name: "Change password" }).click();
      const response = await responsePromise;
      expect(response.ok()).toBeTruthy();
      await expect(page.getByText("Password changed successfully.")).toBeVisible({ timeout: 15_000 });
    };

    await page.goto("/account");
    await expectDashboardShell(page);

    await page.getByLabel("Display name").fill("Zroky Demo Owner");
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByText("Profile updated.")).toBeVisible();

    await page.getByRole("textbox", { name: "Current password" }).fill(seed.password);
    await page.getByRole("textbox", { name: "New password", exact: true }).fill(temporaryPassword);
    await page.getByRole("textbox", { name: "Confirm new password" }).fill(temporaryPassword);
    await submitPasswordChange();

    await page.getByRole("textbox", { name: "Current password" }).fill(temporaryPassword);
    await page.getByRole("textbox", { name: "New password", exact: true }).fill(seed.password);
    await page.getByRole("textbox", { name: "Confirm new password" }).fill(seed.password);
    await submitPasswordChange();

    await expect(page.getByRole("button", { name: "Log out all sessions" })).toBeEnabled();
    await page.getByRole("button", { name: "Delete my account" }).click();
    await expect(page.getByRole("button", { name: "Permanently delete account" })).toBeDisabled();
    await page.locator("input[placeholder='demo@zroky.local']").fill(seed.email);
    await expect(page.getByRole("button", { name: "Permanently delete account" })).toBeEnabled();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expectHealthyPage(page);
  });
});
