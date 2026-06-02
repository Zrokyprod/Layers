import { expect, request as playwrightRequest, test } from "@playwright/test";

import { readSeed } from "./helpers";

const dashboardBaseURL = process.env.PLAYWRIGHT_BASE_URL
  ?? `http://localhost:${process.env.ZROKY_E2E_DASHBOARD_PORT ?? "3010"}`;

test.describe("dashboard proxy and session routes", () => {
  test("logged-out proxy returns backend JSON 401 quickly", async () => {
    const api = await playwrightRequest.newContext({
      baseURL: dashboardBaseURL,
      storageState: { cookies: [], origins: [] },
    });
    const started = Date.now();
    const response = await api.get("/api/zroky/v1/auth/me", { timeout: 5_000 });
    const elapsed = Date.now() - started;
    const contentType = response.headers()["content-type"] ?? "";
    const body = await response.text();

    expect(response.status()).toBe(401);
    expect(elapsed).toBeLessThan(5_000);
    expect(contentType).toContain("application/json");
    expect(body).toContain("Missing or invalid Authorization header");
    expect(body).not.toContain("<!DOCTYPE html>");
    await api.dispose();
  });

  test("set-session stores cookies, forwards bearer auth, and clear-session removes access", async () => {
    const seed = readSeed();
    const api = await playwrightRequest.newContext({ baseURL: dashboardBaseURL });

    const login = await api.post("/api/zroky/v1/auth/login", {
      data: { email: seed.email, password: seed.password },
    });
    expect(login.status()).toBe(200);
    const tokens = await login.json();

    const setSession = await api.post("/api/auth/set-session", {
      data: {
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
        access_max_age_seconds: tokens.access_expires_in_seconds,
        refresh_max_age_seconds: tokens.refresh_expires_in_seconds,
      },
    });
    expect(setSession.status()).toBe(200);

    const me = await api.get("/api/zroky/v1/auth/me");
    expect(me.status()).toBe(200);
    await expect(me.json()).resolves.toMatchObject({
      email: seed.email,
      user_id: seed.user_id,
      email_verified: true,
    });

    const clearSession = await api.post("/api/auth/clear-session");
    expect(clearSession.status()).toBe(200);

    const afterClear = await api.get("/api/zroky/v1/auth/me");
    expect(afterClear.status()).toBe(401);
    await api.dispose();
  });
});
