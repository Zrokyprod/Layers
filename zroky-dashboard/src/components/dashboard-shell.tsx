"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  ChevronDown,
  DollarSign,
  FlaskConical,
  List,
  LogOut,
  Menu,
  RotateCcw,
  Settings,
  Sparkles,
  User,
  X,
  type LucideIcon,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useMe, useProjectSettings } from "@/lib/hooks";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";
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
  if (pathname === "/issues") {
    return "Issues";
  }
  if (pathname.startsWith("/replay/")) {
    return "Replay Run";
  }
  if (pathname === "/settings/evaluation") {
    return "Evaluation Settings";
  }
  if (pathname === "/settings/profile") {
    return "Profile";
  }
  if (pathname === "/settings/keys") {
    return "API Keys";
  }
  if (pathname === "/settings/providers") {
    return "Providers";
  }
  if (pathname === "/settings/team") {
    return "Members";
  }
  if (pathname === "/settings/billing") {
    return "Plan & Billing";
  }
  if (pathname === "/settings" || pathname.startsWith("/settings/")) {
    return "Settings";
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
  if (pathname === "/agents" || pathname.startsWith("/agents/")) {
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
  const projectLabel = process.env.NEXT_PUBLIC_DASHBOARD_PROJECT_LABEL ?? "project";
  const projectQuery = useProjectSettings();
  const meQuery = useMe();

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

    if (projectQuery.data?.project_id) {
      const id = projectQuery.data.project_id;
      const name = projectQuery.data.name ?? id;
      items.set(id, name);
    }

    if (selectedProject && !items.has(selectedProject)) {
      items.set(selectedProject, selectedProject);
    }

    return Array.from(items.entries()).map(([id, name]) => ({ id, name }));
  }, [projectQuery.data, selectedProject]);

  const profileEmail = meQuery.data?.email ?? "";
  const profileName = profileEmail ? profileEmail.split("@")[0] : "Profile";
  const profileInitial = profileEmail ? profileEmail.charAt(0).toUpperCase() : "U";
  const profileMeta = profileEmail || "Account";

  function onLogout() {
    clearAccessToken();
    router.replace("/auth/login?logged_out=1");
    router.refresh();
  }

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <aside className={`sidebar ${sidebarOpen ? "" : "hidden lg:flex"}`}>
        <div className="brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/zroky.logo.png"
            alt="Zroky"
            className="brand-logo"
            draggable={false}
            width={110}
            height={26}
          />
          <p className="brand-tagline">Agent reliability loop</p>
        </div>

        <nav className="nav-links" aria-label="Primary">
          {dashboardLinks.map((item) => (
            <NavEntry key={item.href} pathname={pathname} item={item} />
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-project-card">
            <div className="sidebar-project-head">
              <span>Project</span>
              {sdkConnected ? <span className="sidebar-capture-pill is-live">Connected</span> : null}
            </div>
            <select
              className="sidebar-project-select mono"
              value={selectedProject ?? projectQuery.data?.project_id ?? ""}
              onChange={(event) => setSelectedProject(event.target.value || null)}
              aria-label="Project selector"
            >
              {projectOptions.length > 0 ? (
                projectOptions.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))
              ) : (
                <option value="">{projectLabel}</option>
              )}
            </select>
          </div>

          <Link href="/settings" className={navClass(pathname, "/settings")}>
            <span className="nav-link-main">
              <Settings className="nav-link-icon" aria-hidden="true" />
              <span>Settings</span>
            </span>
          </Link>

          <details className="profile-menu">
            <summary className="profile-summary">
              <span className="shell-profile-avatar" aria-hidden="true">{profileInitial}</span>
              <span className="profile-copy">
                <strong>{profileName}</strong>
                <span>{profileMeta}</span>
              </span>
              <ChevronDown className="profile-chevron" aria-hidden="true" />
            </summary>
            <div className="profile-popover">
              <div className="profile-popover-head">
                <span className="shell-profile-avatar" aria-hidden="true">{profileInitial}</span>
                <span>
                  <strong>{profileName}</strong>
                  <span>{profileMeta}</span>
                </span>
              </div>
              <Link href="/settings/profile" className="profile-menu-item">
                <User className="h-4 w-4" aria-hidden="true" />
                Profile
              </Link>
              <Link href="/settings" className="profile-menu-item">
                <Settings className="h-4 w-4" aria-hidden="true" />
                Settings
              </Link>
              <button type="button" className="profile-menu-item" onClick={onLogout}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Log out
              </button>
            </div>
          </details>
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
