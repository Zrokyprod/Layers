import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, POST } from "./route";

describe("/api/owner/session", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("sets an HttpOnly owner cookie after backend verification", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total_users: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/owner/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token: "owner-secret" }),
    });

    const response = await POST(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(response.headers.get("set-cookie")).toContain("zroky_owner_token=owner-secret");
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/owner/stats");
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Record<string, string>)["x-zroky-admin-token"]).toBe(
      "owner-secret",
    );
  });

  it("does not return the owner token when verification fails", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unauthorized", { status: 401 })));

    const request = new NextRequest("http://localhost/api/owner/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token: "wrong-secret" }),
    });

    const response = await POST(request);

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({
      ok: false,
      error: "Owner session verification failed",
    });
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("verifies an existing owner cookie without exposing it", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ total_users: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/owner/session", {
      headers: {
        cookie: "zroky_owner_token=cookie-owner-token",
      },
    });

    const response = await GET(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Record<string, string>)["x-zroky-admin-token"]).toBe(
      "cookie-owner-token",
    );
  });

  it("clears the owner cookie", async () => {
    const response = await DELETE();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(response.headers.get("set-cookie")).toContain("zroky_owner_token=");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("does not use public API URL variables for owner token verification", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/owner/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token: "owner-secret" }),
    });

    const response = await POST(request);

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({ ok: false, error: "Backend API is unavailable" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
