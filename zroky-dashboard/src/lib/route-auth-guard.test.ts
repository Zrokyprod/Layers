import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { guardDashboardRoute } from "./route-auth-guard";

function request(url: string, token?: string): NextRequest {
  const headers = token ? { Cookie: `zroky_access_token=${token}` } : undefined;
  return new NextRequest(url, { headers });
}

describe("guardDashboardRoute", () => {
  it("redirects retired labs, agent, and drift routes to the Failure Inbox", () => {
    const agents = guardDashboardRoute(request("https://app.zroky.com/agents?window=7d", "token"));
    const drift = guardDashboardRoute(request("https://app.zroky.com/drift", "token"));
    const labs = guardDashboardRoute(request("https://app.zroky.com/labs", "token"));
    const labsAgents = guardDashboardRoute(request("https://app.zroky.com/labs/agents", "token"));
    const labsDrift = guardDashboardRoute(request("https://app.zroky.com/labs/drift", "token"));

    expect(agents.status).toBe(307);
    expect(agents.headers.get("location")).toBe("https://app.zroky.com/home");
    expect(drift.status).toBe(307);
    expect(drift.headers.get("location")).toBe("https://app.zroky.com/home");
    expect(labs.status).toBe(307);
    expect(labs.headers.get("location")).toBe("https://app.zroky.com/home");
    expect(labsAgents.status).toBe(307);
    expect(labsAgents.headers.get("location")).toBe("https://app.zroky.com/home");
    expect(labsDrift.status).toBe(307);
    expect(labsDrift.headers.get("location")).toBe("https://app.zroky.com/home");
  });

  it("still protects active dashboard routes", () => {
    const response = guardDashboardRoute(request("https://app.zroky.com/home"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fhome");
  });
});
