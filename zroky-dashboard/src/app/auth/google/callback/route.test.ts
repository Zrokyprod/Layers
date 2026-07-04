import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";

describe("/auth/google/callback", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exchanges valid Google OAuth callbacks through the backend proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        access_token: "access-token",
        refresh_token: "refresh-token",
        access_expires_in_seconds: 3600,
        refresh_expires_in_seconds: 7200,
        token_type: "bearer",
        user_id: "user_123",
        email: "user@example.com",
        email_verified: true,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest(
      "https://zroky.com/auth/google/callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://zroky.com/home");
    const setCookie = response.headers.get("set-cookie");
    expect(setCookie).toContain("zroky_access_token=access-token");
    expect(setCookie).toContain("zroky_refresh_token=refresh-token");
    expect(setCookie).toContain("SameSite=lax");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "https://zroky.com/api/zroky/v1/auth/google/session-callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      cache: "no-store",
      redirect: "manual",
    });
  });

  it("redirects to pending protected-agent setup after a successful Google callback", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({
          access_token: "access-token",
          refresh_token: "refresh-token",
          access_expires_in_seconds: 3600,
          refresh_expires_in_seconds: 7200,
        }),
      ),
    );
    const pendingNext = encodeURIComponent("/agents/setup?intent=protect-agent&plan=pro");
    const request = new NextRequest(
      "https://zroky.com/auth/google/callback?state=oauth-state&code=oauth-code",
      {
        headers: {
          cookie: `zroky_post_auth_redirect=${pendingNext}`,
        },
      },
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "https://zroky.com/agents/setup?intent=protect-agent&plan=pro",
    );
    expect(response.headers.get("set-cookie")).toContain("zroky_post_auth_redirect=");
  });

  it("redirects provider errors back to login", async () => {
    const request = new NextRequest(
      "https://zroky.com/auth/google/callback?error=access_denied",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://zroky.com/login?error=access_denied");
  });

  it("redirects missing callback parameters back to login", async () => {
    const request = new NextRequest("https://zroky.com/auth/google/callback?state=oauth-state");

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://zroky.com/login?error=oauth_failed");
  });

  it("redirects invalid or expired backend state responses back to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({ detail: "Invalid or expired OAuth state. Please try signing in again." }, { status: 400 }),
      ),
    );
    const request = new NextRequest(
      "https://zroky.com/auth/google/callback?state=expired-state&code=oauth-code",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://zroky.com/login?error=oauth_expired");
  });

  it("redirects failed session completion back to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ detail: "Google sign-in failed." }, { status: 502 })),
    );
    const request = new NextRequest(
      "https://zroky.com/auth/google/callback?state=oauth-state&code=oauth-code",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://zroky.com/login?error=oauth_failed");
  });
});
