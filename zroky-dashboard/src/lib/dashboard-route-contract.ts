export type DashboardRouteKind = "primary" | "support" | "retired";

export type DashboardRouteContract = {
  id: string;
  href: string;
  label: string;
  kind: DashboardRouteKind;
};

export const DASHBOARD_ROUTE_CONTRACT = [
  { id: "home", href: "/home", label: "Home", kind: "primary" },
  { id: "operations", href: "/operations", label: "Operations", kind: "primary" },
  { id: "workflows", href: "/workflows", label: "Workflows", kind: "primary" },
  { id: "systems", href: "/integrations", label: "Systems", kind: "primary" },
  { id: "evidence", href: "/evidence", label: "Evidence", kind: "primary" },
  { id: "settings", href: "/settings", label: "Settings", kind: "primary" },
  { id: "account", href: "/account", label: "Account", kind: "support" },
  { id: "approvals", href: "/approvals", label: "Approvals", kind: "support" },
  { id: "outcomes", href: "/outcomes", label: "Outcomes", kind: "support" },
  { id: "policies", href: "/policies", label: "Policies", kind: "support" },
  { id: "projects", href: "/projects", label: "Projects", kind: "support" },
  { id: "actions", href: "/actions", label: "Actions", kind: "retired" },
  { id: "agents", href: "/agents", label: "Agents", kind: "retired" },
  { id: "alerts", href: "/alerts", label: "Alert Evidence", kind: "retired" },
  { id: "calls", href: "/calls", label: "Call Evidence", kind: "retired" },
  { id: "ci-gates", href: "/ci-gates", label: "CI Gates", kind: "retired" },
  { id: "contracts", href: "/contracts", label: "Contracts", kind: "retired" },
  { id: "cost", href: "/cost", label: "Cost Risk", kind: "retired" },
  { id: "fixtures", href: "/goldens", label: "Fixtures", kind: "retired" },
  { id: "incidents", href: "/incidents", label: "Incidents", kind: "retired" },
  { id: "issues", href: "/issues", label: "Issues", kind: "retired" },
  { id: "replay", href: "/replay", label: "Replay", kind: "retired" },
  { id: "traces", href: "/trace", label: "Traces", kind: "retired" },
  { id: "drift", href: "/drift", label: "Drift", kind: "retired" },
  { id: "labs", href: "/labs", label: "Labs", kind: "retired" },
] as const satisfies readonly DashboardRouteContract[];

export type DashboardRoute = (typeof DASHBOARD_ROUTE_CONTRACT)[number];
export type DashboardPrimaryRoute = Extract<DashboardRoute, { kind: "primary" }>;
export type DashboardSupportRoute = Extract<DashboardRoute, { kind: "support" }>;
export type DashboardRetiredRoute = Extract<DashboardRoute, { kind: "retired" }>;

export const DASHBOARD_PRIMARY_ROUTES = DASHBOARD_ROUTE_CONTRACT.filter(
  (route): route is DashboardPrimaryRoute => route.kind === "primary",
);

export const DASHBOARD_SUPPORT_ROUTES = DASHBOARD_ROUTE_CONTRACT.filter(
  (route): route is DashboardSupportRoute => route.kind === "support",
);

export const DASHBOARD_RETIRED_ROUTES = DASHBOARD_ROUTE_CONTRACT.filter(
  (route): route is DashboardRetiredRoute => route.kind === "retired",
);

export const DASHBOARD_PROTECTED_PREFIXES = [
  ...DASHBOARD_PRIMARY_ROUTES,
  ...DASHBOARD_SUPPORT_ROUTES,
].map((route) => route.href);

export const DASHBOARD_RETIRED_PREFIXES = DASHBOARD_RETIRED_ROUTES.map((route) => route.href);

function pathMatchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function isDashboardPrimaryPath(pathname: string): boolean {
  return DASHBOARD_PRIMARY_ROUTES.some((route) => pathMatchesPrefix(pathname, route.href));
}

export function isDashboardProtectedPath(pathname: string): boolean {
  return DASHBOARD_PROTECTED_PREFIXES.some((prefix) => pathMatchesPrefix(pathname, prefix));
}

export function isDashboardRetiredPath(pathname: string): boolean {
  return DASHBOARD_RETIRED_PREFIXES.some((prefix) => pathMatchesPrefix(pathname, prefix));
}
