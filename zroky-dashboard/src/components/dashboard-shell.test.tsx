import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  myProjectsError: false,
  refetchProjects: vi.fn(),
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
    return { data: undefined };
  }),
  useQueryClient: () => queryClientState,
}));

vi.mock("@/lib/api", () => ({
  getBillingMe: vi.fn(),
  getBillingUsage: vi.fn(),
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
    isError: navState.myProjectsError,
    refetch: navState.refetchProjects,
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
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
        addEventListener: vi.fn(),
        matches: false,
        removeEventListener: vi.fn(),
      })),
      writable: true,
    });
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
    navState.myProjectsError = false;
    navState.refetchProjects.mockReset();
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
      "Home",
      "Operations",
      "Workflows",
      "Connectors",
      "Evidence",
      "Settings",
    ]);
    expect(screen.queryByText("Provider Drift")).toBeNull();
    expect(navItem("home").getAttribute("href")).toBe("/home");
  });

  it("marks the shell with the new dashboard visual system", () => {
    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(container.querySelector(".app-shell")?.getAttribute("data-dashboard-system")).toBe("control-v1");
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
    expect(labels).toEqual([
      "Home",
      "Operations",
      "Workflows",
      "Connectors",
      "Evidence",
      "Settings",
    ]);
    expect(labels).toContain("Operations");
    expect(labels).toContain("Workflows");
    expect(labels).toContain("Connectors");
    expect(labels).toContain("Evidence");
    expect(labels).not.toContain("Actions");
    expect(labels).not.toContain("Agents");
    expect(labels).not.toContain("Approvals");
    expect(labels).not.toContain("Outcomes");
    expect(labels).not.toContain("Replay");
    expect(labels).not.toContain("Contracts");
    expect(labels).not.toContain("CI");
    expect(labels).not.toContain("Traces");
    expect(labels).not.toContain("Integrations");
    expect(labels).not.toContain("Cost");
    expect(labels).not.toContain("Flight Recorder");
    expect(labels).not.toContain("Trace Graphs");
    expect(labels).not.toContain("Alerts");

    expect(navItem("operations").getAttribute("href")).toBe("/operations");
    expect(navItem("workflows").getAttribute("href")).toBe("/workflows");
    expect(navItem("connectors").getAttribute("href")).toBe("/integrations");
    expect(navItem("evidence").getAttribute("href")).toBe("/evidence");
    expect(navItem("settings").getAttribute("href")).toBe("/settings");
  });

  it("uses one primary sidebar group from the route contract", () => {
    render(<DashboardShell>content</DashboardShell>);

    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primary).queryByText(/Core|Governance|Workspace/)).not.toBeInTheDocument();
    expect(primary.querySelectorAll(".nav-link")).toHaveLength(6);
    expect(primary.querySelector('[data-nav-id="incidents"]')).toBeNull();
    expect(primary.querySelector('[data-nav-id="policies"]')).toBeNull();
    expect(primary.querySelector('[data-nav-id="trust-advisor"]')).toBeNull();
    expect(primary.querySelector('[data-nav-id="reports"]')).toBeNull();
    expect(primary.querySelector('[data-nav-section="configure"]')).not.toBeInTheDocument();
  });

  it("does not show fake workspace or account data while identity APIs are unavailable", () => {
    navState.projectData = undefined;
    navState.myProjects = [];
    storeState.selectedProject = null;
    navState.meData = undefined;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getAllByText("Account").length).toBeGreaterThan(0);
    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
    expect(screen.queryByText("sanket@acme.com")).not.toBeInTheDocument();
    expect(screen.queryByText("Sanket K.")).not.toBeInTheDocument();
  });

  it("offers recovery when project loading fails", () => {
    navState.myProjects = [];
    navState.myProjectsError = true;
    storeState.selectedProject = null;

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByRole("heading", { name: "Workspace unavailable" })).toBeInTheDocument();
    expect(screen.queryByText("Preparing workspace")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(navState.refetchProjects).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Sign in again" }).getAttribute("href")).toBe("/login");
  });

  it("keeps project switching in the context gate instead of the global shell", () => {
    storeState.selectedProject = null;
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

    fireEvent.click(screen.getByRole("button", { name: /Beta Lab/ }));

    expect(storeState.setSelectedProject).toHaveBeenCalledWith("proj_2");
    expect(queryClientState.invalidateQueries).toHaveBeenCalledWith({
      predicate: expect.any(Function),
    });
  });

  it("switches workspaces from the sidebar and follows a project detail route", () => {
    navState.pathname = "/projects/proj_1";
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

    fireEvent.click(screen.getByRole("button", { name: "Switch workspace" }));
    expect(screen.getByRole("menu", { name: "Workspaces" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Manage projects/ }).getAttribute("href")).toBe("/projects");
    fireEvent.click(screen.getByRole("menuitem", { name: /Beta Lab/ }));

    expect(storeState.setSelectedProject).toHaveBeenCalledWith("proj_2");
    expect(routerState.replace).toHaveBeenCalledWith("/projects/proj_2");
    expect(screen.queryByRole("menu", { name: "Workspaces" })).not.toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: "Select a project to load this dashboard" })).toBeInTheDocument();
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

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
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

  it("does not render duplicate sidebar footer status, environment, account, or billing blocks", () => {
    navState.planCode = "enterprise";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByText("All systems operational")).not.toBeInTheDocument();
    expect(screen.queryByText("Updated just now")).not.toBeInTheDocument();
    expect(screen.queryByText("Environment")).not.toBeInTheDocument();
    expect(screen.queryByText("Owner access")).not.toBeInTheDocument();
    expect(screen.queryByText("Enterprise Plan")).not.toBeInTheDocument();
    expect(screen.queryByText("Control surface")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Open billing and usage")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Open account for/)).not.toBeInTheDocument();
  });

  it("keeps Replay available as a deep route without promoting it to primary nav", () => {
    navState.planTemplate = {};
    navState.planCode = "pro";

    render(<DashboardShell>content</DashboardShell>);

    expect(screen.getByRole("navigation", { name: "Primary" }).querySelector('[data-nav-id="replay"]')).toBeNull();
  });

  it("opens a profile menu from the topbar account control instead of logging out immediately", () => {
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open account menu" }));

    expect(authState.clearAccessToken).not.toHaveBeenCalled();
    expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Profile & security/ }).getAttribute("href")).toBe("/account");
  });

  it("waits for session cleanup before leaving the dashboard", async () => {
    let finishLogout: (() => void) | undefined;
    authState.clearAccessToken.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finishLogout = resolve;
      }),
    );
    render(<DashboardShell>content</DashboardShell>);

    fireEvent.click(screen.getByRole("button", { name: "Open account menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));

    expect(authState.clearAccessToken).toHaveBeenCalledTimes(1);
    expect(routerState.replace).not.toHaveBeenCalled();

    finishLogout?.();

    await waitFor(() => {
      expect(routerState.replace).toHaveBeenCalledWith("/login?logged_out=1");
    });
    expect(routerState.refresh).not.toHaveBeenCalled();
  });

  it("keeps search in the global top utility bar without page route menus", () => {
    render(<DashboardShell>content</DashboardShell>);

    const searchButton = screen.getByRole("button", { name: "Search evidence, incidents, workflows" });
    expect(searchButton.closest(".topbar")).toBeInTheDocument();
    expect(searchButton.textContent).toContain("Search evidence, incidents, workflows…");
    expect(screen.queryByRole("button", { name: "Open dashboard navigation menu" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Choose dashboard time window" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open environment status" })).not.toBeInTheDocument();
  });

  it("keeps the desktop sidebar fixed even if persisted state says collapsed", () => {
    storeState.sidebarOpen = false;
    const { container, rerender } = render(<DashboardShell>content</DashboardShell>);

    expect(container.querySelector(".app-shell")?.classList.contains("sidebar-collapsed")).toBe(false);
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(false);
    expect(screen.queryByRole("button", { name: "Open navigation" })).not.toBeInTheDocument();
    rerender(<DashboardShell>content</DashboardShell>);
    expect(container.querySelector(".app-shell")?.classList.contains("sidebar-collapsed")).toBe(false);
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(false);
  });

  it("opens and closes the navigation drawer on compact screens", async () => {
    vi.mocked(window.matchMedia).mockImplementation(() => ({
      addEventListener: vi.fn(),
      matches: true,
      removeEventListener: vi.fn(),
    }) as unknown as MediaQueryList);

    const { container } = render(<DashboardShell>content</DashboardShell>);

    const openButton = await screen.findByRole("button", { name: "Open navigation" });
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(true);

    fireEvent.click(openButton);
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(false);

    fireEvent.click(screen.getAllByRole("button", { name: "Close navigation" })[0]);
    expect(container.querySelector(".sidebar")?.classList.contains("sidebar-hidden")).toBe(true);
  });

  it("keeps the profile and utility actions in the topbar while footer stays operational", () => {
    const { container } = render(<DashboardShell>content</DashboardShell>);

    expect(screen.queryByRole("button", { name: "Open page actions and filters" })).not.toBeInTheDocument();

    const topbar = container.querySelector(".topbar");
    const accountButton = screen.getByRole("button", { name: "Open account menu" });
    expect(topbar?.contains(accountButton)).toBe(true);
    expect(screen.queryByRole("button", { name: "Notifications" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Appearance" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Settings" })).toHaveLength(1);
    expect(topbar?.contains(screen.getByRole("link", { name: "Settings" }))).toBe(false);
    expect(screen.queryByText("All systems operational")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Open account for sanket@acme.com")).not.toBeInTheDocument();
  });
});
