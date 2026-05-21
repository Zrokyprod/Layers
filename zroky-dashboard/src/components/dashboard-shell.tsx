"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Bell,
  Coins,
  Database,
  DollarSign,
  GitBranch,
  Home,
  LogOut,
  Menu,
  Network,
  PhoneCall,
  Radio,
  Rocket,
  RotateCcw,
  Scale,
  Settings,
  ShieldCheck,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";

import { clearAccessToken } from "@/lib/auth";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useOwnerProjects, useProjectSettings } from "@/lib/hooks";
import { ThemeToggle } from "./theme-toggle";
import { CommandPalette } from "./command-palette";
import { NotificationBell } from "./notification-bell";
import { ShortcutsHelp } from "./shortcuts-help";
import { SavedYouBadge } from "./saved-you-badge";

// Nav layout per ZROKY-TECHNICAL-PLAN-V2.md §10.3.
// Pilot-section items will gain <PlanGate> wrapping in Module 8.
type NavItem = { href: string; label: string; section: "watch" | "pilot" | "settings"; icon: LucideIcon; pilotPlaceholder?: boolean };
const dashboardLinks: ReadonlyArray<NavItem> = [
  // Watch (free)
  { href: "/home", label: "Home", section: "watch", icon: Home },
  { href: "/live", label: "Live", section: "watch", icon: Radio, pilotPlaceholder: true },
  { href: "/calls", label: "Calls", section: "watch", icon: PhoneCall },
  { href: "/trace", label: "Traces", section: "watch", icon: Network },
  { href: "/issues", label: "Anomalies", section: "watch", icon: AlertTriangle },
  { href: "/cost", label: "Cost Explorer", section: "watch", icon: DollarSign },
  // Pilot (paid) — pages ship in M3..M7. Until then these resolve to a coming-soon placeholder.
  { href: "/pilot", label: "Pilot", section: "pilot", icon: Rocket, pilotPlaceholder: true },
  { href: "/goldens", label: "Goldens", section: "pilot", icon: Database, pilotPlaceholder: true },
  { href: "/replay", label: "Replay Runs", section: "pilot", icon: RotateCcw },
  { href: "/judge", label: "Judge Calibration", section: "pilot", icon: Scale },
  { href: "/calibration", label: "Calibration", section: "pilot", icon: BadgeCheck },
  { href: "/outcomes", label: "Cost Attribution", section: "pilot", icon: Coins },
  { href: "/root-cause", label: "Root Cause", section: "pilot", icon: GitBranch },
  { href: "/reliability", label: "Reliability", section: "pilot", icon: ShieldCheck },
  { href: "/recommendations", label: "Fix Queue", section: "pilot", icon: Wrench },
  { href: "/drift", label: "Provider Drift", section: "watch", icon: Activity },
  // Always-on auxiliaries
  { href: "/alerts", label: "Alerts", section: "watch", icon: Bell },
  { href: "/settings", label: "Settings", section: "settings", icon: Settings },
] as const;

function getTitle(pathname: string): string {
  if (pathname.startsWith("/calls/")) {
    return "Call Detail";
  }
  if (pathname.startsWith("/anomalies/")) {
    return "Anomaly Detail";
  }
  if (pathname.startsWith("/replay/")) {
    return "Replay Run";
  }
  if (pathname.startsWith("/goldens/")) {
    return "Golden Set";
  }
  if (pathname === "/judge" || pathname.startsWith("/judge/")) {
    return "Judge Calibration";
  }
  if (pathname === "/outcomes" || pathname.startsWith("/outcomes/")) {
    return "Cost Attribution";
  }
  if (pathname === "/root-cause" || pathname.startsWith("/root-cause/")) {
    return "Root-Cause Ablation";
  }
  if (pathname === "/reliability" || pathname.startsWith("/reliability/")) {
    return "Agent Reliability";
  }
  if (pathname === "/recommendations" || pathname.startsWith("/recommendations/")) {
    return "Fix Queue";
  }
  if (pathname === "/calibration" || pathname.startsWith("/calibration/")) {
    return "Calibration Score";
  }
  if (pathname === "/drift" || pathname.startsWith("/drift/")) {
    return "Provider Drift";
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
    return "Health, activity, and pilot impact at a glance.";
  }
  if (pathname === "/cost") {
    return "Spend, waste, forecast, and what-if savings — unified view.";
  }
  if (pathname === "/live") {
    return "Real-time stream of incoming calls.";
  }
  if (pathname.startsWith("/calls")) {
    return "Search and inspect captured calls.";
  }
  if (pathname === "/trace" || pathname.startsWith("/trace/")) {
    return "Multi-agent trace trees with parent/child lineage.";
  }
  if (pathname === "/anomalies" || pathname.startsWith("/anomalies/")) {
    return "Detector-driven anomalies with diagnose evidence.";
  }
  if (pathname === "/pilot") {
    return "Autopilot policy, action feed, and goldens.";
  }
  if (pathname === "/goldens" || pathname.startsWith("/goldens/")) {
    return "Production-trace canonicals used for replay.";
  }
  if (pathname === "/replay" || pathname.startsWith("/replay/")) {
    return "Replay runs against golden sets.";
  }
  if (pathname === "/judge" || pathname.startsWith("/judge/")) {
    return "LLM-as-judge accuracy scoreboard, confusion matrix, and mode control.";
  }
  if (pathname === "/outcomes" || pathname.startsWith("/outcomes/")) {
    return "Cost-of-failure attribution — every bad outcome mapped to its dollar cost.";
  }
  if (pathname === "/root-cause" || pathname.startsWith("/root-cause/")) {
    return "Statistical causal ablation — identify which axis explains each AI failure.";
  }
  if (pathname === "/reliability" || pathname.startsWith("/reliability/")) {
    return "Composite 0-100 health score per agent — fail rate, cost, determinism, trend.";
  }
  if (pathname === "/drift" || pathname.startsWith("/drift/")) {
    return "Daily benchmark results across providers — latency, quality, and cost drift.";
  }
  if (pathname === "/recommendations" || pathname.startsWith("/recommendations/")) {
    return "Ranked actionable fix items — causal axis failures, determinism spikes, cost overruns.";
  }
  if (pathname === "/calibration" || pathname.startsWith("/calibration/")) {
    return "Public judge accuracy score — per-model, per-class F1, mode status.";
  }
  if (pathname === "/digest") {
    return "Weekly impact summaries.";
  }
  if (pathname === "/alerts") {
    return "Priority incidents with lifecycle actions.";
  }
  if (pathname === "/notifications") {
    return "Account inbox for alerts, product updates, and reliability events.";
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
          {dashboardLinks.filter((i) => i.section === "watch").length > 0 && (
            <div className="nav-section-label">Watch</div>
          )}
          {dashboardLinks
            .filter((i) => i.section === "watch")
            .map((item) => (
              <NavEntry key={item.href} pathname={pathname} item={item} />
            ))}
          {dashboardLinks.filter((i) => i.section === "pilot").length > 0 && (
            <div className="nav-section-label">Pilot</div>
          )}
          {dashboardLinks
            .filter((i) => i.section === "pilot")
            .map((item) => (
              <NavEntry key={item.href} pathname={pathname} item={item} />
            ))}
          {dashboardLinks
            .filter((i) => i.section === "settings")
            .map((item) => (
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
              className="cp-trigger-btn"
              onClick={() => window.dispatchEvent(new CustomEvent("open-command-palette"))}
              aria-label="Open command palette"
            >
              <span className="cp-trigger-text">Search…</span>
              <kbd className="cp-trigger-kbd">Ctrl+K</kbd>
            </button>
            <SavedYouBadge />
            <NotificationBell />
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
    </div>
  );
}
