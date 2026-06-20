import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { guardDashboardRoute } from "./route-auth-guard";

function request(url: string, token?: string): NextRequest {
  const headers = token ? { Cookie: `zroky_access_token=${token}` } : undefined;
  return new NextRequest(url, { headers });
}

describe("guardDashboardRoute", () => {
  it("redirects retired labs and drift routes to the Command Center", () => {
    const drift = guardDashboardRoute(request("https://app.zroky.com/drift", "token"));
    const labs = guardDashboardRoute(request("https://app.zroky.com/labs", "token"));
    const labsAgents = guardDashboardRoute(request("https://app.zroky.com/labs/agents", "token"));
    const labsDrift = guardDashboardRoute(request("https://app.zroky.com/labs/drift", "token"));

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
    const agents = guardDashboardRoute(request("https://app.zroky.com/agents"));
    const approvals = guardDashboardRoute(request("https://app.zroky.com/approvals"));
    const policies = guardDashboardRoute(request("https://app.zroky.com/policies"));
    const integrations = guardDashboardRoute(request("https://app.zroky.com/integrations"));
    const outcomes = guardDashboardRoute(request("https://app.zroky.com/outcomes?verdict=mismatched"));
    const projects = guardDashboardRoute(request("https://app.zroky.com/projects/proj_1"));
    const contracts = guardDashboardRoute(request("https://app.zroky.com/contracts/contract_1?tab=proof"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fhome");
    expect(agents.status).toBe(307);
    expect(agents.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fagents");
    expect(approvals.status).toBe(307);
    expect(approvals.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fapprovals");
    expect(policies.status).toBe(307);
    expect(policies.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fpolicies");
    expect(integrations.status).toBe(307);
    expect(integrations.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fintegrations");
    expect(outcomes.status).toBe(307);
    expect(outcomes.headers.get("location")).toBe(
      "https://app.zroky.com/login?next=%2Foutcomes%3Fverdict%3Dmismatched",
    );
    expect(projects.status).toBe(307);
    expect(projects.headers.get("location")).toBe("https://app.zroky.com/login?next=%2Fprojects%2Fproj_1");
    expect(contracts.status).toBe(307);
    expect(contracts.headers.get("location")).toBe(
      "https://app.zroky.com/login?next=%2Fcontracts%2Fcontract_1%3Ftab%3Dproof",
    );
  });
});
