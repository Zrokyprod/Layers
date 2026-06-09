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
    { path: "/auth/github/callback", text: /GitHub/i },
    { path: "/auth/github/connect/callback", text: /GitHub/i },
    { path: "/auth/oauth/callback", text: /Sign in to Zroky|Signing you in|OAuth/i },
    { path: "/auth/handoff", text: /Sign in to Zroky|Signing you in|handoff/i },
  ];

  const authAliases = [
    { path: "/auth?next=%2Fissues", canonical: /\/login\?next=%2Fissues$/ },
    { path: "/auth/login?next=%2Fhome", canonical: /\/login\?next=%2Fhome$/ },
    { path: "/auth/register?source=pricing", canonical: /\/signup\?source=pricing$/ },
    { path: "/auth/forgot-password?email=demo%40zroky.local", canonical: /\/forgot-password\?email=demo%40zroky.local$/ },
    { path: "/auth/reset-password?token=reset-token", canonical: /\/reset-password\?token=reset-token$/ },
    { path: "/auth/verify-email?token=verify-token", canonical: /\/verify-email\?token=verify-token$/ },
    { path: "/auth/check-email?email=demo%40zroky.local", canonical: /\/verify-email\?email=demo%40zroky.local$/ },
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

  for (const item of authAliases) {
    test(`${item.path} redirects to the canonical top-level auth route`, async ({ page }) => {
      await page.goto(item.path);

      await expect(page).toHaveURL(item.canonical);
      await expect(page.locator("body")).not.toContainText("This page could not be found.");
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

  test("logged-out dashboard routes redirect to login with return path", async ({ page }) => {
    await page.goto("/home");

    await expect(page).toHaveURL(/\/login\?next=%2Fhome$/);
    await expect(page.getByRole("heading", { name: "Sign in to Zroky" })).toBeVisible();
  });
});

test.describe("authenticated session", () => {
  test("seeded user can restore dashboard session and log out from account menu", async ({ page }) => {
    const seed = readSeed();
    await page.goto("/home");

    await expect(page.getByRole("heading", { name: "Failure Inbox" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open account menu" })).toBeVisible();
    await expectHealthyPage(page);

    await page.getByRole("button", { name: "Open account menu" }).click();
    const accountMenu = page.getByRole("menu", { name: "Account menu" });
    await expect(accountMenu).toBeVisible();
    await expect(accountMenu).toContainText(seed.email);
    await page.getByRole("menuitem", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
