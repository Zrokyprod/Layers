import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function context(path: string[]) {
  return {
    params: Promise.resolve({ path }),
  };
}

describe("/api/zroky owner proxy route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("converts the HttpOnly owner cookie into backend owner auth", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    vi.stubEnv("ZROKY_PROVISIONING_TOKEN", "server-token-must-not-forward");
    vi.stubEnv("ZROKY_PROVISIONING_TOKEN_HEADER", "x-provisioning-token");
    vi.stubEnv("ZROKY_API_KEY", "server-api-key-must-not-forward");
    vi.stubEnv("ZROKY_PROJECT_ID", "proj_must_not_forward");

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total_users: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/owner/stats", {
      headers: {
        cookie: "zroky_owner_token=cookie-owner-token",
        "x-zroky-admin-token": "browser-owner-token-must-ignore",
      },
    });
    const response = await GET(request, context(["v1", "owner", "stats"]));

    expect(response.status).toBe(200);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/owner/stats");

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("x-zroky-admin-token")).toBe("cookie-owner-token");
    expect(headers.get("x-provisioning-token")).toBeNull();
    expect(headers.get("x-api-key")).toBeNull();
    expect(headers.get("x-project-id")).toBeNull();
  });

  it("does not trust browser-supplied owner headers when no owner cookie exists", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    vi.stubEnv("ZROKY_PROVISIONING_TOKEN", "server-token-must-not-forward");

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid owner credentials." }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/owner/stats", {
      headers: {
        "x-zroky-admin-token": "browser-owner-token-must-ignore",
      },
    });
    const response = await GET(request, context(["v1", "owner", "stats"]));

    expect(response.status).toBe(401);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("x-zroky-admin-token")).toBeNull();
    expect(headers.get("x-provisioning-token")).toBeNull();
  });

  it("blocks non-owner backend paths before attaching owner credentials", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/auth/me", {
      headers: {
        cookie: "zroky_owner_token=cookie-owner-token",
      },
    });
    const response = await GET(request, context(["v1", "auth", "me"]));

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ detail: "Owner proxy path is not allowed." });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows admin feature-interest paths through the owner proxy allowlist", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ features: [], generated_at: "2026-06-22T00:00:00.000Z" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/admin/feature-interest", {
      headers: {
        cookie: "zroky_owner_token=cookie-owner-token",
      },
    });
    const response = await GET(request, context(["v1", "admin", "feature-interest"]));

    expect(response.status).toBe(200);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/admin/feature-interest");
  });

  it("allows the live tool registry through the owner proxy allowlist", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        schema_version: "zroky.agent_tool_control.v1",
        project_id: "proj_owner",
        agent_id: null,
        action_type: null,
        runtime_paths: [],
        verification_connectors: [],
        native_tool_families: [],
        recommended: {
          action_types: [],
          runtime_path_ids: [],
          verification_connector_ids: [],
          native_tool_family_ids: [],
          next_steps: [],
        },
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/tools/registry", {
      headers: {
        cookie: "zroky_owner_token=cookie-owner-token",
      },
    });
    const response = await GET(request, context(["v1", "tools", "registry"]));

    expect(response.status).toBe(200);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://backend.test/v1/tools/registry");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("x-zroky-admin-token")).toBe("cookie-owner-token");
  });

  it("does not use public API URL variables for the owner backend proxy", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://backend.test");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/zroky/v1/owner/stats");
    const response = await GET(request, context(["v1", "owner", "stats"]));

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toEqual({ error: "ZROKY_API_BASE_URL is required in production." });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
