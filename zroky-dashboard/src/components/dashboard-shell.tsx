"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Calendar,
  Check,
  ChevronDown,
  Clock3,
  DollarSign,
  FolderOpen,
  GitBranch,
  GitPullRequest,
  Gauge,
  Inbox,
  LockKeyhole,
  LogOut,
  Menu,
  RotateCcw,
  Search,
  Settings2,
  Shield,
  SlidersHorizontal,
  UserRound,
  X,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { getBillingMe, getBudgetStatus, listIssues, getReliabilityLeaderboard } from "@/lib/api";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useMe, useProjectSettings } from "@/lib/hooks";
import { formatPlanLabel, hasFeatureAccess } from "./feature-gate";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";

type NavItem = {
  id: string;
  href?: string;
  label: string;
  subtitle: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  badgeKey?: "issues" | "agents";
  requiredEntitlement?: string;
  placeholder?: boolean;
  visibleInNav?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  {
    id: "failure-inbox",
    href: "/home",
    label: "Failure Inbox",
    subtitle: "Production failure queue, agent health, replay readiness, and next actions.",
    Icon: Inbox,
    badgeKey: "agents",
    visibleInNav: true,
  },
  {
    id: "issues",
    href: "/issues",
    label: "Issues",
    subtitle: "Clustered production failures with impact, owners, and release decisions.",
    Icon: AlertTriangle,
    badgeKey: "issues",
    visibleInNav: true,
  },
  {
    id: "replay-lab",
    href: "/replay",
    label: "Replay Lab",
    subtitle: "Run incident replays, compare outcomes, and verify candidate fixes.",
    Icon: RotateCcw,
    requiredEntitlement: "pilot.replay_stub",
    visibleInNav: true,
  },
  {
    id: "goldens",
    href: "/goldens",
    label: "Goldens",
    subtitle: "Promoted release guards and regression coverage before merge.",
    Icon: Shield,
    requiredEntitlement: "pilot.goldens_basic",
    visibleInNav: true,
  },
  {
    id: "ci-gates",
    href: "/ci-gates",
    label: "CI Gates",
    subtitle: "Regression CI gate controls for pull request safety.",
    Icon: GitPullRequest,
    requiredEntitlement: "pilot.goldens_basic",
    visibleInNav: true,
  },
  {
    id: "traces",
    href: "/trace",
    label: "Traces",
    subtitle: "Trace-by-trace execution paths, span evidence, and multi-agent context.",
    Icon: GitBranch,
    visibleInNav: true,
  },
  {
    id: "cost",
    href: "/cost",
    label: "Cost",
    subtitle: "Failure cost, model mix, budget risk, and spend controls.",
    Icon: DollarSign,
    visibleInNav: true,
  },
  {
    id: "settings",
    href: "/settings",
    label: "Settings",
    subtitle: "Project, providers, billing, notifications, and team controls.",
    Icon: Settings2,
    visibleInNav: true,
  },
];

const VISIBLE_NAV = NAV_ITEMS.filter((n) => n.visibleInNav);

const DATE_PRESETS = [
  { id: "24h", label: "Last 24 hours", days: 1, helper: "Incidents and cost from the last day." },
  { id: "7d", label: "Last 7 days", days: 7, helper: "Default production review window." },
  { id: "14d", label: "Last 14 days", days: 14, helper: "Useful for release-cycle checks." },
  { id: "30d", label: "Last 30 days", days: 30, helper: "Monthly trend and budget review." },
] as const;

type DatePresetId = (typeof DATE_PRESETS)[number]["id"];
type ShellMenu = "workspace" | "route" | "date" | "env" | "filters" | "account";

type ShellActionLink = {
  href: string;
  label: string;
  description: string;
};

const DASHBOARD_ROUTES = [
  ...NAV_ITEMS,
  {
    id: "calls",
    href: "/calls",
    label: "Calls",
    subtitle: "Search individual calls, diagnoses, and call-level evidence.",
    Icon: GitBranch,
  },
  {
    id: "home",
    href: "/home",
    label: "Failure Inbox",
    subtitle: "Production failure queue, replay gaps, CI gates, and review actions.",
    Icon: Bot,
  },
  {
    id: "alerts",
    href: "/alerts",
    label: "Alerts",
    subtitle: "Alert routing, triage, acknowledgement, and resolution.",
    Icon: AlertTriangle,
  },
  {
    id: "drift",
    href: "/drift",
    label: "Provider Drift",
    subtitle: "Provider and model behavior drift over time.",
    Icon: GitBranch,
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
    DASHBOARD_ROUTES.find((r) => pathname === r.href || pathname.startsWith(`${r.href}/`)) ?? null
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
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
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

function filterLinksForPath(pathname: string): ShellActionLink[] {
  if (pathname.startsWith("/calls")) {
    return [
      {
        href: "/calls?status=failed&sort_by=created_at&sort_order=desc",
        label: "Failed calls",
        description: "Open the Calls table with failed calls first.",
      },
      {
        href: "/calls?sort_by=cost_usd&sort_order=desc",
        label: "Highest spend",
        description: "Sort calls by cost impact.",
      },
      {
        href: "/cost",
        label: "Cost explorer",
        description: "Move from call-level evidence to spend impact.",
      },
    ];
  }

  if (pathname.startsWith("/settings")) {
    return [
      { href: "/settings/billing", label: "Plan & billing", description: "Open plan, quota, and Stripe controls." },
      { href: "/settings/providers", label: "Providers", description: "Check model provider connection health." },
      { href: "/settings/keys", label: "API keys", description: "Manage project capture keys." },
    ];
  }

  if (pathname.startsWith("/cost")) {
    return [
      {
        href: "/calls?sort_by=cost_usd&sort_order=desc",
        label: "Expensive calls",
        description: "Inspect the calls driving this spend.",
      },
      { href: "/settings/billing", label: "Budget settings", description: "Tune spend limits and plan controls." },
      { href: "/issues", label: "Costly issues", description: "Review clustered failures with business impact." },
    ];
  }

  if (pathname.startsWith("/replay")) {
    return [
      { href: "/issues", label: "Issues needing proof", description: "Find failures that need trusted replay." },
      { href: "/goldens", label: "Golden traces", description: "Promote verified scenarios into release guards." },
      { href: "/ci-gates", label: "CI gates", description: "Run regression gates after replay proof." },
    ];
  }

  if (pathname.startsWith("/goldens")) {
    return [
      { href: "/replay", label: "Replay lab", description: "Run candidates before promotion." },
      { href: "/ci-gates", label: "CI gates", description: "Use goldens as merge protection." },
      { href: "/issues", label: "Open issues", description: "Find failures that need coverage." },
    ];
  }

  if (pathname.startsWith("/ci-gates")) {
    return [
      { href: "/goldens", label: "Golden coverage", description: "Review the guard set behind CI." },
      { href: "/replay", label: "Replay runs", description: "Verify exact scenarios before gate runs." },
      { href: "/issues", label: "Open regressions", description: "Review failures blocked by gates." },
    ];
  }

  if (pathname.startsWith("/trace")) {
    return [
      { href: "/calls?status=failed", label: "Failed calls", description: "Open failed call evidence with filters applied." },
      { href: "/issues", label: "Clustered issues", description: "Move from traces to root-cause clusters." },
      { href: "/replay", label: "Replay scenario", description: "Verify a trace path in Replay Lab." },
    ];
  }

  return [
    { href: "/issues", label: "Open issues", description: "Review unresolved production failures." },
    { href: "/calls?status=failed", label: "Failed calls", description: "Open captured failed calls." },
    { href: "/cost", label: "Cost impact", description: "Inspect wasted spend and budget risk." },
  ];
}

function navClass(pathname: string, href: string): string {
  return pathname === href || pathname.startsWith(`${href}/`)
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
  const disabled = item.placeholder || disabledByPlan || !item.href;
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
      className={navClass(pathname, href)}
      data-nav-id={item.id}
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

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const envLabel = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  const projectQuery = useProjectSettings();
  const meQuery = useMe();
  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const routeMenuRef = useRef<HTMLDivElement>(null);
  const dateMenuRef = useRef<HTMLDivElement>(null);
  const envMenuRef = useRef<HTMLDivElement>(null);
  const filtersMenuRef = useRef<HTMLDivElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const [openMenu, setOpenMenu] = useState<ShellMenu | null>(null);
  const [activeDatePreset, setActiveDatePreset] = useState<DatePresetId>("7d");
  const [compactShell, setCompactShell] = useState(false);
  const [compactSidebarOpen, setCompactSidebarOpen] = useState(false);
  const accountMenuOpen = openMenu === "account";

  const {
    sidebarOpen,
    toggleSidebar,
    closeSidebar,
    setLastVisitedPage,
    selectedProject,
    setSelectedProject,
    dateRange,
    setDateRange,
    realTimeEnabled,
    toggleRealTime,
  } = useDashboardStore();

  useKeyboardShortcuts();

  useEffect(() => {
    setLastVisitedPage(pathname);
  }, [pathname, setLastVisitedPage]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const mobileShell = window.matchMedia("(max-width: 1120px)");
    const syncMobileSidebar = () => {
      const isCompact = mobileShell.matches;
      setCompactShell(isCompact);
      if (isCompact) {
        setCompactSidebarOpen(false);
        closeSidebar();
      }
    };

    syncMobileSidebar();
    const hydrationGuard = window.setTimeout(syncMobileSidebar, 0);
    mobileShell.addEventListener("change", syncMobileSidebar);
    return () => {
      window.clearTimeout(hydrationGuard);
      mobileShell.removeEventListener("change", syncMobileSidebar);
    };
  }, [closeSidebar, pathname]);

  useEffect(() => {
    const id = projectQuery.data?.project_id ?? null;
    if (id && id !== selectedProject) setSelectedProject(id);
  }, [projectQuery.data?.project_id, selectedProject, setSelectedProject]);

  useEffect(() => {
    if (!openMenu) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      const isInsideMenu = [
        workspaceMenuRef,
        routeMenuRef,
        dateMenuRef,
        envMenuRef,
        filtersMenuRef,
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

  const issuesQuery = useQuery({
    queryKey: ["shell-issues-count"],
    queryFn: () => listIssues({ status: "open", limit: 50 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const agentsQuery = useQuery({
    queryKey: ["shell-agents-count"],
    queryFn: () => getReliabilityLeaderboard(200),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const billingQuery = useQuery({
    queryKey: ["billing", "me"],
    queryFn: ({ signal }) => getBillingMe(signal),
    staleTime: 60_000,
  });

  const budgetQuery = useQuery({
    queryKey: ["shell-budget-status"],
    queryFn: ({ signal }) => getBudgetStatus(signal),
    staleTime: 60_000,
    retry: false,
  });

  const issuesCount = issuesQuery.data?.items?.length ?? 0;
  const agentsCount = Array.isArray(agentsQuery.data) ? agentsQuery.data.length : 0;
  const planTemplate = billingQuery.data?.plan_template;
  const planCode = billingQuery.data?.plan_code;
  const planLabel = formatPlanLabel(planCode);
  const billingStatus = billingQuery.data?.status ?? (billingQuery.isLoading ? "loading" : "unavailable");
  const planPeriod = billingQuery.isLoading
    ? "Loading billing period"
    : periodCopy(billingQuery.data?.current_period_end, billingQuery.data?.trial_end);
  const eventsQuota = numericEntitlement(planTemplate, "events.monthly_quota");
  const budgetStatus = budgetQuery.data;
  const hasBudgetLimit = typeof budgetStatus?.limit_usd === "number" && budgetStatus.limit_usd > 0;
  const budgetPercent = hasBudgetLimit
    ? clampPercent(budgetStatus.percent_used ?? (budgetStatus.spent_usd / budgetStatus.limit_usd!) * 100)
    : 0;
  const planMetricMain = hasBudgetLimit
    ? formatMoney(budgetStatus!.spent_usd)
    : eventsQuota != null
      ? formatCompactNumber(eventsQuota)
      : billingQuery.isLoading
        ? "Loading"
        : "Quota n/a";
  const planMetricTotal = hasBudgetLimit
    ? `/ ${formatMoney(budgetStatus!.limit_usd!)} budget`
    : eventsQuota != null
      ? "events / month"
      : "usage unavailable";
  const planCardStatusClass =
    budgetStatus?.status === "critical" ? "is-critical" : budgetStatus?.status === "warning" ? "is-warning" : "is-ok";
  const selectedWindowLabel = dateRangeLabel(dateRange, activeDatePreset);
  const currentRoute = getRouteMeta(pathname);
  const filterLinks = filterLinksForPath(pathname);
  const sidebarVisible = compactShell ? compactSidebarOpen : sidebarOpen;

  const badges: Record<string, number> = {};
  if (issuesCount > 0) badges.issues = issuesCount;
  if (agentsCount > 0) badges.agents = agentsCount;

  const orgName = projectQuery.data?.name ?? "Acme Corp";
  const envDisplay = envLabel.charAt(0).toUpperCase() + envLabel.slice(1);
  const accountEmail = meQuery.data?.email ?? "sanket@acme.com";
  const accountName = meQuery.data?.display_name?.trim() || accountEmail?.split("@")[0] || "Sanket K.";
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
          ["calls", "cost", "loops", "traces", "reliability", "shell-issues-count", "shell-agents-count"].includes(root)
        );
      },
    });
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

  return (
    <div className={`app-shell ${sidebarVisible ? "" : "sidebar-collapsed"}`}>
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarVisible ? "" : "hidden lg:flex"}`}>
        <div className="sidebar-logo">
          <Image
            src="/zroky-sidebar-logo.png"
            alt="Zroky"
            width={40}
            height={40}
            priority
            className="sidebar-logo-image"
          />
        </div>

        <nav className="nav-links" aria-label="Primary">
          {VISIBLE_NAV.map((item) => {
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
        </nav>

        <div className="sidebar-foot">
          <div className="org-menu" ref={workspaceMenuRef}>
            <button
              type="button"
              className={`org-widget${openMenu === "workspace" ? " org-widget-active" : ""}`}
              aria-label="Open workspace menu"
              aria-haspopup="menu"
              aria-expanded={openMenu === "workspace"}
              onClick={() => toggleMenu("workspace")}
            >
              <span className="org-avatar">{initials(orgName)}</span>
              <span className="org-info">
                <span className="org-name">{orgName}</span>
                <span className="org-env">
                  <span className="org-env-dot" />
                  {envDisplay}
                </span>
              </span>
              <ChevronDown size={13} className="org-chevron" />
            </button>

            {openMenu === "workspace" ? (
              <div className="shell-popover shell-popover-up org-popover" role="menu" aria-label="Workspace menu">
                <div className="shell-popover-head">
                  <span>Current workspace</span>
                  <strong>{orgName}</strong>
                </div>
                <Link href="/settings" className="shell-menu-item" role="menuitem" onClick={() => setOpenMenu(null)}>
                  <Settings2 size={15} aria-hidden="true" />
                  <span>
                    <strong>Project settings</strong>
                    <small>Providers, team, billing, and keys.</small>
                  </span>
                </Link>
                <Link href="/settings/team" className="shell-menu-item" role="menuitem" onClick={() => setOpenMenu(null)}>
                  <UserRound size={15} aria-hidden="true" />
                  <span>
                    <strong>Team access</strong>
                    <small>Invite or remove project members.</small>
                  </span>
                </Link>
                <div className="shell-menu-item is-static" role="menuitem" aria-disabled="true">
                  <FolderOpen size={15} aria-hidden="true" />
                  <span>
                    <strong>Project ID</strong>
                    <small>{projectQuery.data?.project_id ?? selectedProject ?? "Unavailable"}</small>
                  </span>
                </div>
              </div>
            ) : null}
          </div>

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
            <div className="plan-usage-track">
              <div className="plan-usage-fill" style={{ width: `${budgetPercent}%` }} />
            </div>
            <span className="plan-usage-link">
              View billing <ArrowRight size={12} aria-hidden="true" />
            </span>
          </Link>

          <div className="user-menu" ref={accountMenuRef}>
            <button
              type="button"
              className={`user-row${accountMenuOpen ? " user-row-active" : ""}`}
              aria-label="Open account menu"
              aria-haspopup="menu"
              aria-expanded={accountMenuOpen}
              onClick={() => toggleMenu("account")}
            >
              <span className="user-avatar">{accountInitials}</span>
              <span className="user-info">
                <span className="user-name">{accountName}</span>
                <span className="user-email">{accountEmail ?? "No email set"}</span>
              </span>
              <ChevronDown size={13} className="user-row-chevron" aria-hidden="true" />
            </button>

            {accountMenuOpen ? (
              <div className="user-menu-popover" role="menu" aria-label="Account menu">
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
                  onClick={() => setOpenMenu(null)}
                >
                  <UserRound size={15} aria-hidden="true" />
                  Account
                </Link>
                <button type="button" className="user-menu-item user-menu-danger" role="menuitem" onClick={onLogout}>
                  <LogOut size={15} aria-hidden="true" />
                  Log out
                </button>
              </div>
            ) : null}
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
              <span className="topbar-bc-org">{orgName}</span>
              <span className="topbar-bc-sep">/</span>
              <span className="topbar-bc-page">{currentRoute?.label ?? getTitle(pathname)}</span>
              <ChevronDown size={12} className="topbar-bc-chevron" />
            </button>

            {openMenu === "route" ? (
              <div className="shell-popover topbar-popover route-popover" role="menu" aria-label="Dashboard navigation">
                <div className="shell-popover-head">
                  <span>Jump to module</span>
                  <strong>{currentRoute?.subtitle ?? "Open a dashboard workspace."}</strong>
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
            aria-label="Search (Command Palette)"
          >
            <Search className="topbar-search-icon" size={14} aria-hidden="true" />
            <span className="topbar-search-hint">Search traces, issues, failures...</span>
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

            <div className="topbar-menu-wrap" ref={filtersMenuRef}>
              <button
                type="button"
                className="topbar-icon-btn"
                aria-label="Open page actions and filters"
                aria-haspopup="menu"
                aria-expanded={openMenu === "filters"}
                onClick={() => toggleMenu("filters")}
              >
                <SlidersHorizontal size={14} aria-hidden="true" />
              </button>
              {openMenu === "filters" ? (
                <div className="shell-popover topbar-popover filter-popover" role="menu" aria-label="Page actions and filters">
                  <div className="shell-popover-head">
                    <span>Page actions</span>
                    <strong>{getTitle(pathname)}</strong>
                  </div>
                  {filterLinks.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="shell-menu-item"
                      role="menuitem"
                      onClick={() => setOpenMenu(null)}
                    >
                      <SlidersHorizontal size={15} aria-hidden="true" />
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.description}</small>
                      </span>
                      <ArrowRight size={14} className="shell-menu-check" aria-hidden="true" />
                    </Link>
                  ))}
                  <button type="button" className="shell-menu-item" role="menuitem" onClick={openCommandPalette}>
                    <Search size={15} aria-hidden="true" />
                    <span>
                      <strong>Search everything</strong>
                      <small>Open command palette for traces, issues, and routes.</small>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="content-inner page-enter">{children}</main>
      </section>

      <CommandPalette />
      <ShortcutsHelp />
    </div>
  );
}
