"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  Check,
  Copy,
  FolderOpen,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { SettingsHero, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
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
  const createdTimestamp = formatDateTime(project?.created_at ?? membership?.created_at);

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
        title="Workspace"
        copy="Manage the project name and stable workspace identifiers used across Zroky."
        tone={active ? "success" : "danger"}
        pill={active ? "Active" : "Inactive"}
        updatedLabel={loading ? "Loading" : "Settings live"}
      />

      <SettingsSection
        id="workspace-identity"
        eyebrow="Identity"
        title="Workspace details"
        copy="Rename the workspace shown across the dashboard. Project IDs remain stable for keys, receipts, and audit links."
        actions={
          <StatusPill
            value={renameAllowed ? "editable" : "read_only"}
            label={renameAllowed ? "Editable" : "Read only"}
            tone={renameAllowed ? "success" : "neutral"}
          />
        }
      >
        <div className="workspace-simple-grid">
          <article className="workspace-name-card">
            <div className="workspace-card-head">
              <span>Workspace name</span>
              <StatusPill
                value={active ? "active" : "inactive"}
                label={active ? "Active" : "Inactive"}
                tone={active ? "success" : "danger"}
              />
            </div>
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
                  {renameAllowed ? "Owners and admins can rename this workspace." : "Only owners and admins can rename this workspace."}
                </span>
              </div>
              <DashboardButton
                type="submit"
                variant="primary"
                loading={updateProject.isPending}
                disabled={renameDisabled || draftName.trim() === workspaceName}
              >
                Save name
              </DashboardButton>
            </form>
            {statusMessage ? (
              <p className={statusMessage.toLowerCase().includes("failed") ? "field-error" : "field-success"}>
                {statusMessage}
              </p>
            ) : null}
          </article>

          <article className="workspace-details-card" aria-label="Workspace details">
            <div className="workspace-card-head">
              <span>Project details</span>
              <ShieldCheck aria-hidden="true" />
            </div>
            <div className="workspace-fact-list">
              <div>
                <span>Project ID</span>
                <strong className="mono">{compactIdentifier(projectId)}</strong>
                <DashboardButton
                  type="button"
                  size="sm"
                  variant="soft"
                  icon={copied ? <Check /> : <Copy />}
                  onClick={() => void copyProjectId()}
                  disabled={!projectId}
                >
                  {copied ? "Copied" : "Copy"}
                </DashboardButton>
              </div>
              <div>
                <span>Your role</span>
                <strong>{role}</strong>
              </div>
              <div>
                <span>Environment</span>
                <strong>{roleLabel(dashboardEnvironment)}</strong>
              </div>
              <div>
                <span>Created</span>
                <strong>{createdTimestamp}</strong>
              </div>
              <div>
                <span>Updated</span>
                <strong>{projectTimestamp}</strong>
              </div>
            </div>
          </article>
        </div>
      </SettingsSection>

    </SettingsScaffold>
  );
}
