import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DASHBOARD_PRIMARY_ROUTES } from "@/lib/dashboard-route-contract";

import { DashboardShell } from "./dashboard-shell";

const navState = vi.hoisted(() => ({
  pathname: "/home",
  planTemplate: {
    "actions.protected.monthly_quota": 10_000,
    "pilot.replay_stub": true,
    "pilot.goldens_basic": true,
    "pro.ci_gate_nonblocking": true,
  } as Record<string, unknown>,
  planCode: "pro" as string | undefined,
  billingDataAvailable: true,
  billingLoading: false,
  billingUsageDataAvailable: true,
  billingUsageLoading: false,
  protectedActionsUsage: {
    used: 250,
    limit: 10_000,
    unlimited: false,
    overage: null,
    state: "ok",
    resets_at: null,
  } as {
    used: number;
    limit: number | null;
    unlimited: boolean;
    overage: number | null;
    state: string;
    resets_at: string | null;
  },
  issueCount: 0,
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
    priority,
    ...props
  }: {
    alt: string;
    src: string;
    priority?: boolean;
    [key: string]: unknown;
  }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} data-priority={priority ? "true" : undefined} {...props} />
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
    if (key === "billing:usage") {
      return {
        data: navState.billingUsageDataAvailable
          ? { protected_actions: navState.protectedActionsUsage }
          : undefined,
        isLoading: navState.billingUsageLoading,
      };
    }
    if (key === "shell-issues-count") {
      return { data: { items: Array.from({ length: navState.issueCount }, (_, index) => ({ id: `issue_${index}` })) } };
    }
    return { data: undefined };
  }),
  useQueryClient: () => queryClientState,
}));

vi.mock("@/lib/api", () => ({
  getBillingMe: vi.fn(),
  getBillingUsage: vi.fn(),
  listIssues: vi.fn(),
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
      "actions.protected.monthly_quota": 10_000,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
      "pro.ci_gate_nonblocking": true,
    };
    navState.planCode = "pro";
    navState.billingDataAvailable = true;
    navState.billingLoading = false;
    navState.billingUsageDataAvailable = true;
    navState.billingUsageLoading = false;
    navState.protectedActionsUsage = {
      used: 250,
      limit: 10_000,
      unlimited: false,
      overage: null,
      state: "ok",
      resets_at: null,
    };
    navState.issueCount = 0;
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

    expect(primaryNavLabels()).toEqual(DASHBOARD_PRIMARY_ROUTES.map((route) => route.label));
    expect(screen.queryByText("Provider Drift")).toBeNull();
    expect(navItem("home").getAttribute("href")).toBe("/home");
  });

  it("marks the shell with the new dashboard visual system", () => {
    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(container.querySelector(".app-shell")?.getAttribute("data-dashboard-system")).toBe("control-v1");
  });

  it("keeps incident counts out of the minimal primary nav", () => {
    navState.issueCount = 3;

    render(<DashboardShell>content</DashboardShell>);

    expect(within(navItem("home") as HTMLElement).queryByText("3")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Primary" }).querySelector('[data-nav-id="issues"]')).toBeNull();
  });

  it("keeps Settings child navigation out of the sidebar", () => {
    const { rerender } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByRole("group", { name: "Settings sections" })).not.toBeInTheDocument();

    navState.pathname = "/settings/workspace";
    rerender(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByRole("group", { name: "Settings sections" })).not.toBeInTheDocument();
  });

  it("renders the dashboard logo image without the old text lockup", () => {
    render(<DashboardShell>content</DashboardShell>);

    const logo = screen.getByRole("img", { name: "Zroky" });
    expect(logo.getAttribute("src")).toBe("/zroky-brand.png");
    expect(logo.classList.contains("sidebar-logo-image")).toBe(true);
    expect(screen.queryByText("ZROKY")).not.toBeInTheDocument();
  });

  it("removes engineering routes from the primary action-control IA", () => {
    render(<DashboardShell>content</DashboardShell>);

    const labels = primaryNavLabels();
    expect(labels).not.toContain("Contracts");
    expect(labels).not.toContain("CI");
  });

  it("renders the action-accountability routes instead of deprecated analytics surfaces", () => {
    render(<DashboardShell>content</DashboardShell>);

    const labels = primaryNavLabels();
    expect(labels).toEqual(["Home", "Approvals", "Actions", "Agents", "Outcomes", "Evidence", "Policies", "Connectors", "Settings"]);
    expect(labels).toContain("Actions");
    expect(labels).toContain("Agents");
    expect(labels).toContain("Approvals");
    expect(labels).toContain("Outcomes");
    expect(labels).toContain("Evidence");
    expect(labels).toContain("Connectors");
    expect(labels).toContain("Policies");
    expect(labels).not.toContain("Incidents");
    expect(labels).not.toContain("Replay");
    expect(labels).not.toContain("Contracts");
    expect(labels).not.toContain("CI");
    expect(labels).not.toContain("Traces");
    expect(labels).not.toContain("Integrations");
    expect(labels).not.toContain("Cost");
    expect(labels).not.toContain("Flight Recorder");
    expect(labels).not.toContain("Trace Graphs");
    expect(labels).not.toContain("Alerts");

    expect(navItem("actions").getAttribute("href")).toBe("/actions");
    expect(navItem("connectors").getAttribute("href")).toBe("/integrations");
    expect(navItem("evidence").getAttribute("href")).toBe("/evidence");
  });

  it("groups the sidebar around the control loop", () => {
    render(<DashboardShell>content</DashboardShell>);

    const primary = screen.getByRole("navigation", { name: "Primary" });
    const sections = within(primary).getAllByText(/Control|Proof|Configure|Workspace/).map((node) => node.textContent);
    expect(sections).toEqual(["Control", "Proof", "Configure", "Workspace"]);
    expect(primary.querySelector('[data-nav-section="control"]')).toBeInTheDocument();
    expect(primary.querySelector('[data-nav-section="proof"]')).toBeInTheDocument();
    expect(primary.querySelector('[data-nav-section="configure"]')).toBeInTheDocument();
  });

  it("does not show fake workspace or account data while identity APIs are unavailable", () => {
    navState.projectData = undefined;
    navState.myProjects = [];
    storeState.selectedProject = null;
    navState.meData = undefined;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getAllByText("Project unavailable").length).toBeGreaterThan(0);
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

    fireEvent.click(screen.getByRole("button", { name: "Open project menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Beta Lab/ }));

    expect(storeState.setSelectedProject).toHaveBeenCalledWith("proj_2");
    expect(routerState.push).toHaveBeenCalledWith("/projects/proj_2");
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

  it("does not surface hidden gated modules as locked primary nav noise", () => {
    navState.planTemplate = {};
    navState.planCode = "free";

    render(<DashboardShell>content</DashboardShell>);

    const primaryNav = screen.getByRole("navigation", { name: "Primary" });
    expect(primaryNav.querySelector('[data-nav-id="replay"]')).toBeNull();
    expect(primaryNav.textContent).not.toContain("locked");
  });

  it("uses the actual billing plan code for the sidebar plan badge", () => {
    navState.planCode = "enterprise";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Enterprise Plan")).toBeInTheDocument();
    expect(screen.queryByText("Pro Plan")).not.toBeInTheDocument();
  });

  it("renders protected-action usage from the active subscription meter", () => {
    navState.planCode = "free";
    navState.planTemplate = {
      ...navState.planTemplate,
      "actions.protected.monthly_quota": 500,
    };
    navState.protectedActionsUsage = {
      used: 7,
      limit: 500,
      unlimited: false,
      overage: null,
      state: "ok",
      resets_at: null,
    };

    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Free Plan")).toBeInTheDocument();
    expect(screen.getByText("Protected actions")).toBeInTheDocument();
    expect(screen.getByText("7 / 500")).toBeInTheDocument();
    expect(screen.getByText("used this month")).toBeInTheDocument();
    expect(container.querySelector(".plan-usage-track")).toBeInTheDocument();
  });

  it("surfaces near-limit and exhausted protected-action quotas", () => {
    navState.protectedActionsUsage = {
      used: 8_000,
      limit: 10_000,
      unlimited: false,
      overage: null,
      state: "near_limit",
      resets_at: null,
    };

    const { container, rerender } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Near monthly limit")).toBeInTheDocument();
    expect(container.querySelector(".plan-card")?.classList.contains("is-warning")).toBe(true);

    navState.protectedActionsUsage = {
      ...navState.protectedActionsUsage,
      used: 10_000,
      state: "blocked",
    };
    rerender(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Limit reached")).toBeInTheDocument();
    expect(container.querySelector(".plan-card")?.classList.contains("is-critical")).toBe(true);
  });

  it("keeps the subscription quota visible while usage is still syncing", () => {
    navState.planCode = "free";
    navState.planTemplate = {
      ...navState.planTemplate,
      "actions.protected.monthly_quota": 500,
    };
    navState.billingUsageLoading = true;
    navState.billingUsageDataAvailable = false;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Free Plan")).toBeInTheDocument();
    expect(screen.getByText("0 / 500")).toBeInTheDocument();
    expect(screen.getByText("syncing usage")).toBeInTheDocument();
  });

  it("renders unlimited protected-action quota without exposing backend sentinel values or a meter", () => {
    navState.planCode = "enterprise";
    navState.planTemplate = {
      ...navState.planTemplate,
      "actions.protected.monthly_quota": -1,
    };
    navState.protectedActionsUsage = {
      used: 1200,
      limit: null,
      unlimited: true,
      overage: null,
      state: "ok",
      resets_at: null,
    };
    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Unlimited")).toBeInTheDocument();
    expect(screen.getByText("protected actions")).toBeInTheDocument();
    expect(screen.queryByText("-1")).not.toBeInTheDocument();
    expect(container.querySelector(".plan-usage-track")).toBeNull();
  });

  it("does not show Team Plan when billing data is unavailable", () => {
    navState.billingDataAvailable = false;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByText("Plan unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Team Plan")).not.toBeInTheDocument();
  });

  it("keeps Replay available as a deep route without promoting it to primary nav", () => {
    navState.planTemplate = {};
    navState.planCode = "pro";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByRole("navigation", { name: "Primary" }).querySelector('[data-nav-id="replay"]')).toBeNull();
  });

  it("opens a profile menu from the topbar account control instead of logging out immediately", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: /Open profile menu/ }));

    expect(authState.clearAccessToken).not.toHaveBeenCalled();
    expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Profile & security/ }).getAttribute("href")).toBe("/account");
  });

  it("logs out only from the explicit account menu action", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: /Open profile menu/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));

    expect(authState.clearAccessToken).toHaveBeenCalledTimes(1);
    expect(routerState.replace).toHaveBeenCalledWith("/login?logged_out=1");
    expect(routerState.refresh).toHaveBeenCalledTimes(1);
  });

  it("opens real workspace and route menus from shell controls", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open project menu" }));

    const projectMenu = screen.getByRole("menu", { name: "Project menu" });
    expect(projectMenu).toBeInTheDocument();
    expect(projectMenu.closest(".sidebar")).toBeNull();
    expect(projectMenu.classList.contains("shell-popover-portal")).toBe(true);
    expect((projectMenu as HTMLElement).style.position).toBe("fixed");
    expect((projectMenu as HTMLElement).style.width).toBe("312px");
    expect(screen.getByRole("menuitem", { name: /Manage projects/ }).getAttribute("href")).toBe("/projects");
    expect(screen.getByRole("menuitem", { name: /Team access/ }).getAttribute("href")).toBe("/settings/team");
    expect(screen.queryByText("Project switcher")).not.toBeInTheDocument();
    expect(screen.queryByText(/projects used/)).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /New project/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Upgrade to add more/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Project settings/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Find project" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open dashboard navigation menu" }));

    expect(screen.getByRole("menu", { name: "Dashboard navigation" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Home/ }).getAttribute("href")).toBe("/home");
    expect(screen.getByRole("menuitem", { name: /Agents/ }).getAttribute("href")).toBe("/agents");
    expect(screen.getByRole("menuitem", { name: /Approvals/ }).getAttribute("href")).toBe("/approvals");
    expect(screen.getByRole("menuitem", { name: /Outcomes/ }).getAttribute("href")).toBe("/outcomes");
    const routeMenu = screen.getByRole("menu", { name: "Dashboard navigation" });
    expect(routeMenu.querySelector('[href="/evidence"]')).not.toBeNull();
    expect(routeMenu.querySelector('[href="/integrations"]')).not.toBeNull();
    expect(screen.queryByRole("menuitem", { name: /Contracts/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^CI$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Traces/ })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Policies/ }).getAttribute("href")).toBe("/policies");
    expect(screen.queryByRole("menuitem", { name: /Integrations/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Cost/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Alerts/ })).not.toBeInTheDocument();
  });

  it("filters large project lists without crowding smaller workspaces", () => {
    navState.myProjects = Array.from({ length: 6 }, (_, index) => ({
      membership_id: `mem_${index + 1}`,
      project_id: `proj_${index + 1}`,
      project_name: index === 5 ? "Payments Production" : `Workspace ${index + 1}`,
      role: index === 0 ? "owner" : "member",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }));

    render(<DashboardShell>content</DashboardShell>);
    fireEvent.click(screen.getByRole("button", { name: "Open project menu" }));

    const search = screen.getByRole("searchbox", { name: "Find project" });
    fireEvent.change(search, { target: { value: "payments" } });

    expect(screen.getByRole("menuitem", { name: "Payments Production" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Workspace 2" })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "missing" } });
    expect(screen.getByRole("menuitem", { name: /No matching projects/ })).toBeInTheDocument();
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

  it("hides the dashboard time window on Settings routes", () => {
    navState.pathname = "/settings/keys";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByRole("button", { name: "Choose dashboard time window" })).not.toBeInTheDocument();
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
    const accountButton = screen.getByRole("button", { name: /Open profile menu/ });
    expect(topbar?.contains(accountButton)).toBe(true);

    const planLink = screen.getByLabelText("Open billing and usage");
    const workspaceButton = screen.getByRole("button", { name: "Open project menu" });
    expect(planLink.getAttribute("href")).toBe("/settings/billing");
    expect(workspaceButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(workspaceButton);

    expect(workspaceButton.getAttribute("aria-expanded")).toBe("true");
    expect(workspaceButton.classList.contains("org-widget-active")).toBe(true);
    expect(planLink.compareDocumentPosition(workspaceButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
