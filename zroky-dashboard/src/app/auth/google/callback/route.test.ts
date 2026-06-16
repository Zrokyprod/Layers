import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";

describe("/auth/google/callback", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exchanges valid Google OAuth callbacks through the backend proxy", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 302,
          headers: {
            location: "https://app.zroky.com/auth/oauth/callback?handoff_id=handoff_123",
          },
        }),
      )
      .mockResolvedValueOnce(
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
      "https://app.zroky.com/auth/google/callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/home");
    expect(response.headers.get("set-cookie")).toContain("zroky_access_token=access-token");
    expect(response.headers.get("set-cookie")).toContain("zroky_refresh_token=refresh-token");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "https://app.zroky.com/api/zroky/v1/auth/google/callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      cache: "no-store",
      redirect: "manual",
    });
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("https://app.zroky.com/api/zroky/v1/auth/oauth/handoff");
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      cache: "no-store",
      body: JSON.stringify({ handoff_id: "handoff_123" }),
    });
  });

  it("redirects provider errors back to login", async () => {
    const request = new NextRequest(
      "https://app.zroky.com/auth/google/callback?error=access_denied",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=access_denied");
  });

  it("redirects missing callback parameters back to login", async () => {
    const request = new NextRequest("https://app.zroky.com/auth/google/callback?state=oauth-state");

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=oauth_failed");
  });

  it("redirects invalid or expired backend state responses back to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({ detail: "Invalid or expired OAuth state. Please try signing in again." }, { status: 400 }),
      ),
    );
    const request = new NextRequest(
      "https://app.zroky.com/auth/google/callback?state=expired-state&code=oauth-code",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=oauth_expired");
  });

  it("redirects failed handoff completion back to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(null, {
            status: 302,
            headers: {
              location: "https://app.zroky.com/auth/oauth/callback?handoff_id=handoff_123",
            },
          }),
        )
        .mockResolvedValueOnce(Response.json({ detail: "Invalid or expired OAuth handoff." }, { status: 400 })),
    );
    const request = new NextRequest(
      "https://app.zroky.com/auth/google/callback?state=oauth-state&code=oauth-code",
    );

    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=oauth_failed");
  });
});
