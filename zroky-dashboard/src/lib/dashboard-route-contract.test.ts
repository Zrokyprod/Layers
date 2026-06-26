import { describe, expect, it } from "vitest";
import { readdirSync } from "node:fs";
import { join } from "node:path";

import {
  DASHBOARD_PRIMARY_ROUTES,
  DASHBOARD_PROTECTED_PREFIXES,
  DASHBOARD_RETIRED_PREFIXES,
  DASHBOARD_SUPPORT_ROUTES,
  isDashboardPrimaryPath,
  isDashboardProtectedPath,
  isDashboardRetiredPath,
} from "./dashboard-route-contract";

describe("dashboard route contract", () => {
  it("keeps deleted legacy dashboard route directories from coming back", () => {
    const routeDirectories = readdirSync(join(process.cwd(), "src", "app", "(dashboard)"), {
      withFileTypes: true,
    })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();

    expect(routeDirectories).toEqual([
      "account",
      "actions",
      "agents",
      "approvals",
      "evidence",
      "home",
      "integrations",
      "outcomes",
      "policies",
      "projects",
      "settings",
    ]);
  });

  it("keeps the paid dashboard primary IA frozen", () => {
    expect(DASHBOARD_PRIMARY_ROUTES.map((route) => route.href)).toEqual([
      "/home",
      "/actions",
      "/agents",
      "/approvals",
      "/outcomes",
      "/evidence",
      "/integrations",
      "/policies",
      "/settings",
    ]);
    expect(DASHBOARD_PRIMARY_ROUTES.map((route) => route.label)).toEqual([
      "Home",
      "Actions",
      "Agents",
      "Approvals",
      "Outcomes",
      "Evidence",
      "Connectors",
      "Policies",
      "Settings",
    ]);
  });

  it("keeps only account and project management as non-primary support routes", () => {
    expect(DASHBOARD_SUPPORT_ROUTES.map((route) => route.href)).toEqual([
      "/account",
      "/projects",
    ]);
    expect(DASHBOARD_PROTECTED_PREFIXES).toEqual([
      "/home",
      "/actions",
      "/agents",
      "/approvals",
      "/outcomes",
      "/evidence",
      "/integrations",
      "/policies",
      "/settings",
      "/account",
      "/projects",
    ]);
  });

  it("classifies route prefixes for shell and auth guard reuse", () => {
    expect(isDashboardPrimaryPath("/settings/keys")).toBe(true);
    expect(isDashboardPrimaryPath("/issues/issue_1")).toBe(false);
    expect(isDashboardProtectedPath("/contracts/contract_1")).toBe(false);
    expect(isDashboardProtectedPath("/pricing")).toBe(false);
    expect(DASHBOARD_RETIRED_PREFIXES).toEqual([
      "/alerts",
      "/calls",
      "/ci-gates",
      "/contracts",
      "/cost",
      "/goldens",
      "/incidents",
      "/issues",
      "/replay",
      "/trace",
      "/drift",
      "/labs",
    ]);
    expect(isDashboardRetiredPath("/contracts/contract_1")).toBe(true);
    expect(isDashboardRetiredPath("/incidents")).toBe(true);
    expect(isDashboardProtectedPath("/incidents")).toBe(false);
    expect(isDashboardRetiredPath("/labs/drift")).toBe(true);
    expect(isDashboardRetiredPath("/home")).toBe(false);
  });
});
