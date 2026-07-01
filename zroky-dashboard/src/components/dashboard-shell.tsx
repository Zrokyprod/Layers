"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Activity,
  Bot,
  Calendar,
  Check,
  ChevronDown,
  Clock3,
  CreditCard,
  FileJson,
  FolderOpen,
  Gauge,
  Inbox,
  KeyRound,
  LockKeyhole,
  LogOut,
  Menu,
  Plug,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { getBillingMe, getBudgetStatus, listIssues } from "@/lib/api";
import { isDashboardPrimaryPath } from "@/lib/dashboard-route-contract";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useMe, useMyProjects, useProjectSettings } from "@/lib/hooks";
import { formatPlanLabel, hasFeatureAccess } from "./feature-gate";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";

type NavItem = {
  id: string;
  href?: string;
  label: string;
  subtitle: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  badgeKey?: "issues";
  requiredEntitlement?: string;
  placeholder?: boolean;
  visibleInNav?: boolean;
};

function visibleInPrimaryNav(href: string): boolean {
  return isDashboardPrimaryPath(href);
}

const NAV_ITEMS: NavItem[] = [
  {
    id: "home",
    href: "/home",
    label: "Home",
    subtitle: "Mission control for protected agents, held actions, verified outcomes, and evidence gaps.",
    Icon: Inbox,
    visibleInNav: visibleInPrimaryNav("/home"),
  },
  {
    id: "actions",
    href: "/actions",
    label: "Actions",
    subtitle: "Protected action lifecycle, quotas, receipts, verification, and bypass risk.",
    Icon: Activity,
    visibleInNav: visibleInPrimaryNav("/actions"),
  },
  {
    id: "agents",
    href: "/agents",
    label: "Agents",
    subtitle: "Protected agents, mandates, high-risk action coverage, and outcome proof readiness.",
    Icon: Bot,
    visibleInNav: visibleInPrimaryNav("/agents"),
  },
  {
    id: "approvals",
    href: "/approvals",
    label: "Approvals",
    subtitle: "Held risky actions, runtime policy decisions, approval trail, and Evidence Pack access.",
    Icon: LockKeyhole,
    visibleInNav: visibleInPrimaryNav("/approvals"),
  },
  {
    id: "outcomes",
    href: "/outcomes",
    label: "Outcomes",
    subtitle: "System-of-record verification for high-stakes agent actions.",
    Icon: ShieldCheck,
    visibleInNav: visibleInPrimaryNav("/outcomes"),
  },
  {
    id: "evidence",
    href: "/evidence",
    label: "Evidence",
    subtitle: "Decision evidence packs, outcome proof, audit hashes, and customer export readiness.",
    Icon: FileJson,
    visibleInNav: visibleInPrimaryNav("/evidence"),
  },
  {
    id: "connectors",
    href: "/integrations",
    label: "Connectors",
    subtitle: "System-of-record connectors, preflight status, and pilot handoff readiness.",
    Icon: Plug,
    visibleInNav: visibleInPrimaryNav("/integrations"),
  },
  {
    id: "policies",
    href: "/policies",
    label: "Policies",
    subtitle: "Agent mandates, runtime limits, approval-required actions, and kill switch state.",
    Icon: ShieldAlert,
    visibleInNav: visibleInPrimaryNav("/policies"),
  },
  {
    id: "settings",
    href: "/settings/keys",
    label: "Settings",
    subtitle: "API keys, members, billing, and workspace controls.",
    Icon: Settings2,
    visibleInNav: visibleInPrimaryNav("/settings"),
  },
];

const VISIBLE_NAV = NAV_ITEMS.filter((n) => n.visibleInNav);

const NAV_SECTIONS: ReadonlyArray<{ id: string; label: string; itemIds: string[] }> = [
  { id: "control", label: "Control", itemIds: ["home", "approvals", "actions", "agents"] },
  { id: "proof", label: "Proof", itemIds: ["outcomes", "evidence"] },
  { id: "configure", label: "Configure", itemIds: ["policies", "connectors"] },
];

const SETTINGS_CHILD_LINKS = [
  { href: "/settings/keys", label: "API Keys", Icon: KeyRound },
  { href: "/settings/team", label: "Members", Icon: UserRound },
  { href: "/settings/billing", label: "Plan & Billing", Icon: CreditCard },
  { href: "/settings/workspace", label: "Workspace", Icon: FolderOpen },
];

const DATE_PRESETS = [
  { id: "24h", label: "Last 24 hours", days: 1, helper: "Action exceptions and cost from the last day." },
  { id: "7d", label: "Last 7 days", days: 7, helper: "Default production review window." },
  { id: "14d", label: "Last 14 days", days: 14, helper: "Useful for release-cycle checks." },
  { id: "30d", label: "Last 30 days", days: 30, helper: "Monthly trend and budget review." },
] as const;

type DatePresetId = (typeof DATE_PRESETS)[number]["id"];
type ShellMenu = "workspace" | "route" | "date" | "env" | "account";

const DASHBOARD_ROUTES = [
  ...NAV_ITEMS,
  {
    id: "projects",
    href: "/projects",
    label: "Projects",
    subtitle: "Project list, subscription limit, active context, and deletion controls.",
    Icon: FolderOpen,
  },
  {
    id: "account",
    href: "/account",
    label: "Account",
    subtitle: "Personal identity, password, sessions, and account security.",
    Icon: UserRound,
  },
];

function getRouteMeta(pathname: string): NavItem | null {
  return (
    DASHBOARD_ROUTES.find((r) => {
      if (!r.href) return false;
      const prefix = routePrefixForHref(r.href);
      return pathname === prefix || pathname.startsWith(`${prefix}/`);
    }) ?? null
  );
}

function getTitle(pathname: string): string {
  return getRouteMeta(pathname)?.label ?? "Dashboard";
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: value >= 10_000 ? 1 : 0,
  }).format(value);
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value);
}

function formatDateShort(date: Date): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function safeDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function periodCopy(currentPeriodEnd: string | null | undefined, trialEnd: string | null | undefined): string {
  const trial = safeDate(trialEnd);
  const periodEnd = safeDate(currentPeriodEnd);
  const target = trial ?? periodEnd;
  if (!target) return "Billing period unavailable";

  const today = new Date();
  const msRemaining = target.getTime() - today.getTime();
  const daysRemaining = Math.ceil(msRemaining / 86_400_000);
  const prefix = trial ? "Trial ends" : "Renews";

  if (daysRemaining < 0) return `${prefix} ${formatDateShort(target)}`;
  if (daysRemaining === 0) return `${prefix} today`;
  if (daysRemaining === 1) return `${prefix} tomorrow`;
  return `${prefix} in ${daysRemaining} days`;
}

function numericEntitlement(planTemplate: Record<string, unknown> | undefined, key: string): number | null {
  const value = planTemplate?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function projectLimitCopy(projectCount: number, maxProjects: number | null): string {
  const projectLabel = projectCount === 1 ? "project" : "projects";
  if (maxProjects === -1) return `${projectCount} ${projectLabel} - unlimited`;
  if (maxProjects == null) return `${projectCount} ${projectLabel}`;
  return `${projectCount} / ${maxProjects} projects used`;
}

function dateRangeLabel(
  dateRange: { from: Date | null; to: Date | null },
  activePreset: DatePresetId,
): string {
  const preset = DATE_PRESETS.find((item) => item.id === activePreset);
  if (preset) return preset.label;
  if (dateRange.from && dateRange.to) {
    return `${formatDateShort(dateRange.from)} - ${formatDateShort(dateRange.to)}`;
  }
  return "Last 7 days";
}

function routePrefixForHref(href: string): string {
  if (href.startsWith("/settings")) return "/settings";
  if (href.startsWith("/projects")) return "/projects";
  return href;
}

function navClass(pathname: string, href: string): string {
  const prefix = routePrefixForHref(href);
  return pathname === prefix || pathname.startsWith(`${prefix}/`)
    ? "nav-link nav-link-active"
    : "nav-link";
}

function NavFeatureGate({
  item,
  pathname,
  badgeCount,
  planTemplate,
  planCode,
  entitlementLoading,
}: {
  item: NavItem;
  pathname: string;
  badgeCount: number;
  planTemplate: Record<string, unknown> | undefined;
  planCode: string | null | undefined;
  entitlementLoading: boolean;
}) {
  const Icon = item.Icon;
  const disabledByPlan =
    Boolean(item.requiredEntitlement) &&
    !entitlementLoading &&
    !hasFeatureAccess(planTemplate, planCode, item.requiredEntitlement);
  const disabled = item.placeholder || !item.href;
  const label = (
    <>
      <span className="nav-link-main">
        <Icon size={16} className="nav-link-icon" />
        <span>{item.label}</span>
      </span>
      {disabledByPlan ? (
        <span className="nav-link-soon" aria-label={`${item.label} requires a plan upgrade`}>
          <LockKeyhole size={10} aria-hidden="true" />
          locked
        </span>
      ) : item.placeholder ? (
        <span className="nav-link-soon">soon</span>
      ) : badgeCount > 0 ? (
        <span className={`nav-badge${item.badgeKey === "issues" ? " nav-badge-danger" : ""}`}>
          {badgeCount}
        </span>
      ) : null}
    </>
  );

  if (disabled) {
    return (
      <span
        className="nav-link nav-link-placeholder"
        role="link"
        aria-disabled="true"
        title={
          item.placeholder
            ? `${item.label} is not available in the primary MVP yet.`
            : `${item.label} requires ${item.requiredEntitlement}.`
        }
        data-nav-id={item.id}
      >
        {label}
      </span>
    );
  }

  const href = item.href;
  if (!href) return null;

  return (
    <Link
      href={href}
      className={`${navClass(pathname, href)}${disabledByPlan ? " nav-link-locked" : ""}`}
      data-nav-id={item.id}
      title={disabledByPlan ? `${item.label} requires ${item.requiredEntitlement}.` : undefined}
    >
      {label}
    </Link>
  );
}

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] ?? "")
      .join("")
      .toUpperCase() || "AC"
  );
}

function compactIdentifier(value: string | null | undefined, lead = 9, tail = 4): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}...${normalized.slice(-tail)}`;
}

function formatRoleLabel(role: string | null | undefined): string {
  const normalized = role?.trim();
  if (!normalized) return "Member";
  return normalized
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function ProjectContextGate({
  isLoading,
  noProjects,
  requiresSelection,
  projects,
  onSelectProject,
}: {
  isLoading: boolean;
  noProjects: boolean;
  requiresSelection: boolean;
  projects: { project_id: string; project_name: string; role: string }[];
  onSelectProject: (projectId: string) => void;
}) {
  const title = noProjects
    ? "No active project found"
    : requiresSelection
      ? "Select a project to load this dashboard"
      : "Loading project context";
  const body = noProjects
    ? "Ask an owner to add your account to a project before dashboard modules can load data."
    : requiresSelection
      ? "Dashboard data is scoped by project. Choose the project you want to inspect."
      : "Preparing project-scoped data before loading dashboard modules.";

  return (
    <section className="panel project-context-gate" aria-live="polite">
      <div className="panel-header">
        <div>
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
        {isLoading ? <span className="pill">Loading</span> : null}
      </div>

      {requiresSelection ? (
        <div className="project-context-actions">
          {projects.map((project) => (
            <button
              key={project.project_id}
              type="button"
              className="shell-menu-item"
              onClick={() => onSelectProject(project.project_id)}
            >
              <FolderOpen size={15} aria-hidden="true" />
              <span>
                <strong>{project.project_name}</strong>
                <small>
                  {project.project_id} - {project.role}
                </small>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const envLabel = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  const appShellRef = useRef<HTMLDivElement>(null);
  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const workspaceButtonRef = useRef<HTMLButtonElement>(null);
  const workspacePopoverRef = useRef<HTMLDivElement>(null);
  const routeMenuRef = useRef<HTMLDivElement>(null);
  const dateMenuRef = useRef<HTMLDivElement>(null);
  const envMenuRef = useRef<HTMLDivElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const [openMenu, setOpenMenu] = useState<ShellMenu | null>(null);
  const [workspacePopoverStyle, setWorkspacePopoverStyle] = useState<CSSProperties | null>(null);
  const [workspacePopoverTarget, setWorkspacePopoverTarget] = useState<HTMLElement | null>(null);
  const [activeDatePreset, setActiveDatePreset] = useState<DatePresetId>("7d");
  const [compactShell, setCompactShell] = useState(false);
  const [compactSidebarOpen, setCompactSidebarOpen] = useState(false);
  const accountMenuOpen = openMenu === "account";

  const {
    sidebarOpen,
    toggleSidebar,
    setLastVisitedPage,
    selectedProject,
    setSelectedProject,
    dateRange,
    setDateRange,
    realTimeEnabled,
    toggleRealTime,
  } = useDashboardStore();

  const projectQuery = useProjectSettings(selectedProject);
  const myProjectsQuery = useMyProjects();
  const meQuery = useMe();

  useKeyboardShortcuts();

  useEffect(() => {
    setLastVisitedPage(pathname);
  }, [pathname, setLastVisitedPage]);

  useEffect(() => {
    setWorkspacePopoverTarget(appShellRef.current ?? document.body);
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const mobileShell = window.matchMedia("(max-width: 1120px)");
    const syncMobileSidebar = () => {
      const isCompact = mobileShell.matches;
      setCompactShell(isCompact);
      if (isCompact) {
        setCompactSidebarOpen(false);
      }
    };

    syncMobileSidebar();
    const hydrationGuard = window.setTimeout(syncMobileSidebar, 0);
    mobileShell.addEventListener("change", syncMobileSidebar);
    return () => {
      window.clearTimeout(hydrationGuard);
      mobileShell.removeEventListener("change", syncMobileSidebar);
    };
  }, [pathname]);

  const myProjects = useMemo(() => myProjectsQuery.data ?? [], [myProjectsQuery.data]);
  const myProjectIdsKey = myProjects.map((project) => project.project_id).join("|");
  const selectedProjectMembership = selectedProject
    ? myProjects.find((project) => project.project_id === selectedProject) ?? null
    : null;
  const projectSelectionRequired = myProjects.length > 1 && !selectedProject;
  const noActiveProjects = Boolean(myProjectsQuery.data && myProjects.length === 0);
  const projectContextLoading = myProjectsQuery.isLoading || (myProjects.length === 1 && !selectedProject);
  const projectContextReady = Boolean(selectedProject)
    && !projectSelectionRequired
    && !noActiveProjects
    && (!myProjectsQuery.data || selectedProjectMembership != null);

  useEffect(() => {
    if (!myProjectsQuery.data) return;

    const selectedIsValid = selectedProject
      ? myProjects.some((project) => project.project_id === selectedProject)
      : false;
    if (selectedIsValid) return;

    if (myProjects.length === 1) {
      setSelectedProject(myProjects[0].project_id);
      return;
    }

    if (selectedProject) {
      setSelectedProject(null);
    }
  }, [myProjects, myProjectsQuery.data, myProjectIdsKey, selectedProject, setSelectedProject]);

  useEffect(() => {
    if (!openMenu) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      const isInsideMenu = [
        workspaceMenuRef,
        workspacePopoverRef,
        routeMenuRef,
        dateMenuRef,
        envMenuRef,
        accountMenuRef,
      ].some((ref) => ref.current?.contains(target));
      if (!isInsideMenu) setOpenMenu(null);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenMenu(null);
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openMenu]);

  useLayoutEffect(() => {
    if (openMenu !== "workspace") {
      setWorkspacePopoverStyle(null);
      return;
    }

    function syncWorkspacePopover() {
      if (typeof window === "undefined") return;
      const trigger = workspaceButtonRef.current;
      if (!trigger) return;

      const gutter = 12;
      const rect = trigger.getBoundingClientRect();
      const width = Math.min(312, window.innerWidth - gutter * 2);
      const left = Math.min(Math.max(rect.left, gutter), window.innerWidth - width - gutter);
      const bottom = Math.max(gutter, window.innerHeight - rect.top + 8);
      const maxHeight = Math.max(180, rect.top - gutter * 2);

      setWorkspacePopoverStyle({
        position: "fixed",
        left,
        right: "auto",
        top: "auto",
        bottom,
        width,
        maxHeight,
      });
    }

    syncWorkspacePopover();
    window.addEventListener("resize", syncWorkspacePopover);
    window.addEventListener("scroll", syncWorkspacePopover, true);
    return () => {
      window.removeEventListener("resize", syncWorkspacePopover);
      window.removeEventListener("scroll", syncWorkspacePopover, true);
    };
  }, [openMenu]);

  const issuesQuery = useQuery({
    queryKey: ["shell-issues-count"],
    queryFn: () => listIssues({ status: "open", limit: 50 }),
    enabled: projectContextReady,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const billingQuery = useQuery({
    queryKey: ["billing", "me"],
    queryFn: ({ signal }) => getBillingMe(signal),
    enabled: projectContextReady,
    staleTime: 60_000,
  });

  const budgetQuery = useQuery({
    queryKey: ["shell-budget-status"],
    queryFn: ({ signal }) => getBudgetStatus(signal),
    enabled: projectContextReady,
    staleTime: 60_000,
    retry: false,
  });

  const issuesCount = issuesQuery.data?.items?.length ?? 0;
  const planTemplate = billingQuery.data?.plan_template;
  const planCode = billingQuery.data?.plan_code;
  const planLabel = formatPlanLabel(planCode);
  const billingStatus = billingQuery.data?.status ?? (billingQuery.isLoading ? "loading" : "unavailable");
  const protectedActionsQuota = numericEntitlement(planTemplate, "actions.protected.monthly_quota");
  const protectedActionsQuotaLabel = protectedActionsQuota === -1
    ? "Unlimited"
    : protectedActionsQuota != null
      ? formatCompactNumber(protectedActionsQuota)
      : null;
  const planPeriod = billingQuery.isLoading
    ? "Loading billing period"
    : !billingQuery.data?.current_period_end && !billingQuery.data?.trial_end && protectedActionsQuotaLabel
      ? protectedActionsQuota === -1
        ? "Unlimited protected actions"
        : `${protectedActionsQuotaLabel} protected actions/month`
      : periodCopy(billingQuery.data?.current_period_end, billingQuery.data?.trial_end);
  const budgetStatus = budgetQuery.data;
  const hasBudgetLimit = typeof budgetStatus?.limit_usd === "number" && budgetStatus.limit_usd > 0;
  const budgetPercent = hasBudgetLimit
    ? clampPercent(budgetStatus.percent_used ?? (budgetStatus.spent_usd / budgetStatus.limit_usd!) * 100)
    : 0;
  const planMetricMain = hasBudgetLimit
    ? formatMoney(budgetStatus!.spent_usd)
    : protectedActionsQuotaLabel
      ? protectedActionsQuotaLabel
      : billingQuery.isLoading
        ? "Loading"
      : "Quota n/a";
  const planMetricTotal = hasBudgetLimit
    ? `/ ${formatMoney(budgetStatus!.limit_usd!)} budget`
    : protectedActionsQuota != null
      ? protectedActionsQuota === -1
        ? "protected actions"
        : "protected actions / month"
      : "usage unavailable";
  const maxProjects = numericEntitlement(planTemplate, "max_projects");
  const projectLimitReached = maxProjects !== null && maxProjects !== -1 && myProjects.length >= maxProjects;
  const projectLimitStatus = projectLimitCopy(myProjects.length, maxProjects);
  const showPlanUsageTrack = hasBudgetLimit;
  const planCardStatusClass =
    budgetStatus?.status === "critical" ? "is-critical" : budgetStatus?.status === "warning" ? "is-warning" : "is-ok";
  const selectedWindowLabel = dateRangeLabel(dateRange, activeDatePreset);
  const currentRoute = getRouteMeta(pathname);
  const settingsNavActive = pathname === "/settings" || pathname.startsWith("/settings/");
  const sidebarVisible = compactShell ? compactSidebarOpen : sidebarOpen;

  const badges: Record<string, number> = {};
  if (issuesCount > 0) badges.issues = issuesCount;

  const orgName =
    selectedProjectMembership?.project_name?.trim() ||
    projectQuery.data?.name?.trim() ||
    (projectSelectionRequired
      ? "Select project"
      : myProjectsQuery.isLoading || projectQuery.isLoading
        ? "Loading project"
        : "Project unavailable");
  const envDisplay = envLabel.charAt(0).toUpperCase() + envLabel.slice(1);
  const accountEmail = meQuery.data?.email?.trim() || null;
  const accountName =
    meQuery.data?.display_name?.trim() ||
    (accountEmail ? accountEmail.split("@")[0] : null) ||
    (meQuery.isLoading ? "Loading account" : "Account");
  const accountInitials = initials(accountName || accountEmail || "User");

  function toggleMenu(menu: ShellMenu) {
    setOpenMenu((current) => (current === menu ? null : menu));
  }

  function onToggleSidebar() {
    setOpenMenu(null);
    if (compactShell) {
      setCompactSidebarOpen((open) => !open);
      return;
    }
    toggleSidebar();
  }

  function applyDatePreset(presetId: DatePresetId) {
    const preset = DATE_PRESETS.find((item) => item.id === presetId) ?? DATE_PRESETS[1];
    const to = new Date();
    const from = new Date(to);
    from.setDate(to.getDate() - preset.days);
    setActiveDatePreset(preset.id);
    setDateRange({ from, to });
    setOpenMenu(null);
    void queryClient.invalidateQueries({
      predicate: (query) => {
        const root = query.queryKey[0];
        return (
          typeof root === "string" &&
          [
            "calls",
            "cost",
            "loops",
            "outcomes",
            "traces",
            "reliability",
            "shell-issues-count",
            "shell-agents-count",
          ].includes(root)
        );
      },
    });
  }

  function switchProject(projectId: string) {
    if (projectId === selectedProject) {
      setOpenMenu(null);
      return;
    }

    setSelectedProject(projectId);
    setOpenMenu(null);
    void queryClient.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== "me",
    });
  }

  function openProjectDetails(projectId: string) {
    if (projectId !== selectedProject) {
      setSelectedProject(projectId);
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== "me",
      });
    }
    setOpenMenu(null);
    router.push(`/projects/${encodeURIComponent(projectId)}`);
  }

  function openCommandPalette() {
    setOpenMenu(null);
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }

  function onLogout() {
    setOpenMenu(null);
    clearAccessToken();
    router.replace("/login?logged_out=1");
    router.refresh();
  }

  const workspacePopover = openMenu === "workspace" && workspacePopoverStyle ? (
    <div
      ref={workspacePopoverRef}
      className="shell-popover shell-popover-up shell-popover-portal org-popover"
      role="menu"
      aria-label="Project menu"
      style={workspacePopoverStyle}
    >
      <div className="shell-popover-head">
        <span>Projects</span>
        <strong>{projectSelectionRequired ? "Select a project" : "Project switcher"}</strong>
        <small>{projectLimitStatus}</small>
      </div>
      {myProjects.length > 0 ? (
        myProjects.map((project) => {
          const isSelected = project.project_id === selectedProject;
          const projectRoleLabel = formatRoleLabel(project.role);
          return (
            <button
              key={project.project_id}
              type="button"
              className={`shell-menu-item${isSelected ? " is-active" : ""}`}
              role="menuitem"
              aria-current={isSelected ? "true" : undefined}
              onClick={() => openProjectDetails(project.project_id)}
            >
              <FolderOpen size={15} aria-hidden="true" />
              <span>
                <strong>{project.project_name}</strong>
                <small>
                  <span className="org-menu-project-id" title={project.project_id}>
                    {compactIdentifier(project.project_id)}
                  </span>
                  <span className="org-role-badge">{projectRoleLabel}</span>
                </small>
              </span>
              {isSelected ? <Check size={14} className="shell-menu-check" aria-hidden="true" /> : null}
            </button>
          );
        })
      ) : (
        <div className="shell-menu-item is-static" role="menuitem" aria-disabled="true">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>
            <strong>{myProjectsQuery.isLoading ? "Loading projects" : "No active projects"}</strong>
            <small>{myProjectsQuery.isLoading ? "Fetching your memberships." : "Ask an admin to add you to a project."}</small>
          </span>
        </div>
      )}
      <Link
        href={projectLimitReached ? "/settings/billing" : "/projects"}
        className={`shell-menu-item${projectLimitReached ? " is-muted-action" : ""}`}
        role="menuitem"
        onClick={() => setOpenMenu(null)}
      >
        {projectLimitReached ? <CreditCard size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
        <span>
          <strong>{projectLimitReached ? "Upgrade to add more" : "New project"}</strong>
        </span>
      </Link>
      <Link href="/projects" className="shell-menu-item" role="menuitem" onClick={() => setOpenMenu(null)}>
        <Settings2 size={15} aria-hidden="true" />
        <span>
          <strong>Manage projects</strong>
        </span>
      </Link>
      <Link href="/settings/team" className="shell-menu-item" role="menuitem" onClick={() => setOpenMenu(null)}>
        <UserRound size={15} aria-hidden="true" />
        <span>
          <strong>Team access</strong>
        </span>
      </Link>
    </div>
  ) : null;

  return (
    <div
      ref={appShellRef}
      className={`app-shell ${sidebarVisible ? "" : "sidebar-collapsed"}`}
      data-dashboard-system="control-v1"
    >
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarVisible ? "" : "sidebar-hidden"}`}>
        <Link href="/home" className="sidebar-logo" aria-label="Zroky dashboard home">
          <Image
            src="/zroky-sidebar-logo-transparent.png"
            alt="Zroky"
            width={34}
            height={34}
            priority
            className="sidebar-logo-image"
          />
          <span className="sidebar-logo-word">Zroky</span>
        </Link>

        <nav className="nav-links" aria-label="Primary">
          {NAV_SECTIONS.map((section, index) => {
            const sectionItems = section.itemIds
              .map((id) => VISIBLE_NAV.find((item) => item.id === id))
              .filter((item): item is NavItem => Boolean(item));
            if (sectionItems.length === 0) return null;
            return (
              <div key={section.id} className="nav-section-block" data-nav-section={section.id}>
                <span className={`nav-section-label${index > 0 ? " nav-section-label-spaced" : ""}`}>{section.label}</span>
                {sectionItems.map((item) => {
                  const { badgeKey } = item;
                  const count = badgeKey ? (badges[badgeKey] ?? 0) : 0;
                  return (
                    <NavFeatureGate
                      key={item.id}
                      item={item}
                      pathname={pathname}
                      badgeCount={count}
                      planTemplate={planTemplate}
                      planCode={planCode}
                      entitlementLoading={billingQuery.isLoading}
                    />
                  );
                })}
              </div>
            );
          })}
          <span className="nav-section-label nav-section-label-spaced">Workspace</span>
          {VISIBLE_NAV.filter((item) => item.id === "settings").map((item) => {
            const { badgeKey } = item;
            const count = badgeKey ? (badges[badgeKey] ?? 0) : 0;
            return (
              <NavFeatureGate
                key={item.id}
                item={item}
                pathname={pathname}
                badgeCount={count}
                planTemplate={planTemplate}
                planCode={planCode}
                entitlementLoading={billingQuery.isLoading}
              />
            );
          })}
          {settingsNavActive ? (
            <div className="settings-subnav" role="group" aria-label="Settings sections">
              {SETTINGS_CHILD_LINKS.map((item) => {
                const Icon = item.Icon;
                const active = item.href === "/settings" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`settings-subnav-link${active ? " is-active" : ""}`}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon size={13} aria-hidden="true" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ) : null}
        </nav>

        <div className="sidebar-foot">
          <Link href="/settings/billing" className={`plan-card ${planCardStatusClass}`} aria-label="Open billing and usage">
            <div className="plan-card-head">
              <span className="plan-badge">{planLabel}</span>
              <span className="plan-status">{billingStatus}</span>
            </div>
            <span className="plan-renew">{planPeriod}</span>
            <div className="plan-usage-label">
              <span>{planMetricMain}</span>
              <span className="plan-usage-total">{planMetricTotal}</span>
            </div>
            {showPlanUsageTrack ? (
              <div className="plan-usage-track">
                <div className="plan-usage-fill" style={{ width: `${budgetPercent}%` }} />
              </div>
            ) : null}
            <span className="plan-usage-link">
              View billing <ArrowRight size={12} aria-hidden="true" />
            </span>
          </Link>

          <div className="org-menu" ref={workspaceMenuRef}>
            <button
              ref={workspaceButtonRef}
              type="button"
              className={`org-widget${openMenu === "workspace" ? " org-widget-active" : ""}`}
              aria-label="Open project menu"
              aria-haspopup="menu"
              aria-expanded={openMenu === "workspace"}
              onClick={() => toggleMenu("workspace")}
            >
              <span className="org-avatar" aria-hidden="true">
                {initials(orgName)}
              </span>
              <span className="org-info">
                <span className="org-kicker">Project</span>
                <span className="org-name">{orgName}</span>
                <span className="org-meta">
                  <span className="org-env">
                    <span className="org-env-dot" />
                    {envDisplay}
                  </span>
                </span>
              </span>
              <ChevronDown size={13} className="org-chevron" />
            </button>
            {workspacePopover && workspacePopoverTarget ? createPortal(workspacePopover, workspacePopoverTarget) : null}
          </div>

        </div>
      </aside>

      {/* Content */}
      <section className="content">
        <header className="topbar">
          <div className="topbar-breadcrumb" ref={routeMenuRef}>
            <button
              type="button"
              className="sidebar-toggle"
              onClick={onToggleSidebar}
              aria-label="Toggle sidebar"
            >
              {sidebarVisible ? <X size={16} /> : <Menu size={16} />}
            </button>
            <button
              type="button"
              className="topbar-route-trigger"
              aria-label="Open dashboard navigation menu"
              aria-haspopup="menu"
              aria-expanded={openMenu === "route"}
              onClick={() => toggleMenu("route")}
            >
              <FolderOpen size={14} className="topbar-bc-icon" />
              <span className="topbar-bc-org">Dashboard</span>
              <span className="topbar-bc-sep">/</span>
              <span className="topbar-bc-page">{currentRoute?.label ?? getTitle(pathname)}</span>
              <ChevronDown size={12} className="topbar-bc-chevron" />
            </button>

            {openMenu === "route" ? (
              <div className="shell-popover topbar-popover route-popover" role="menu" aria-label="Dashboard navigation">
                <div className="shell-popover-head">
                  <span>Jump to module</span>
                  <strong>{currentRoute?.subtitle ?? "Open a dashboard module."}</strong>
                </div>
                {VISIBLE_NAV.map((item) => {
                  const Icon = item.Icon;
                  const isActive = item.href ? pathname === item.href || pathname.startsWith(`${item.href}/`) : false;
                  return item.href ? (
                    <Link
                      key={item.id}
                      href={item.href}
                      className={`shell-menu-item${isActive ? " is-active" : ""}`}
                      role="menuitem"
                      onClick={() => setOpenMenu(null)}
                    >
                      <Icon size={15} aria-hidden="true" />
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.subtitle}</small>
                      </span>
                      {isActive ? <Check size={14} className="shell-menu-check" aria-hidden="true" /> : null}
                    </Link>
                  ) : null;
                })}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            className="topbar-search"
            onClick={openCommandPalette}
            aria-label="Search actions, agents, and evidence"
          >
            <Search className="topbar-search-icon" size={14} aria-hidden="true" />
            <span className="topbar-search-hint">Search actions, agents, evidence...</span>
            <kbd className="topbar-search-kbd">⌘K</kbd>
          </button>

          <div className="topbar-controls">
            <div className="topbar-menu-wrap" ref={dateMenuRef}>
              <button
                type="button"
                className="topbar-ctrl-btn"
                aria-label="Choose dashboard time window"
                aria-haspopup="menu"
                aria-expanded={openMenu === "date"}
                onClick={() => toggleMenu("date")}
              >
                <Calendar size={13} aria-hidden="true" />
                <span>{selectedWindowLabel}</span>
                <ChevronDown size={11} aria-hidden="true" />
              </button>
              {openMenu === "date" ? (
                <div className="shell-popover topbar-popover date-popover" role="menu" aria-label="Dashboard time window">
                  <div className="shell-popover-head">
                    <span>Time window</span>
                    <strong>Updates the global dashboard range.</strong>
                  </div>
                  {DATE_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className={`shell-menu-item${activeDatePreset === preset.id ? " is-active" : ""}`}
                      role="menuitem"
                      onClick={() => applyDatePreset(preset.id)}
                    >
                      <Clock3 size={15} aria-hidden="true" />
                      <span>
                        <strong>{preset.label}</strong>
                        <small>{preset.helper}</small>
                      </span>
                      {activeDatePreset === preset.id ? <Check size={14} className="shell-menu-check" aria-hidden="true" /> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="topbar-menu-wrap" ref={envMenuRef}>
              <button
                type="button"
                className="topbar-env-btn"
                aria-label="Open environment status"
                aria-haspopup="menu"
                aria-expanded={openMenu === "env"}
                onClick={() => toggleMenu("env")}
              >
                <span className="topbar-env-dot" />
                <span>{envDisplay}</span>
                <ChevronDown size={11} aria-hidden="true" />
              </button>
              {openMenu === "env" ? (
                <div className="shell-popover topbar-popover env-popover" role="menu" aria-label="Environment status">
                  <div className="shell-popover-head">
                    <span>Environment</span>
                    <strong>{envDisplay} build target</strong>
                  </div>
                  <div className="shell-menu-item is-static" role="menuitem" aria-disabled="true">
                    <Gauge size={15} aria-hidden="true" />
                    <span>
                      <strong>Runtime environment</strong>
                      <small>Set by NEXT_PUBLIC_DASHBOARD_ENV.</small>
                    </span>
                    <Check size={14} className="shell-menu-check" aria-hidden="true" />
                  </div>
                  <button
                    type="button"
                    className={`shell-menu-item${realTimeEnabled ? " is-active" : ""}`}
                    role="menuitem"
                    onClick={() => toggleRealTime()}
                  >
                    <RotateCcw size={15} aria-hidden="true" />
                    <span>
                      <strong>Live dashboard refresh</strong>
                      <small>{realTimeEnabled ? "Enabled for polling-backed widgets." : "Paused in this browser."}</small>
                    </span>
                    {realTimeEnabled ? <Check size={14} className="shell-menu-check" aria-hidden="true" /> : null}
                  </button>
                </div>
              ) : null}
            </div>

            <div className="topbar-menu-wrap topbar-account-menu" ref={accountMenuRef}>
              <button
                type="button"
                className={`topbar-account-btn${accountMenuOpen ? " topbar-account-btn-active" : ""}`}
                aria-label={`Open profile menu for ${accountName}`}
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                title={accountEmail ?? accountName}
                onClick={() => toggleMenu("account")}
              >
                <span className="user-avatar">{accountInitials}</span>
                <span className="topbar-account-name">{accountName}</span>
                <ChevronDown size={11} className="user-row-chevron" aria-hidden="true" />
              </button>

              {accountMenuOpen ? (
                <div className="user-menu-popover topbar-account-popover" role="menu" aria-label="Account menu">
                  <div className="user-menu-head">
                    <span className="user-avatar">{accountInitials}</span>
                    <span className="user-info">
                      <span className="user-name">{accountName}</span>
                      <span className="user-email">{accountEmail ?? "No email set"}</span>
                    </span>
                  </div>
                  <Link
                    href="/account"
                    className="user-menu-item"
                    role="menuitem"
                    aria-label="Profile & security"
                    onClick={() => setOpenMenu(null)}
                  >
                    <UserRound size={15} aria-hidden="true" />
                    <span>
                      <strong>Profile & security</strong>
                      <small>Identity, password, and sessions.</small>
                    </span>
                  </Link>
                  <button
                    type="button"
                    className="user-menu-item user-menu-danger"
                    role="menuitem"
                    aria-label="Log out"
                    onClick={onLogout}
                  >
                    <LogOut size={15} aria-hidden="true" />
                    <span>
                      <strong>Log out</strong>
                      <small>End this browser session.</small>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="content-inner page-enter">
          {projectContextReady ? (
            children
          ) : (
            <ProjectContextGate
              isLoading={projectContextLoading}
              noProjects={noActiveProjects}
              requiresSelection={projectSelectionRequired}
              projects={myProjects}
              onSelectProject={switchProject}
            />
          )}
        </main>
      </section>

      <CommandPalette />
      <ShortcutsHelp />
    </div>
  );
}
