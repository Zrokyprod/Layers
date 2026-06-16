import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { POST as clearSession } from "./clear-session/route";
import { POST as refreshSession } from "./refresh-session/route";
import { POST as setSession } from "./set-session/route";

describe("auth session API routes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("clears session cookies", async () => {
    const response = await clearSession();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    const setCookie = response.headers.get("set-cookie");
    expect(setCookie).toContain("zroky_access_token=");
    expect(setCookie).toContain("zroky_refresh_token=");
    expect(setCookie).toContain("SameSite=lax");
  });

  it("sets session cookies from a valid token payload", async () => {
    const request = new NextRequest("http://localhost/api/auth/set-session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        access_token: "access-token",
        refresh_token: "refresh-token",
        access_max_age_seconds: 3600,
        refresh_max_age_seconds: 7200,
      }),
    });

    const response = await setSession(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    const setCookie = response.headers.get("set-cookie");
    expect(setCookie).toContain("zroky_access_token=access-token");
    expect(setCookie).toContain("zroky_refresh_token=refresh-token");
    expect(setCookie).toContain("SameSite=lax");
  });

  it("rejects malformed set-session payloads", async () => {
    const request = new NextRequest("http://localhost/api/auth/set-session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ access_token: "access-token" }),
    });

    const response = await setSession(request);

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "Missing required fields" });
  });

  it("refreshes session cookies without returning backend tokens to the browser", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        access_token: "rotated-access-token",
        refresh_token: "rotated-refresh-token",
        access_expires_in_seconds: 3600,
        refresh_expires_in_seconds: 7200,
        email_verified: true,
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/auth/refresh-session", {
      method: "POST",
      headers: {
        cookie: "zroky_refresh_token=old-refresh-token",
      },
    });

    const response = await refreshSession(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      access_expires_in_seconds: 3600,
      refresh_expires_in_seconds: 7200,
      email_verified: true,
    });
    const setCookie = response.headers.get("set-cookie");
    expect(setCookie).toContain("zroky_access_token=rotated-access-token");
    expect(setCookie).toContain("zroky_refresh_token=rotated-refresh-token");
    expect(setCookie).toContain("SameSite=lax");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/auth/refresh");
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).body).toBe(JSON.stringify({ refresh_token: "old-refresh-token" }));
  });

  it("rejects refresh without a refresh cookie", async () => {
    const request = new NextRequest("http://localhost/api/auth/refresh-session", {
      method: "POST",
    });

    const response = await refreshSession(request);

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "Missing refresh session" });
  });

  it("does not use public API URL variables for refresh-session backend calls", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/auth/refresh-session", {
      method: "POST",
      headers: {
        cookie: "zroky_refresh_token=old-refresh-token",
      },
    });

    const response = await refreshSession(request);

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toEqual({ error: "ZROKY_API_BASE_URL is required in production." });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
