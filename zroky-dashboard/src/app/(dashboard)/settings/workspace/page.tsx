"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  Activity,
  CalendarClock,
  Check,
  Copy,
  Database,
  FolderOpen,
  KeyRound,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  SettingsHero,
  SettingsMetricStrip,
  SettingsScaffold,
  SettingsSection,
} from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import { useMyProjects, useProjectSettings, useUpdateProjectSettings } from "@/lib/hooks";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";

function roleLabel(value: string | null | undefined): string {
  const normalized = value?.trim();
  if (!normalized) return "Member";
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function compactIdentifier(value: string | null | undefined): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= 22) return normalized;
  return `${normalized.slice(0, 12)}...${normalized.slice(-6)}`;
}

function canRenameWorkspace(role: string | null | undefined): boolean {
  const normalized = role?.toLowerCase();
  return normalized === "owner" || normalized === "admin";
}

function authorityCopy(role: string | null | undefined): string {
  const normalized = role?.toLowerCase();
  if (normalized === "owner") return "Full workspace authority, member access, billing, and policy changes.";
  if (normalized === "admin") return "Operational authority for workspace setup and most project controls.";
  if (normalized === "viewer") return "Read-only visibility into workspace state and evidence.";
  return "Project operator access without owner-level controls.";
}

export default function WorkspaceSettingsPage() {
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const projectQuery = useProjectSettings();
  const projectsQuery = useMyProjects();
  const updateProject = useUpdateProjectSettings();
  const [copied, setCopied] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  const project = projectQuery.data ?? null;
  const memberships = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const projectId = project?.project_id ?? selectedProject;
  const membership = useMemo(
    () => memberships.find((item) => item.project_id === projectId) ?? null,
    [memberships, projectId],
  );
  const workspaceName = safeString(project?.name ?? membership?.project_name, "Project unavailable");
  const loading = projectQuery.isLoading || projectsQuery.isLoading;
  const active = project?.is_active === false || membership?.is_active === false ? false : true;
  const role = roleLabel(membership?.role);
  const renameAllowed = canRenameWorkspace(membership?.role);
  const renameDisabled = !renameAllowed || !projectId || updateProject.isPending || draftName.trim().length < 2;
  const dashboardEnvironment = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  const projectTimestamp = formatDateTime(project?.updated_at ?? membership?.updated_at);

  useEffect(() => {
    setDraftName(workspaceName === "Project unavailable" ? "" : workspaceName);
  }, [workspaceName]);

  async function copyProjectId() {
    if (!projectId) return;
    try {
      await navigator.clipboard.writeText(projectId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  async function onRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = draftName.trim();
    if (renameDisabled || name === workspaceName) return;
    setStatusMessage("");
    try {
      await updateProject.mutateAsync({ name });
      setStatusMessage("Workspace name updated.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Workspace rename failed.");
    }
  }

  return (
    <SettingsScaffold className="workspace-settings-page" aria-labelledby="workspace-settings-title">
      <SettingsHero
        ariaLabel="Workspace settings"
        eyebrow="Workspace"
        icon={<FolderOpen aria-hidden="true" />}
        title={workspaceName}
        copy="Project identity, role context, and the stable ID used by SDK keys, billing, receipts, and audit links."
        tone={active ? "success" : "danger"}
        pill={active ? "Active" : "Inactive"}
        updatedLabel={loading ? "Loading" : "Settings live"}
        actions={
          <>
            <DashboardButtonLink href="/projects" variant="soft">
              Open projects
            </DashboardButtonLink>
            <DashboardButtonLink href="/settings/team" variant="primary">
              Manage members
            </DashboardButtonLink>
          </>
        }
      />

      <SettingsMetricStrip
        ariaLabel="Workspace settings summary"
        metrics={[
          {
            id: "workspace",
            label: "Workspace",
            value: workspaceName,
            helper: "Stable dashboard project context",
            tone: active ? "success" : "danger",
            icon: <FolderOpen aria-hidden="true" />,
          },
          {
            id: "status",
            label: "Status",
            value: active ? "Active" : "Inactive",
            helper: "Used by SDK keys, billing, and member access",
            tone: active ? "success" : "danger",
            icon: <ShieldCheck aria-hidden="true" />,
          },
          {
            id: "role",
            label: "Your role",
            value: role,
            helper: membership ? "Role comes from project membership" : "Membership details are not loaded",
            tone: renameAllowed ? "success" : "neutral",
            icon: <UserRound aria-hidden="true" />,
          },
          {
            id: "updated",
            label: "Updated",
            value: projectTimestamp,
            helper: "Latest project metadata timestamp",
            tone: "setup",
            icon: <RefreshCw aria-hidden="true" />,
          },
        ]}
      />

      <section className="workspace-command-card" aria-label="Workspace access boundary">
        <div className="workspace-command-main">
          <span className="workspace-command-kicker">
            <LockKeyhole aria-hidden="true" />
            Workspace boundary
          </span>
          <h2>One project identity governs agents, members, keys, billing, and evidence.</h2>
          <p>
            This is the stable control context Zroky uses when a protected action is proposed, approved, verified, and signed.
          </p>
          <div className="workspace-command-rail" aria-label="Workspace routing controls">
            <span>
              <KeyRound aria-hidden="true" />
              SDK keys resolve here
            </span>
            <span>
              <UserRound aria-hidden="true" />
              Member role gates controls
            </span>
            <span>
              <Database aria-hidden="true" />
              Receipts keep this project ID
            </span>
          </div>
        </div>

        <aside className="workspace-routing-card" aria-label="Workspace routing">
          <div className="workspace-routing-head">
            <span>Routing state</span>
            <StatusPill
              value={active ? "active" : "inactive"}
              label={active ? "Active" : "Inactive"}
              tone={active ? "success" : "danger"}
            />
          </div>
          <div className="workspace-routing-list">
            <div>
              <Activity aria-hidden="true" />
              <span>
                <small>Environment</small>
                <strong>{roleLabel(dashboardEnvironment)}</strong>
              </span>
            </div>
            <div>
              <ShieldCheck aria-hidden="true" />
              <span>
                <small>Your authority</small>
                <strong>{role}</strong>
              </span>
            </div>
            <div>
              <CalendarClock aria-hidden="true" />
              <span>
                <small>Last metadata update</small>
                <strong>{projectTimestamp}</strong>
              </span>
            </div>
          </div>
        </aside>
      </section>

      <SettingsSection
        id="workspace-identity"
        eyebrow="Identity"
        title="Workspace identity"
        copy="Rename the workspace shown across the dashboard. Project IDs stay stable for API keys, receipts, and audit links."
        actions={
          <StatusPill
            value={renameAllowed ? "editable" : "read_only"}
            label={renameAllowed ? "Editable" : "Read only"}
            tone={renameAllowed ? "success" : "neutral"}
          />
        }
      >
        <div className="workspace-identity-grid">
          <form onSubmit={onRename} className="settings-workspace-form">
            <div className="field">
              <label htmlFor="workspace-name" className="field-label">
                Workspace name
              </label>
              <input
                id="workspace-name"
                type="text"
                className="input"
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                disabled={!renameAllowed}
                minLength={2}
                maxLength={120}
              />
              <span className="field-hint">
                {renameAllowed
                  ? "Owners and admins can rename this workspace."
                  : "Only owners and admins can rename this workspace."}
              </span>
            </div>
            <DashboardButton type="submit" variant="primary" loading={updateProject.isPending} disabled={renameDisabled || draftName.trim() === workspaceName}>
              Save workspace name
            </DashboardButton>
          </form>

          <div className="workspace-authority-card" aria-label="Workspace authority">
            <span className="workspace-authority-icon">
              <ShieldCheck aria-hidden="true" />
            </span>
            <div>
              <span>Your role</span>
              <strong>{role}</strong>
              <p>{authorityCopy(membership?.role)}</p>
            </div>
          </div>
        </div>
        {statusMessage ? (
          <p className={statusMessage.toLowerCase().includes("failed") ? "field-error" : "field-success"}>
            {statusMessage}
          </p>
        ) : null}

        <div className="workspace-fact-list">
          <div className="list-row">
            <div className="list-main">
              <strong>Project ID</strong>
              <span className="mono">{compactIdentifier(projectId)}</span>
            </div>
            <DashboardButton type="button" size="sm" variant="soft" icon={copied ? <Check /> : <Copy />} onClick={() => void copyProjectId()} disabled={!projectId}>
              {copied ? "Copied" : "Copy project ID"}
            </DashboardButton>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Owner reference</strong>
              <span className="mono">{compactIdentifier(project?.owner_ref)}</span>
            </div>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Dashboard environment</strong>
              <span>{roleLabel(dashboardEnvironment)}</span>
            </div>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Created</strong>
              <span>{formatDateTime(project?.created_at ?? membership?.created_at)}</span>
            </div>
          </div>
        </div>
      </SettingsSection>

    </SettingsScaffold>
  );
}
