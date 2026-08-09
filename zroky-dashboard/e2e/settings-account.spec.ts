import { expect, test } from "@playwright/test";

import { expectDashboardShell, expectHealthyPage, expectVisibleTexts, readSeed } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("settings and account", () => {
  test("workspace settings pages render cleanly", async ({ page }) => {
    test.setTimeout(180_000);

    const pages = [
      { path: "/settings", labels: ["API keys", "Project keys", "Create key"] },
      { path: "/settings/keys", labels: ["API keys", "Project keys", "Create key"] },
      { path: "/settings/providers", labels: ["API keys", "Project keys", "Create key"] },
      { path: "/settings/team", labels: ["Members", "Invite member", "Project members"] },
      { path: "/settings/billing", labels: ["Plan & Billing", "Usage this month", "Available plans"] },
      { path: "/settings/evaluation", labels: ["API keys", "Project keys", "Create key"] },
      { path: "/settings/integrations", labels: ["Connectors", "Available systems", "Recent test-reads"] },
      { path: "/settings/integrations/slack", labels: ["Slack notifications", "Connected channel", "Test message"] },
      { path: "/settings/workspace", labels: ["Workspace", "Workspace details"] },
      { path: "/account", labels: ["Personal account", "Plan and workspace access"] },
    ];

    for (const item of pages) {
      await page.goto(item.path, { waitUntil: "networkidle" });
      await expectDashboardShell(page);
      await expectVisibleTexts(page, item.labels);

      const activeSettingsTab = page.locator(".settings-tab-link-active");
      if (await activeSettingsTab.count()) {
        await expect(activeSettingsTab.locator("strong")).toHaveCSS("color", "rgb(255, 255, 255)");
        const brokenLabelReferences = await page.locator("main [aria-labelledby]").evaluateAll((elements) =>
          elements.flatMap((element) => {
            const missing = (element.getAttribute("aria-labelledby") ?? "")
              .split(/\s+/)
              .filter((id) => id && !document.getElementById(id));
            return missing.length ? [{ html: element.outerHTML.slice(0, 160), missing }] : [];
          }),
        );
        expect(brokenLabelReferences).toEqual([]);
      }
    }
  });

  test("settings profile compatibility route redirects to account", async ({ page }) => {
    await page.goto("/settings/profile");
    await expect(page).toHaveURL(/\/account/);
    await expectDashboardShell(page);
    await expect(page.getByText("Personal account", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("API key confirmation keeps focus inside the native dialog and closes with Escape", async ({ page }) => {
    await page.goto("/settings/keys");
    await expectDashboardShell(page);

    const revokeTrigger = page.getByRole("button", { name: "Revoke" }).first();
    await revokeTrigger.focus();
    await revokeTrigger.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Revoke API key" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(revokeTrigger).toBeFocused();
  });

  test("API key create, rotate, and revoke flow works", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Mutation flow runs once in the desktop Chromium project.");

    await page.goto("/settings/keys");
    await expectDashboardShell(page);

    const keyName = `E2E key ${Date.now()}`;
    await page.getByLabel("Key name").fill(keyName);
    await page.getByLabel("Expires in days").fill("30");
    await page.getByRole("button", { name: "Create key" }).click();
    await expect(page.getByRole("heading", { name: "Key created" })).toBeVisible();
    await expect(page.locator(".settings-key-reveal")).toContainText("zk_live_");
    await page.getByRole("button", { name: "Done" }).click();

    await page.getByRole("button", { name: "Rotate" }).first().click();
    await expect(page.getByRole("dialog", { name: "Rotate API key" })).toBeVisible();
    await page.getByRole("button", { name: "Rotate and show replacement" }).click();
    await expect(page.getByRole("heading", { name: "Key created" })).toBeVisible();
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
    test.skip(testInfo.project.name !== "mobile-chromium", "Session-revoking password mutation runs once at the end of the mobile project.");
    test.setTimeout(60_000);

    const seed = readSeed();
    const temporaryPassword = "ZrokyDemo124!";
    const restoreSession = async (password: string) => {
      const login = await page.request.post("/api/zroky/v1/auth/login", {
        data: { email: seed.email, password },
      });
      expect(login.status(), await login.text()).toBe(200);
      const tokens = await login.json();
      const setSession = await page.request.post("/api/auth/set-session", {
        data: {
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token,
          access_max_age_seconds: tokens.access_expires_in_seconds,
          refresh_max_age_seconds: tokens.refresh_expires_in_seconds,
        },
      });
      expect(setSession.status(), await setSession.text()).toBe(200);
      await page.goto("/account");
      await expectDashboardShell(page);
    };
    const submitPasswordChange = async () => {
      const responsePromise = page.waitForResponse((response) => {
        return response.url().includes("/v1/auth/me/password") && response.request().method() === "PATCH";
      });
      await page.getByRole("button", { name: "Change password" }).click();
      const response = await responsePromise;
      expect(response.ok(), await response.text()).toBeTruthy();
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
    await restoreSession(temporaryPassword);

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
