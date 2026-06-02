import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { DELETE, GET } from "./route";

function context(path: string[]) {
  return {
    params: Promise.resolve({ path }),
  };
}

describe("/api/zroky proxy route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("forwards backend status and JSON content", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Missing project context." }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/settings/project?mode=preview");
    const response = await GET(request, context(["v1", "settings", "project"]));

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ detail: "Missing project context." });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/settings/project?mode=preview");
  });

  it("converts the session cookie into backend bearer auth", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ email: "sanket@acme.com" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/auth/me", {
      headers: {
        cookie: "zroky_access_token=local-token",
      },
    });
    await GET(request, context(["v1", "auth", "me"]));

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("authorization")).toBe("Bearer local-token");
  });

  it("returns clean JSON when the backend is unavailable", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://127.0.0.1:8999");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connect ECONNREFUSED")));

    const request = new NextRequest("http://localhost/api/zroky/v1/auth/me");
    const response = await GET(request, context(["v1", "auth", "me"]));

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      detail: "Backend API is unavailable. Start the Zroky backend and retry.",
    });
  });

  it("forwards no-content responses without attaching a body", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/goldens/golden_1", {
      method: "DELETE",
    });
    const response = await DELETE(request, context(["v1", "goldens", "golden_1"]));

    expect(response.status).toBe(204);
    await expect(response.text()).resolves.toBe("");
  });

  it("allows a local backend in production only when the explicit E2E flag is set", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("ZROKY_API_BASE_URL", "http://127.0.0.1:8000");
    vi.stubEnv("ZROKY_ALLOW_LOCAL_API_BASE_URL", "1");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Missing bearer token." }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/auth/me");
    const response = await GET(request, context(["v1", "auth", "me"]));

    expect(response.status).toBe(401);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8000/v1/auth/me");
  });
});
