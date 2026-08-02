"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  ChevronDown,
  FileJson,
  FolderOpen,
  Gauge,
  Inbox,
  LockKeyhole,
  LogOut,
  Menu,
  Network,
  Plug,
  Search,
  Settings2,
  UserRound,
  X,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { getBillingMe, listIssues } from "@/lib/api";
import { DASHBOARD_PRIMARY_ROUTES } from "@/lib/dashboard-route-contract";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useMe, useMyProjects } from "@/lib/hooks";
import { hasFeatureAccess } from "./feature-gate";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";

type NavItem = {
  id: string;
  href: string;
  label: string;
  subtitle: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  badgeKey?: "issues";
  requiredEntitlement?: string;
  placeholder?: boolean;
  visibleInNav?: boolean;
};

const NAV_META: Record<string, Pick<NavItem, "subtitle" | "Icon">> = {
  home: { subtitle: "Proof posture, attention queue, verification readiness, and recent evidence.", Icon: Inbox },
  operations: { subtitle: "Runs, incidents, approvals, and remediation queues.", Icon: Gauge },
  workflows: { subtitle: "Assurance Packs, policies, and trusted workflow bindings.", Icon: Network },
  connectors: { subtitle: "Read-only source connectors and proof readiness.", Icon: Plug },
  evidence: { subtitle: "Signed bundles, proof trails, audit hashes, and export readiness.", Icon: FileJson },
  settings: { subtitle: "API keys, members, billing, and workspace controls.", Icon: Settings2 },
};

const VISIBLE_NAV: NavItem[] = DASHBOARD_PRIMARY_ROUTES.map((route) => ({
  ...route,
  ...(NAV_META[route.id] ?? { subtitle: route.label, Icon: Inbox }),
}));

type ShellMenu = "account" | "workspace";

function demoDashboardRequested(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("demoHome") === "1" || params.get("demoOperations") === "1" || params.get("demoDashboard") === "1";
}

function routePrefixForHref(href: string): string {
  const cleanHref = href.split(/[?#]/)[0] || href;
  if (cleanHref.startsWith("/settings")) return "/settings";
  if (cleanHref.startsWith("/projects")) return "/projects";
  return cleanHref;
}

function navClass(pathname: string, href: string): string {
  if (href.includes("#") || href.includes("?")) return "nav-link";
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

function ProjectContextGate({
  isLoading,
  isUnavailable,
  noProjects,
  requiresSelection,
  projects,
  onRetry,
  onSelectProject,
}: {
  isLoading: boolean;
  isUnavailable: boolean;
  noProjects: boolean;
  requiresSelection: boolean;
  projects: { project_id: string; project_name: string; role: string }[];
  onRetry: () => void;
  onSelectProject: (projectId: string) => void;
}) {
  const title = isUnavailable
    ? "Workspace unavailable"
    : noProjects
    ? "No active project found"
    : requiresSelection
      ? "Select a project to load this dashboard"
      : "Preparing workspace";
  const body = isUnavailable
    ? "We could not load your projects. Retry the request or sign in again."
    : noProjects
    ? "Ask an owner to add your account to a project before dashboard modules can load data."
    : requiresSelection
      ? "Dashboard data is scoped by project. Choose the project you want to inspect."
      : "Preparing project-scoped dashboard modules.";

  return (
    <section className="panel project-context-gate" aria-live="polite">
      <div className="panel-header">
        <div>
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
        {isLoading ? <span className="pill">Syncing</span> : null}
      </div>

      {isUnavailable ? (
        <div className="project-context-recovery">
          <button type="button" className="btn btn-soft" onClick={onRetry}>Retry</button>
          <Link className="btn btn-primary" href="/login">Sign in again</Link>
        </div>
      ) : requiresSelection ? (
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
  const appShellRef = useRef<HTMLDivElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const [openMenu, setOpenMenu] = useState<ShellMenu | null>(null);
  const [compactShell, setCompactShell] = useState(false);
  const [, setCompactSidebarOpen] = useState(false);
  const [localPreview, setLocalPreview] = useState(false);
  const accountMenuOpen = openMenu === "account";

  const {
    toggleSidebar,
    setLastVisitedPage,
    selectedProject,
    setSelectedProject,
  } = useDashboardStore();

  const myProjectsQuery = useMyProjects();
  const meQuery = useMe();

  useKeyboardShortcuts();

  useEffect(() => {
    setLastVisitedPage(pathname);
  }, [pathname, setLastVisitedPage]);

  useEffect(() => {
    setLocalPreview(demoDashboardRequested());
  }, [pathname]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const mobileShell = window.matchMedia("(max-width: 1279px)");
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
  const localProjectFallback = localPreview && (myProjectsQuery.isError || process.env.NODE_ENV !== "production");
  const projectContextLoading = !localProjectFallback && (myProjectsQuery.isLoading || (myProjects.length === 1 && !selectedProject));
  const projectContextUnavailable = !localProjectFallback && (
    myProjectsQuery.isError || (!myProjectsQuery.isLoading && myProjectsQuery.data === undefined)
  );
  const projectContextReady = localProjectFallback || (Boolean(selectedProject)
    && !projectSelectionRequired
    && !noActiveProjects
    && (!myProjectsQuery.data || selectedProjectMembership != null));

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
      const isInsideMenu = accountMenuRef.current?.contains(target);
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
    enabled: projectContextReady && !localProjectFallback,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const billingQuery = useQuery({
    queryKey: ["billing", "me"],
    queryFn: ({ signal }) => getBillingMe(signal),
    enabled: projectContextReady && !localProjectFallback,
    staleTime: 60_000,
  });

  const issuesCount = issuesQuery.data?.items?.length ?? 0;
  const planTemplate = billingQuery.data?.plan_template;
  const planCode = billingQuery.data?.plan_code;
  const sidebarVisible = true;

  const badges: Record<string, number> = {};
  if (issuesCount > 0) badges.issues = issuesCount;

  const accountEmail = meQuery.data?.email?.trim() || null;
  const accountName =
    meQuery.data?.display_name?.trim() ||
    (accountEmail ? accountEmail.split("@")[0] : null) ||
    (meQuery.isLoading ? "Loading account" : "Account");
  const accountInitials = initials(accountName || accountEmail || "User");
  const workspaceName =
    selectedProjectMembership?.project_name?.trim() ||
    (localProjectFallback ? "Local preview" : null) ||
    (projectContextUnavailable ? "Workspace unavailable" : null) ||
    (projectSelectionRequired ? "Select project" : "ZROKY workspace");

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

  function openCommandPalette() {
    setOpenMenu(null);
    window.dispatchEvent(new CustomEvent("open-command-palette"));
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

  function onLogout() {
    setOpenMenu(null);
    clearAccessToken();
    router.replace("/login?logged_out=1");
    router.refresh();
  }

  return (
    <div
      ref={appShellRef}
      className="app-shell"
      data-dashboard-system="control-v1"
    >
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo-row">
          <Link href="/home" className="sidebar-logo" aria-label="Zroky dashboard home">
            <Image
              src="/zroky-brand.png"
              alt="Zroky"
              width={112}
              height={32}
              priority
              className="sidebar-logo-image"
            />
          </Link>
          <button
            type="button"
            className="sidebar-logo-toggle"
            onClick={onToggleSidebar}
            aria-label="Toggle sidebar"
            hidden
            aria-hidden="true"
            tabIndex={-1}
          >
            {sidebarVisible ? <X size={15} aria-hidden="true" /> : <Menu size={15} aria-hidden="true" />}
          </button>
        </div>

        <Link href="/projects" className="sidebar-context-card" aria-label="Open project context">
          <span className="sidebar-context-mark" aria-hidden="true">
            <FolderOpen size={14} />
          </span>
          <span className="sidebar-context-copy">
            <strong>{workspaceName}</strong>
          </span>
          <ChevronDown size={13} aria-hidden="true" />
        </Link>

        <nav className="nav-links" aria-label="Primary">
          <span className="nav-section-label">Navigation</span>
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
      </aside>

      {/* Content */}
      <section className="content">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="sidebar-toggle"
              onClick={onToggleSidebar}
              aria-label="Toggle sidebar"
              hidden
              aria-hidden="true"
              tabIndex={-1}
            >
              {sidebarVisible ? <X size={16} /> : <Menu size={16} />}
            </button>
            <button
              type="button"
              className="topbar-search"
              aria-label="Search evidence, incidents, workflows"
              onClick={openCommandPalette}
            >
              <Search size={14} className="topbar-search-icon" aria-hidden="true" />
              <span className="topbar-search-hint">Search evidence, incidents, workflows…</span>
              <span className="topbar-search-kbd" aria-hidden="true">⌘K</span>
            </button>
          </div>

          <div className="topbar-controls">
            <button type="button" className="topbar-icon-btn" aria-label="Notifications">
              <Bell size={14} aria-hidden="true" />
              {issuesCount > 0 ? <span className="topbar-notification-dot" aria-hidden="true" /> : null}
            </button>
            <span className="topbar-separator" aria-hidden="true" />

            <div className="topbar-menu-wrap topbar-account-menu" ref={accountMenuRef}>
              <button
                type="button"
                className={`topbar-account-btn${accountMenuOpen ? " topbar-account-btn-active" : ""}`}
                aria-label="Open account menu"
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                title={accountEmail ?? accountName}
                onClick={() => toggleMenu("account")}
              >
                <span className="topbar-account-name">Account</span>
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
              isUnavailable={projectContextUnavailable}
              noProjects={noActiveProjects}
              requiresSelection={projectSelectionRequired}
              projects={myProjects}
              onRetry={() => void myProjectsQuery.refetch()}
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
