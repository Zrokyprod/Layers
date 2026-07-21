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
      "approvals",
      "evidence",
      "home",
      "integrations",
      "operations",
      "outcomes",
      "policies",
      "projects",
      "settings",
      "workflows",
    ]);
  });

  it("keeps the paid dashboard primary IA frozen", () => {
    expect(DASHBOARD_PRIMARY_ROUTES.map((route) => route.href)).toEqual([
      "/home",
      "/operations",
      "/workflows",
      "/integrations",
      "/evidence",
      "/settings",
    ]);
    expect(DASHBOARD_PRIMARY_ROUTES.map((route) => route.label)).toEqual([
      "Home",
      "Operations",
      "Workflows",
      "Systems",
      "Evidence",
      "Settings",
    ]);
  });

  it("keeps final support pages protected but out of primary IA", () => {
    expect(DASHBOARD_SUPPORT_ROUTES.map((route) => route.href)).toEqual([
      "/account",
      "/approvals",
      "/outcomes",
      "/policies",
      "/projects",
    ]);
    expect(DASHBOARD_PROTECTED_PREFIXES).toEqual([
      "/home",
      "/operations",
      "/workflows",
      "/integrations",
      "/evidence",
      "/settings",
      "/account",
      "/approvals",
      "/outcomes",
      "/policies",
      "/projects",
    ]);
  });

  it("classifies route prefixes for shell and auth guard reuse", () => {
    expect(isDashboardPrimaryPath("/settings/keys")).toBe(true);
    expect(isDashboardPrimaryPath("/issues/issue_1")).toBe(false);
    expect(isDashboardProtectedPath("/contracts/contract_1")).toBe(false);
    expect(isDashboardProtectedPath("/pricing")).toBe(false);
    expect(DASHBOARD_RETIRED_PREFIXES).toEqual([
      "/actions",
      "/agents",
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
