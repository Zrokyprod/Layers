import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("login page loads", async ({ page }) => {
    await page.goto("/auth/login");
    await expect(page.locator("h1, h2, h3").first()).toBeVisible();
  });

  test("register page loads", async ({ page }) => {
    await page.goto("/auth/register");
    await expect(page.locator("h1, h2, h3").first()).toBeVisible();
  });
});
