import { test, expect } from "@playwright/test";

test.describe("Owner Dashboard", () => {
  test("owner login requires provisioning token", async ({ page }) => {
    await page.goto("/owner");
    // Should redirect or show auth prompt when no token is present
    await expect(page.locator("body")).toContainText(/login|token|unauthorized/i);
  });
});
