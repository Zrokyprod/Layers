import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardShell } from "./dashboard-shell";

const navState = vi.hoisted(() => ({
  pathname: "/home",
  planTemplate: {
    "pilot.replay_stub": true,
    "pilot.goldens_basic": true,
    "pro.ci_gate_nonblocking": true,
  } as Record<string, unknown>,
  planCode: "pro" as string | undefined,
  billingDataAvailable: true,
  billingLoading: false,
  budgetDataAvailable: true,
  projectData: { project_id: "proj_1", name: "Acme Corp" } as { project_id: string; name: string } | undefined,
  projectLoading: false,
  myProjects: [
    {
      membership_id: "mem_1",
      project_id: "proj_1",
      project_name: "Acme Corp",
      role: "owner",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ] as Array<{
    membership_id: string;
    project_id: string;
    project_name: string;
    role: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
  }>,
  myProjectsLoading: false,
  meData: { email: "sanket@acme.com", display_name: "Sanket K." } as
    | { email: string | null; display_name: string | null }
    | undefined,
  meLoading: false,
}));

const routerState = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
  replace: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  clearAccessToken: vi.fn(),
}));

const queryClientState = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
}));

const storeState = vi.hoisted(() => ({
  sidebarOpen: true,
  selectedProject: "proj_1" as string | null,
  toggleSidebar: vi.fn(),
  setLastVisitedPage: vi.fn(),
  setSelectedProject: vi.fn(),
  setDateRange: vi.fn(),
  toggleRealTime: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({
    alt,
    src,
    ...props
  }: {
    alt: string;
    src: string;
    [key: string]: unknown;
  }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} {...props} />
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navState.pathname,
  useRouter: () => ({
    replace: routerState.replace,
    refresh: routerState.refresh,
    push: routerState.push,
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey.join(":");
    if (key === "billing:me") {
      return {
        data: navState.billingDataAvailable
          ? { plan_template: navState.planTemplate, plan_code: navState.planCode }
          : undefined,
        isLoading: navState.billingLoading,
      };
    }
    if (key === "shell-budget-status") {
      return {
        data: navState.budgetDataAvailable
          ? {
              spent_usd: 12.5,
              limit_usd: 100,
              percent_used: 12.5,
              days_remaining_in_period: 20,
              forecast_exhaust_in_days: null,
              status: "ok",
              forecast_risk_level: "low",
              forecast_recommendation: "Within budget.",
            }
          : undefined,
        isLoading: false,
      };
    }
    if (key === "shell-issues-count") return { data: { items: [] } };
    if (key === "shell-agents-count") return { data: [] };
    return { data: undefined };
  }),
  useQueryClient: () => queryClientState,
}));

vi.mock("@/lib/api", () => ({
  getBillingMe: vi.fn(),
  getBudgetStatus: vi.fn(),
  listIssues: vi.fn(),
  getReliabilityLeaderboard: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  clearAccessToken: authState.clearAccessToken,
}));

vi.mock("@/lib/hooks", () => ({
  useMe: () => ({
    data: navState.meData,
    isLoading: navState.meLoading,
  }),
  useProjectSettings: () => ({
    data: navState.projectData,
    isLoading: navState.projectLoading,
  }),
  useMyProjects: () => ({
    data: navState.myProjects,
    isLoading: navState.myProjectsLoading,
  }),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: () => ({
    sidebarOpen: storeState.sidebarOpen,
    toggleSidebar: storeState.toggleSidebar,
    setLastVisitedPage: storeState.setLastVisitedPage,
    selectedProject: storeState.selectedProject,
    setSelectedProject: storeState.setSelectedProject,
    dateRange: { from: null, to: null },
    setDateRange: storeState.setDateRange,
    realTimeEnabled: true,
    toggleRealTime: storeState.toggleRealTime,
  }),
}));

vi.mock("@/lib/keyboard-shortcuts", () => ({
  useKeyboardShortcuts: vi.fn(),
}));

vi.mock("./command-palette", () => ({
  CommandPalette: () => null,
}));

vi.mock("./shortcuts-help", () => ({
  ShortcutsHelp: () => null,
}));

function primaryNavLabels(): string[] {
  const nav = screen.getByRole("navigation", { name: "Primary" });
  return Array.from(nav.querySelectorAll("[data-nav-id] .nav-link-main span:last-child"))
    .map((node) => node.textContent ?? "");
}

function navItem(id: string): Element {
  const nav = screen.getByRole("navigation", { name: "Primary" });
  const item = nav.querySelector(`[data-nav-id="${id}"]`);
  if (!item) throw new Error(`Missing nav item ${id}`);
  return item;
}

describe("DashboardShell primary navigation", () => {
  beforeEach(() => {
    navState.pathname = "/home";
    navState.planTemplate = {
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
      "pro.ci_gate_nonblocking": true,
    };
    navState.planCode = "pro";
    navState.billingDataAvailable = true;
    navState.billingLoading = false;
    navState.budgetDataAvailable = true;
    navState.projectData = { project_id: "proj_1", name: "Acme Corp" };
    navState.projectLoading = false;
    navState.myProjects = [
      {
        membership_id: "mem_1",
        project_id: "proj_1",
        project_name: "Acme Corp",
        role: "owner",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    navState.myProjectsLoading = false;
    navState.meData = { email: "sanket@acme.com", display_name: "Sanket K." };
    navState.meLoading = false;
    storeState.sidebarOpen = true;
    storeState.selectedProject = "proj_1";
    routerState.push.mockClear();
    routerState.refresh.mockClear();
    routerState.replace.mockClear();
    authState.clearAccessToken.mockClear();
    queryClientState.invalidateQueries.mockClear();
    storeState.toggleSidebar.mockReset();
    storeState.toggleSidebar.mockImplementation(() => {
      storeState.sidebarOpen = !storeState.sidebarOpen;
    });
    storeState.setLastVisitedPage.mockClear();
    storeState.setSelectedProject.mockClear();
    storeState.setDateRange.mockClear();
    storeState.toggleRealTime.mockClear();
  });

  it("renders the primary nav in the required product order", () => {
    render(<DashboardShell>content</DashboardShell>);

    expect(primaryNavLabels()).toEqual([
      "Overview",
      "Incidents",
      "Replays",
      "Contracts",
      "CI",
      "Settings",
    ]);
    expect(screen.queryByText("Provider Drift")).toBeNull();
    expect(navItem("failure-inbox").getAttribute("href")).toBe("/home");
  });

  it("renders the dashboard logo image without the old text lockup", () => {
    render(<DashboardShell>content</DashboardShell>);

    const logo = screen.getByRole("img", { name: "Zroky" });
    expect(logo.getAttribute("src")).toBe("/zroky-sidebar-logo-transparent.png");
    expect(logo.classList.contains("sidebar-logo-image")).toBe(true);
    expect(screen.queryByText("ZROKY")).not.toBeInTheDocument();
  });

  it("renders CI Gates as a live primary route", () => {
    render(<DashboardShell>content</DashboardShell>);

    const ciGates = navItem("ci-gates");
    expect(ciGates.getAttribute("aria-disabled")).toBeNull();
    expect(ciGates.getAttribute("href")).toBe("/ci-gates");
    expect(within(ciGates as HTMLElement).queryByText("soon")).toBeNull();
  });

  it("renders the reliability control-plane routes instead of deprecated analytics surfaces", () => {
    render(<DashboardShell>content</DashboardShell>);

    const labels = primaryNavLabels();
    expect(labels).toContain("Contracts");
    expect(labels).toContain("CI");
    expect(labels).not.toContain("Agents");
    expect(labels).not.toContain("Traces");
    expect(labels).not.toContain("Policies");
    expect(labels).not.toContain("Approvals");
    expect(labels).not.toContain("Integrations");
    expect(labels).not.toContain("Cost");
    expect(labels).not.toContain("Flight Recorder");
    expect(labels).not.toContain("Trace Graphs");
    expect(labels).not.toContain("Alerts");

    const contracts = navItem("goldens");
    expect(contracts.getAttribute("aria-disabled")).toBeNull();
    expect(contracts.getAttribute("href")).toBe("/contracts");
  });

  it("does not show fake workspace or account data while identity APIs are unavailable", () => {
    navState.projectData = undefined;
    navState.myProjects = [];
    storeState.selectedProject = null;
    navState.meData = undefined;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getAllByText("Workspace unavailable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Account").length).toBeGreaterThan(0);
    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
    expect(screen.queryByText("sanket@acme.com")).not.toBeInTheDocument();
    expect(screen.queryByText("Sanket K.")).not.toBeInTheDocument();
  });

  it("renders project memberships and switches the selected project", () => {
    navState.myProjects = [
      {
        membership_id: "mem_1",
        project_id: "proj_1",
        project_name: "Acme Corp",
        role: "owner",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        membership_id: "mem_2",
        project_id: "proj_2",
        project_name: "Beta Lab",
        role: "admin",
        is_active: true,
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      },
    ];

    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open workspace menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Beta Lab/ }));

    expect(storeState.setSelectedProject).toHaveBeenCalledWith("proj_2");
    expect(queryClientState.invalidateQueries).toHaveBeenCalledWith({
      predicate: expect.any(Function),
    });
  });

  it("shows a project selection state for multi-project users without a selected project", () => {
    storeState.selectedProject = null;
    navState.projectData = undefined;
    navState.myProjects = [
      {
        membership_id: "mem_1",
        project_id: "proj_1",
        project_name: "Acme Corp",
        role: "owner",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        membership_id: "mem_2",
        project_id: "proj_2",
        project_name: "Beta Lab",
        role: "admin",
        is_active: true,
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      },
    ];

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Select project")).toBeInTheDocument();
    expect(storeState.setSelectedProject).not.toHaveBeenCalled();
  });

  it("auto-selects the only active project", async () => {
    storeState.selectedProject = null;

    render(<DashboardShell>content</DashboardShell>);

    await waitFor(() => {
      expect(storeState.setSelectedProject).toHaveBeenCalledWith("proj_1");
    });
  });

  it("does not overwrite an explicit selected project from project settings", () => {
    storeState.selectedProject = "proj_2";
    navState.projectData = { project_id: "proj_1", name: "Acme Corp" };
    navState.myProjects = [
      {
        membership_id: "mem_1",
        project_id: "proj_1",
        project_name: "Acme Corp",
        role: "owner",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        membership_id: "mem_2",
        project_id: "proj_2",
        project_name: "Beta Lab",
        role: "admin",
        is_active: true,
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      },
    ];

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Beta Lab")).toBeInTheDocument();
    expect(storeState.setSelectedProject).not.toHaveBeenCalled();
  });

  it("disables gated nav entries when the plan template lacks entitlement", () => {
    navState.planTemplate = {};
    navState.planCode = "free";

    render(<DashboardShell>content</DashboardShell>);

    expect(navItem("replay").getAttribute("aria-disabled")).toBe("true");
    expect(navItem("goldens").getAttribute("aria-disabled")).toBe("true");
    expect(within(navItem("replay") as HTMLElement).getByText("locked")).toBeInTheDocument();
    expect(within(navItem("goldens") as HTMLElement).getByText("locked")).toBeInTheDocument();
  });

  it("uses the actual billing plan code for the sidebar plan badge", () => {
    navState.planCode = "enterprise";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Enterprise Plan")).toBeInTheDocument();
    expect(screen.queryByText("Pro Plan")).not.toBeInTheDocument();
  });

  it("does not show Pro Plan when billing data is unavailable", () => {
    navState.billingDataAvailable = false;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Plan unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Pro Plan")).not.toBeInTheDocument();
  });

  it("does not lock Contracts for paid plan-code fallback", () => {
    navState.planTemplate = {};
    navState.planCode = "pro";

    render(<DashboardShell>content</DashboardShell>);

    expect(navItem("goldens").getAttribute("aria-disabled")).toBeNull();
    expect(navItem("goldens").getAttribute("href")).toBe("/contracts");
    expect(within(navItem("goldens") as HTMLElement).queryByText("locked")).toBeNull();
  });

  it("opens an account menu from the topbar profile control instead of logging out immediately", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open account menu" }));

    expect(authState.clearAccessToken).not.toHaveBeenCalled();
    expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Account" }).getAttribute("href")).toBe("/account");
  });

  it("logs out only from the explicit account menu action", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open account menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));

    expect(authState.clearAccessToken).toHaveBeenCalledTimes(1);
    expect(routerState.replace).toHaveBeenCalledWith("/login?logged_out=1");
    expect(routerState.refresh).toHaveBeenCalledTimes(1);
  });

  it("opens real workspace and route menus from shell controls", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open workspace menu" }));

    expect(screen.getByRole("menu", { name: "Workspace menu" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Project settings/ }).getAttribute("href")).toBe("/settings");

    fireEvent.click(screen.getByRole("button", { name: "Open dashboard navigation menu" }));

    expect(screen.getByRole("menu", { name: "Dashboard navigation" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Overview/ }).getAttribute("href")).toBe("/home");
    expect(screen.getByRole("menuitem", { name: /Contracts/ }).getAttribute("href")).toBe("/contracts");
    expect(screen.queryByRole("menuitem", { name: /Traces/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Policies/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Integrations/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Cost/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Alerts/ })).not.toBeInTheDocument();
  });

  it("toggles the desktop sidebar from the topbar control", () => {
    const { container, rerender } = render(<DashboardShell>content</DashboardShell>);

    expect(container.querySelector(".app-shell")?.classList.contains("sidebar-collapsed")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    expect(storeState.toggleSidebar).toHaveBeenCalledTimes(1);
    rerender(<DashboardShell>content</DashboardShell>);
    expect(container.querySelector(".app-shell")?.classList.contains("sidebar-collapsed")).toBe(true);
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(true);
  });

  it("applies a dashboard date preset and invalidates dashboard queries", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Choose dashboard time window" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Last 30 days/ }));

    expect(storeState.setDateRange).toHaveBeenCalledTimes(1);
    expect(storeState.setDateRange.mock.calls[0]?.[0]).toMatchObject({
      from: expect.any(Date),
      to: expect.any(Date),
    });
    expect(queryClientState.invalidateQueries).toHaveBeenCalledTimes(1);
  });

  it("opens environment status and toggles live refresh", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open environment status" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Live dashboard refresh/ }));

    expect(storeState.toggleRealTime).toHaveBeenCalledTimes(1);
  });

  it("keeps the profile in the topbar and the plan above workspace in the sidebar footer", () => {
    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByRole("button", { name: "Open page actions and filters" })).not.toBeInTheDocument();

    const topbar = container.querySelector(".topbar");
    const accountButton = screen.getByRole("button", { name: "Open account menu" });
    expect(topbar?.contains(accountButton)).toBe(true);

    const planLink = screen.getByLabelText("Open billing and usage");
    const workspaceButton = screen.getByRole("button", { name: "Open workspace menu" });
    expect(planLink.compareDocumentPosition(workspaceButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
