import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { POST as clearSession } from "./clear-session/route";
import { POST as setSession } from "./set-session/route";

describe("auth session API routes", () => {
  it("clears session cookies", async () => {
    const response = await clearSession();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(response.headers.get("set-cookie")).toContain("zroky_access_token=");
    expect(response.headers.get("set-cookie")).toContain("zroky_refresh_token=");
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
    expect(response.headers.get("set-cookie")).toContain("zroky_access_token=access-token");
    expect(response.headers.get("set-cookie")).toContain("zroky_refresh_token=refresh-token");
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
});
