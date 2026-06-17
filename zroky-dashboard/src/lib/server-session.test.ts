import { afterEach, describe, expect, it, vi } from "vitest";

import { checkDashboardSession } from "./server-session";

describe("checkDashboardSession", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("returns an authenticated but unverified user from the backend session", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "https://api.zroky.test");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        user_id: "user_1",
        email: "demo@example.com",
        email_verified: false,
        is_active: true,
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const session = await checkDashboardSession("access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.zroky.test/v1/auth/me",
      expect.objectContaining({
        cache: "no-store",
        headers: { authorization: "Bearer access-token" },
      }),
    );
    expect(session).toEqual({
      status: "authenticated",
      user: {
        user_id: "user_1",
        email: "demo@example.com",
        email_verified: false,
        is_active: true,
      },
    });
  });

  it("treats rejected backend sessions as unauthenticated", async () => {
    vi.stubEnv("ZROKY_API_BASE_URL", "https://api.zroky.test");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));

    await expect(checkDashboardSession("bad-token")).resolves.toEqual({ status: "unauthenticated" });
  });
});
