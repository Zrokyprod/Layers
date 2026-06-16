import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";

describe("/auth/google/callback", () => {
  it("redirects valid Google OAuth callbacks to the backend proxy", () => {
    const request = new NextRequest(
      "https://app.zroky.com/auth/google/callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );

    const response = GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "https://app.zroky.com/api/zroky/v1/auth/google/callback?state=oauth-state&code=oauth-code&iss=https%3A%2F%2Faccounts.google.com",
    );
  });

  it("redirects provider errors back to login", () => {
    const request = new NextRequest(
      "https://app.zroky.com/auth/google/callback?error=access_denied",
    );

    const response = GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=access_denied");
  });

  it("redirects missing callback parameters back to login", () => {
    const request = new NextRequest("https://app.zroky.com/auth/google/callback?state=oauth-state");

    const response = GET(request);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?error=oauth_failed");
  });
});
