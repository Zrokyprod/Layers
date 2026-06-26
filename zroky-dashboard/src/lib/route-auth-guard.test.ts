import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { guardDashboardRoute } from "./route-auth-guard";
import {
  DASHBOARD_PRIMARY_ROUTES,
  DASHBOARD_RETIRED_ROUTES,
  DASHBOARD_SUPPORT_ROUTES,
} from "./dashboard-route-contract";

function request(url: string, token?: string): NextRequest {
  const headers = token ? { Cookie: `zroky_access_token=${token}` } : undefined;
  return new NextRequest(url, { headers });
}

describe("guardDashboardRoute", () => {
  it("redirects every retired old dashboard route to Home", () => {
    for (const route of DASHBOARD_RETIRED_ROUTES) {
      for (const path of [route.href, `${route.href}/legacy_detail?tab=proof`]) {
        const response = guardDashboardRoute(request(`https://zroky.com${path}`, "token"));

        expect(response.status, path).toBe(307);
        expect(response.headers.get("location"), path).toBe("https://zroky.com/home");
      }
    }
  });

  it("still protects active dashboard routes", () => {
    const response = guardDashboardRoute(request("https://zroky.com/home"));
    const agents = guardDashboardRoute(request("https://zroky.com/agents"));
    const approvals = guardDashboardRoute(request("https://zroky.com/approvals"));
    const policies = guardDashboardRoute(request("https://zroky.com/policies"));
    const integrations = guardDashboardRoute(request("https://zroky.com/integrations"));
    const evidence = guardDashboardRoute(request("https://zroky.com/evidence"));
    const outcomes = guardDashboardRoute(request("https://zroky.com/outcomes?verdict=mismatched"));
    const projects = guardDashboardRoute(request("https://zroky.com/projects/proj_1"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://zroky.com/login?next=%2Fhome");
    expect(agents.status).toBe(307);
    expect(agents.headers.get("location")).toBe("https://zroky.com/login?next=%2Fagents");
    expect(approvals.status).toBe(307);
    expect(approvals.headers.get("location")).toBe("https://zroky.com/login?next=%2Fapprovals");
    expect(policies.status).toBe(307);
    expect(policies.headers.get("location")).toBe("https://zroky.com/login?next=%2Fpolicies");
    expect(integrations.status).toBe(307);
    expect(integrations.headers.get("location")).toBe("https://zroky.com/login?next=%2Fintegrations");
    expect(evidence.status).toBe(307);
    expect(evidence.headers.get("location")).toBe("https://zroky.com/login?next=%2Fevidence");
    expect(outcomes.status).toBe(307);
    expect(outcomes.headers.get("location")).toBe(
      "https://zroky.com/login?next=%2Foutcomes%3Fverdict%3Dmismatched",
    );
    expect(projects.status).toBe(307);
    expect(projects.headers.get("location")).toBe("https://zroky.com/login?next=%2Fprojects%2Fproj_1");
  });

  it("protects every primary and support route from the shared dashboard contract", () => {
    const routes = [...DASHBOARD_PRIMARY_ROUTES, ...DASHBOARD_SUPPORT_ROUTES];

    for (const route of routes) {
      const response = guardDashboardRoute(request(`https://zroky.com${route.href}`));

      expect(response.status, route.href).toBe(307);
      expect(response.headers.get("location"), route.href).toBe(
        `https://zroky.com/login?next=${encodeURIComponent(route.href)}`,
      );
    }
  });
});
