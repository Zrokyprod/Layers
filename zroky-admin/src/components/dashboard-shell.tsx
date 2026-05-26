"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  DollarSign,
  FlaskConical,
  List,
  LogOut,
  Menu,
  RotateCcw,
  Settings,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useOwnerProjects, useProjectSettings } from "@/lib/hooks";
import { ThemeToggle } from "./theme-toggle";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";
import { SavedYouBadge } from "./saved-you-badge";
import { AskZroky } from "./ask-zroky";

type NavItem = { href: string; label: string; icon: LucideIcon; pilotPlaceholder?: boolean };
const dashboardLinks: ReadonlyArray<NavItem> = [
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/issues", label: "Issues", icon: AlertTriangle },
  { href: "/replay", label: "Replay", icon: RotateCcw },
  { href: "/goldens", label: "Goldens", icon: FlaskConical },
  { href: "/drift", label: "Drift", icon: Activity },
  { href: "/calls", label: "Calls", icon: List },
  { href: "/cost", label: "Cost", icon: DollarSign },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

function getTitle(pathname: string): string {
  if (pathname.startsWith("/calls/")) {
    return "Call Detail";
  }
  if (pathname.startsWith("/anomalies/") || pathname.startsWith("/issues/")) {
    return "Issue Detail";
  }
  if (pathname === "/home") {
    return "Command Center";
  }
  if (pathname === "/reliability") {
    return "Agents";
  }
  if (pathname === "/issues") {
    return "Issues";
  }
  if (pathname.startsWith("/replay/")) {
    return "Replay Run";
  }
  if (pathname === "/recommendations" || pathname.startsWith("/recommendations/")) {
    return "Fix Queue";
  }
  if (pathname === "/settings/evaluation") {
    return "Evaluation Settings";
  }
  if (pathname === "/calibration" || pathname.startsWith("/calibration/")) {
    return "Calibration";
  }
  if (pathname === "/judge" || pathname.startsWith("/judge/")) {
    return "Judge";
  }
  if (pathname === "/root-cause" || pathname.startsWith("/root-cause/")) {
    return "Root Cause";
  }
  if (pathname === "/trace" || pathname.startsWith("/trace/")) {
    return "Trace";
  }
  if (pathname === "/cost" || pathname.startsWith("/cost/")) {
    return "Cost";
  }

  const match = dashboardLinks.find((item) => item.href === pathname);
  if (match) {
    return match.label;
  }

  if (pathname.startsWith("/auth/")) {
    return "Auth";
  }

  return "Dashboard";
}

function getSubTitle(pathname: string): string {
  if (pathname === "/home") {
    return "Secondary command center for project-wide operational context.";
  }
  if (pathname === "/agents" || pathname.startsWith("/agents/") || pathname === "/reliability") {
    return "Launch from real agent health, reliability, cost, and determinism data.";
  }
  if (pathname === "/cost" || pathname.startsWith("/cost/")) {
    return "What you spent — and what failures cost you.";
  }
  if (pathname.startsWith("/calls")) {
    return "What your agent said — every prompt, response, and trace.";
  }
  if (pathname === "/anomalies" || pathname.startsWith("/anomalies/") || pathname === "/issues" || pathname.startsWith("/issues/")) {
    return "Top production problems — not raw traces. Plain-English root cause and one-click fix.";
  }
  if (pathname === "/replay" || pathname.startsWith("/replay/")) {
    return "Test your fix against past data before deploying.";
  }
  if (pathname === "/goldens" || pathname.startsWith("/goldens/")) {
    return "Golden datasets for regression-safe evaluation.";
  }
  if (pathname === "/drift" || pathname.startsWith("/drift/")) {
    return "Provider and model behavior drift over time.";
  }
  if (pathname === "/alerts" || pathname.startsWith("/alerts/")) {
    return "Alert routing, triage, acknowledgement, and resolution.";
  }
  if (pathname === "/recommendations" || pathname.startsWith("/recommendations/")) {
    return "What to fix next, ranked by dollar impact.";
  }
  if (pathname === "/settings") {
    return "Project, members, providers, plan & billing.";
  }
  if (pathname === "/settings/keys") {
    return "Create and revoke API keys for this project.";
  }
  if (pathname === "/settings/providers") {
    return "Upstream provider keys vault for replay execution.";
  }
  if (pathname === "/settings/integrations/slack") {
    return "Connect Slack alerts and reliability events to your incident channel.";
  }
  if (pathname === "/settings/integrations/teams") {
    return "Connect Microsoft Teams alerts and reliability events to your team channel.";
  }
  if (pathname === "/settings/billing") {
    return "Plan, usage, and Stripe-managed billing.";
  }
  if (pathname === "/settings/profile") {
    return "Identity, password, 2FA, account deletion.";
  }
  if (pathname === "/settings/team") {
    return "Invite and remove project members.";
  }
  if (pathname === "/settings/evaluation") {
    return "Calibration and judge controls live here.";
  }
  if (pathname === "/outcomes" || pathname.startsWith("/outcomes/")) {
    return "Business cost of every failure — refunds, escalations, churn, attributed by agent.";
  }
  if (pathname === "/calibration" || pathname.startsWith("/calibration/")) {
    return "Secondary evaluation workspace linked from Settings.";
  }
  if (pathname === "/judge" || pathname.startsWith("/judge/")) {
    return "Secondary judge diagnostics linked from Settings.";
  }
  if (pathname === "/root-cause" || pathname.startsWith("/root-cause/")) {
    return "Root-cause analysis belongs in issue context.";
  }
  if (pathname === "/trace" || pathname.startsWith("/trace/")) {
    return "Deep-linked trace evidence for calls and issues.";
  }
  return "Operational view";
}

function navClass(pathname: string, href: string): string {
  const isActive = pathname === href || pathname.startsWith(`${href}/`);
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

// Renders a navigable `<Link>` for real routes, or a non-navigable `<span>` for
// placeholders. We never let users click into a route that doesn't yet exist —
// the previous implementation rendered placeholders as real `<Link>`s and gave
// users 404s. The "soon" badge is preserved either way.
function NavEntry({ pathname, item }: { pathname: string; item: NavItem }) {
  const Icon = item.icon;
  const label = (
    <>
      <span className="nav-link-main">
        <Icon className="nav-link-icon" aria-hidden="true" />
        <span>{item.label}</span>
      </span>
      {item.pilotPlaceholder ? <span className="nav-link-soon">soon</span> : null}
    </>
  );
  if (item.pilotPlaceholder) {
    return (
      <span
        className="nav-link nav-link-placeholder"
        role="link"
        aria-disabled="true"
        title={`${item.label} is on the roadmap — coming soon.`}
      >
        {label}
      </span>
    );
  }
  return (
    <Link href={item.href} className={navClass(pathname, item.href)}>
      {label}
    </Link>
  );
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const envLabel = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "staging";
  const projectLabel = process.env.NEXT_PUBLIC_DASHBOARD_PROJECT_LABEL ?? "project";
  const projectQuery = useProjectSettings();
  const ownerProjectsQuery = useOwnerProjects(200, 0);

  // Use store for sidebar state
  const {
    sidebarOpen,
    toggleSidebar,
    setLastVisitedPage,
    sdkConnected,
    selectedProject,
    setSelectedProject,
  } = useDashboardStore();

  // Enable keyboard shortcuts
  useKeyboardShortcuts();

  // Track last visited page
  useEffect(() => {
    setLastVisitedPage(pathname);
  }, [pathname, setLastVisitedPage]);

  useEffect(() => {
    const projectId = projectQuery.data?.project_id ?? null;
    if (projectId && !selectedProject) {
      setSelectedProject(projectId);
    }
  }, [projectQuery.data?.project_id, selectedProject, setSelectedProject]);

  const projectOptions = useMemo(() => {
    const items = new Map<string, string>();

    const ownerProjects = ownerProjectsQuery.data?.projects ?? [];
    for (const project of ownerProjects) {
      if (project.id) {
        items.set(project.id, project.name || project.id);
      }
    }

    if (projectQuery.data?.project_id) {
      const id = projectQuery.data.project_id;
      const name = projectQuery.data.name ?? id;
      items.set(id, name);
    }

    if (selectedProject && !items.has(selectedProject)) {
      items.set(selectedProject, selectedProject);
    }

    return Array.from(items.entries()).map(([id, name]) => ({ id, name }));
  }, [ownerProjectsQuery.data?.projects, projectQuery.data, selectedProject]);

  function onLogout() {
    clearAccessToken();
    router.replace("/auth/login?logged_out=1");
    router.refresh();
  }

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <aside className={`sidebar ${sidebarOpen ? "" : "hidden lg:flex"}`}>
        <div className="brand">
          <h1>Zroky Dashboard</h1>
          <p>Failure intelligence with decisive actions.</p>
        </div>

        <nav className="nav-links" aria-label="Primary">
          {dashboardLinks.map((item) => (
            <NavEntry key={item.href} pathname={pathname} item={item} />
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-actions">
            <ThemeToggle />
          </div>
          <button type="button" className="nav-link nav-link-button" onClick={onLogout}>
            <span className="nav-link-main">
              <LogOut className="nav-link-icon" aria-hidden="true" />
              <span>Logout</span>
            </span>
          </button>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="sidebar-toggle lg:hidden"
              onClick={toggleSidebar}
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <div className="topbar-title">
              <h2>{getTitle(pathname)}</h2>
              <p>{getSubTitle(pathname)}</p>
            </div>
          </div>
          <div className="topbar-meta">
            <button
              type="button"
              className="ask-trigger-btn"
              onClick={() => window.dispatchEvent(new CustomEvent("open-ask-zroky"))}
              aria-label="Open Ask Zroky"
              title="Ask Zroky anything about your agent (Ctrl+J)"
            >
              <Sparkles className="ask-trigger-icon" aria-hidden="true" />
              <span className="ask-trigger-text">Ask Zroky</span>
              <kbd className="ask-trigger-kbd">Ctrl+J</kbd>
            </button>
            <button
              type="button"
              className="cp-trigger-btn"
              onClick={() => window.dispatchEvent(new CustomEvent("open-command-palette"))}
              aria-label="Open command palette"
            >
              <span className="cp-trigger-text">Search…</span>
              <kbd className="cp-trigger-kbd">Ctrl+K</kbd>
            </button>
            <SavedYouBadge />
            <span
              className={`sdk-badge ${sdkConnected ? "sdk-badge-connected" : "sdk-badge-idle"}`}
              title={sdkConnected ? "SDK is sending live data" : "No live data received yet"}
              aria-label={sdkConnected ? "SDK connected" : "SDK not connected"}
            >
              <span className="sdk-badge-dot" aria-hidden="true" />
              {sdkConnected ? "SDK Live" : "SDK Idle"}
            </span>
            <button
              type="button"
              className="sh-help-btn"
              aria-label="Show keyboard shortcuts (Shift+?)"
              title="Keyboard shortcuts (Shift+?)"
              onClick={() => window.dispatchEvent(new CustomEvent("show-shortcuts-help"))}
            >
              ?
            </button>
            <label className="project-switch-wrap" aria-label="Project selector">
              <span className="project-switch-label">Project</span>
              <select
                className="project-switch-select mono"
                value={selectedProject ?? projectQuery.data?.project_id ?? ""}
                onChange={(event) => setSelectedProject(event.target.value || null)}
              >
                {projectOptions.length > 0 ? (
                  projectOptions.map((project) => (
                    <option key={project.id} value={project.id}>{project.name}</option>
                  ))
                ) : (
                  <option value="">{projectLabel}</option>
                )}
              </select>
            </label>
            <span className="env-badge">{envLabel.toUpperCase()}</span>
          </div>
        </header>

        <nav className="mobile-nav" aria-label="Mobile Primary">
          {dashboardLinks.map((item) => (
            <NavEntry key={item.href} pathname={pathname} item={item} />
          ))}
        </nav>

        <main className="content-inner page-enter">{children}</main>
      </section>
      <CommandPalette />
      <ShortcutsHelp />
      <AskZroky />
    </div>
  );
}
