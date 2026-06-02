import { expect, test } from "@playwright/test";

import { expectHealthyPage, expectNoHorizontalOverflow, readSeed } from "./helpers";

test.describe("public auth pages", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  const publicPages = [
    { path: "/login", text: /Sign in to Zroky/i },
    { path: "/signup", text: /Create your Zroky workspace/i },
    { path: "/forgot-password", text: /Recover workspace access/i },
    { path: "/reset-password", text: /New password|Invalid or missing reset token/i },
    { path: "/verify-email", text: /Verify your email/i },
    { path: "/auth", text: /Sign in to Zroky/i },
    { path: "/auth/login", text: /Sign in to Zroky/i },
    { path: "/auth/register", text: /Create your Zroky workspace/i },
    { path: "/auth/forgot-password", text: /Recover workspace access/i },
    { path: "/auth/reset-password", text: /New password|Invalid or missing reset token/i },
    { path: "/auth/verify-email", text: /Verify your email/i },
    { path: "/auth/check-email", text: /Verify your email|Check your email/i },
    { path: "/auth/github/callback", text: /GitHub/i },
    { path: "/auth/github/connect/callback", text: /GitHub/i },
    { path: "/auth/oauth/callback", text: /Sign in to Zroky|Signing you in|OAuth/i },
    { path: "/auth/handoff", text: /Sign in to Zroky|Signing you in|handoff/i },
  ];

  for (const item of publicPages) {
    test(`${item.path} renders a clean auth state`, async ({ page }) => {
      await page.goto(item.path);
      await expect(page.locator("body")).toContainText(item.text);
      await expect(page.locator("body")).not.toContainText("This page could not be found.");
      await expect(page.locator("body")).not.toContainText("Requested resource was not found");
      await expectNoHorizontalOverflow(page);
    });
  }

  test("login validation and password visibility work", async ({ page }) => {
    await page.goto("/login");

    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("form")).toContainText("email", { ignoreCase: true });

    const password = page.locator("#login-password");
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(password).toHaveAttribute("type", "text");
  });
});

test.describe("authenticated session", () => {
  test("seeded user can restore dashboard session and log out from account menu", async ({ page }) => {
    const seed = readSeed();
    await page.goto("/home");

    await expect(page.getByRole("heading", { name: "Failure Inbox" })).toBeVisible();
    const viewport = page.viewportSize();
    if (viewport && viewport.width <= 640) {
      await page.getByRole("button", { name: "Toggle sidebar" }).click();
    } else {
      await expect(page.getByText(seed.email, { exact: false })).toBeVisible();
    }
    await expectHealthyPage(page);

    await page.getByRole("button", { name: "Open account menu" }).click();
    await expect(page.getByRole("menu", { name: "Account menu" })).toBeVisible();
    await page.getByRole("menuitem", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
