"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";

import { clearAccessToken, readEmailVerifiedFromBrowser } from "@/lib/auth";
import { resendVerification } from "@/lib/api";
import { useDashboardStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/keyboard-shortcuts";
import { useOwnerProjects, useProjectSettings } from "@/lib/hooks";
import { ThemeToggle } from "./theme-toggle";
import { NotificationBell } from "./notification-bell";
import { CommandPalette } from "./command-palette";
import { ShortcutsHelp } from "./shortcuts-help";
import { AiAssistant } from "./ai-assistant";

const dashboardLinks = [
  { href: "/home", label: "Home" },
  { href: "/calls", label: "Calls" },
  { href: "/fixes", label: "Fixes" },
  { href: "/cost", label: "Cost" },
  { href: "/loops", label: "Loops" },
  { href: "/auth-health", label: "Auth Health" },
  { href: "/trace", label: "Traces" },
  { href: "/alerts", label: "Alerts" },
  { href: "/settings", label: "Settings" },
  { href: "/notifications", label: "Notifications" },
  { href: "/account", label: "Account" },
] as const;

function getTitle(pathname: string): string {
  if (pathname.startsWith("/calls/")) {
    return "Call Detail";
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
    return "Command center for health, activity, and fast fixes.";
  }
  if (pathname.startsWith("/calls")) {
    return "Trace and fix failed calls in context.";
  }
  if (pathname === "/fixes") {
    return "Fix health, trust, adoption, and action queue.";
  }
  if (pathname === "/cost") {
    return "Spend trust, model mix, and budget controls.";
  }
  if (pathname === "/loops") {
    return "Agent loop incidents, waste estimate, and pattern breakdown.";
  }
  if (pathname === "/auth-health") {
    return "Auth failure trend, MTTA, provider breakdown, and incident triage.";
  }
  if (pathname === "/trace") {
    return "Provider-agnostic multi-agent trace tree — which agent did what, in order, with costs and failures.";
  }
  if (pathname === "/alerts") {
    return "Priority incidents with lifecycle actions.";
  }
  if (pathname === "/settings") {
    return "Project, policies, providers, and notifications.";
  }
  if (pathname === "/settings/keys") {
    return "Create and revoke API keys for this project.";
  }
  if (pathname === "/settings/providers") {
    return "Upstream AI provider connectivity and call tracking.";
  }
  if (pathname === "/settings/billing") {
    return "Plan, spend limits, and invoice history.";
  }
  if (pathname === "/settings/profile") {
    return "Your identity, password, security, and account deletion.";
  }
  if (pathname === "/settings/team") {
    return "Invite, manage, and remove project members.";
  }
  if (pathname === "/account") {
    return "Your profile, password, and login methods.";
  }
  if (pathname === "/notifications") {
    return "Activity alerts and system messages.";
  }
  return "Operational view";
}

function navClass(pathname: string, href: string): string {
  const isActive = pathname === href || pathname.startsWith(`${href}/`);
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

function useEmailVerifiedStatus(): boolean | null {
  const [verified, setVerified] = useState<boolean | null>(null);
  useEffect(() => {
    setVerified(readEmailVerifiedFromBrowser());
  }, []);
  return verified;
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

  const emailVerified = useEmailVerifiedStatus();
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "done">("idle");

  const handleResendBanner = async () => {
    setResendState("sending");
    try {
      await resendVerification();
      setResendState("done");
    } catch {
      setResendState("idle");
    }
  };

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
            <Link key={item.href} href={item.href} className={navClass(pathname, item.href)}>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-actions">
            <ThemeToggle />
          </div>
          <Link href="/onboarding" className={navClass(pathname, "/onboarding")}>
            <span>Onboarding</span>
          </Link>
          <button type="button" className="nav-link nav-link-button" onClick={onLogout}>
            <span>Logout</span>
          </button>
          <span className="pill">V1 Scope Locked</span>
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
            <NotificationBell />
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
            <Link key={item.href} href={item.href} className={navClass(pathname, item.href)}>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        {emailVerified === false && !bannerDismissed && (
          <div style={{
            background: "#fffbeb",
            borderBottom: "1px solid #fcd34d",
            padding: "10px 20px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            flexWrap: "wrap",
            fontSize: "0.84rem",
            color: "#92400e",
          }}>
            <span>⚠️ <strong>Email not verified.</strong> Check your inbox and click the verification link to secure your account.</span>
            <button
              onClick={handleResendBanner}
              disabled={resendState !== "idle"}
              style={{ fontSize: "0.82rem", fontWeight: 600, color: "#b45309", background: "none", border: "1px solid #fbbf24", borderRadius: "4px", padding: "2px 10px", cursor: "pointer" }}
            >
              {resendState === "sending" ? "Sending…" : resendState === "done" ? "Sent ✓" : "Resend email"}
            </button>
            <button
              onClick={() => setBannerDismissed(true)}
              style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "#b45309", fontWeight: 700 }}
              aria-label="Dismiss"
            >✕</button>
          </div>
        )}
        <main className="content-inner page-enter">{children}</main>
      </section>
      <CommandPalette />
      <ShortcutsHelp />
      <AiAssistant />
    </div>
  );
}
