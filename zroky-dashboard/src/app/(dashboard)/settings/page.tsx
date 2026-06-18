"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CreditCard,
  Database,
  Download,
  FolderKanban,
  KeyRound,
  Plug,
  RefreshCw,
  Users,
} from "lucide-react";

import { exportProjectData, getProjectSettings, listMyProjects } from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type { CurrentUserProjectResponse, ProjectResponse } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type SettingsState = {
  project: ProjectResponse | null;
  projects: CurrentUserProjectResponse[];
};

const settingsLoadTimeoutMs = 15_000;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function withSettingsTimeout<T>(promise: Promise<T>, detail: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => reject(new Error(detail)), settingsLoadTimeoutMs);
    promise.then(resolve, reject).finally(() => globalThis.clearTimeout(timeout));
  });
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("error") || text.includes("unavailable");
}

function compactIdentifier(value: string | null | undefined, lead = 12, tail = 6): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}...${normalized.slice(-tail)}`;
}

function formatOwnerRef(ownerRef: string | null): { label: string; detail: string | null; raw: string | null } {
  const raw = ownerRef?.trim() || null;
  if (!raw) return { label: "Current account", detail: null, raw };

  const separatorIndex = raw.indexOf(":");
  if (separatorIndex === -1) {
    return { label: "Project owner", detail: compactIdentifier(raw, 8, 5), raw };
  }

  const provider = raw.slice(0, separatorIndex).toLowerCase();
  const subject = raw.slice(separatorIndex + 1);

  if (provider === "email") {
    return { label: subject || "Email account", detail: "Email owner", raw };
  }

  const providerLabel =
    provider === "google" ? "Google account" : provider === "github" ? "GitHub account" : "Project owner";
  return { label: providerLabel, detail: compactIdentifier(subject || raw, 8, 5), raw };
}

function formatRoleLabel(role: string | null | undefined): string {
  const normalized = role?.trim();
  if (!normalized) return "Member";
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function projectRows(project: ProjectResponse | null, projects: CurrentUserProjectResponse[]) {
  if (projects.length > 0) return projects;
  if (!project) return [];
  return [
    {
      membership_id: project.project_id,
      project_id: project.project_id,
      project_name: project.name,
      role: "owner",
      is_active: project.is_active,
      created_at: project.created_at,
      updated_at: project.updated_at,
    },
  ];
}

export default function SettingsPage() {
  const [state, setState] = useState<SettingsState>({ project: null, projects: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectListError, setProjectListError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [exporting, setExporting] = useState(false);
  const setSelectedProject = useDashboardStore((store) => store.setSelectedProject);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProjectListError(null);

    try {
      const [projectResult, projectsResult] = await Promise.allSettled([
        withSettingsTimeout(
          getProjectSettings(),
          `Backend API timed out after ${settingsLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
        ),
        withSettingsTimeout(listMyProjects(), "Project directory load timed out."),
      ]);

      if (projectResult.status === "rejected") {
        throw projectResult.reason;
      }

      setState({
        project: projectResult.value,
        projects: projectsResult.status === "fulfilled" ? projectsResult.value : [],
      });

      if (projectsResult.status === "rejected") {
        setProjectListError(errorMessage(projectsResult.reason, "Project directory could not load."));
      }
    } catch (loadError) {
      setError(errorMessage(loadError, "Failed to load project settings."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onExportData() {
    setStatusMessage("");
    try {
      setExporting(true);
      const payload = await exportProjectData({ limit: 500, include_payload: true });
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      link.href = downloadUrl;
      link.download = `zroky-export-${payload.tenant_id}-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
      setStatusMessage(`Export downloaded: ${payload.call_count} calls, ${payload.diagnosis_count} diagnoses, ${payload.alert_count} alerts.`);
    } catch (exportError) {
      setStatusMessage(errorMessage(exportError, "Failed to export project data."));
    } finally {
      setExporting(false);
    }
  }

  function onSwitchProject(projectId: string) {
    if (projectId === state.project?.project_id) return;
    setStatusMessage("Project switched. Refreshing settings.");
    setSelectedProject(projectId);
    window.setTimeout(() => {
      void load();
    }, 0);
  }

  const project = state.project;
  const rows = projectRows(project, state.projects);
  const ownerDisplay = project ? formatOwnerRef(project.owner_ref) : null;
  const projectIdLabel = project ? compactIdentifier(project.project_id) : "Unavailable";
  const currentMembership = project
    ? rows.find((row) => row.project_id === project.project_id) ?? null
    : null;

  return (
    <div className="page-content settings-project-page">
      {error ? (
        <section className="panel settings-error-panel">
          <header className="panel-header">
            <div>
              <h3>Settings could not load</h3>
              <p>{error}</p>
            </div>
            <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
              <RefreshCw aria-hidden="true" />
              Retry
            </button>
          </header>
        </section>
      ) : null}

      {statusMessage ? (
        <div className={isProblemMessage(statusMessage) ? "alert-strip alert-strip-error" : "alert-strip"}>
          {statusMessage}
        </div>
      ) : null}

      {loading ? (
        <section className="panel settings-project-skeleton" aria-label="Loading project settings">
          <div className="loading" />
        </section>
      ) : null}

      {!loading && project ? (
        <>
          <section className="panel settings-project-cockpit" aria-labelledby="settings-project-title">
            <div className="settings-project-cockpit-header">
              <div>
                <span className="settings-section-kicker">
                  <Database aria-hidden="true" />
                  Project
                </span>
                <h2 id="settings-project-title">{safeString(project.name, "My Project")}</h2>
                <p>Workspace identity, capture scope, access, and billing stay tied to the selected project.</p>
              </div>
              <div className="settings-project-cockpit-status">
                <StatusPill value={project.is_active ? "active" : "inactive"} />
                <small>{rows.length === 1 ? "1 project available" : `${rows.length} projects available`}</small>
              </div>
            </div>

            <div className="settings-project-facts" aria-label="Current project facts">
              <div className="settings-project-fact">
                <span>Project ID</span>
                <strong className="mono" title={project.project_id}>
                  {projectIdLabel}
                </strong>
                <small>Capture scope</small>
              </div>
              <div className="settings-project-fact">
                <span>Your role</span>
                <strong>{formatRoleLabel(currentMembership?.role ?? "owner")}</strong>
                <small>Access level</small>
              </div>
              <div className="settings-project-fact">
                <span>Owner</span>
                <strong title={ownerDisplay?.raw ?? undefined}>{ownerDisplay?.label ?? "Current account"}</strong>
                {ownerDisplay?.detail ? <small>{ownerDisplay.detail}</small> : <small>Project owner</small>}
              </div>
              <div className="settings-project-fact">
                <span>Updated</span>
                <strong>{formatDateTime(project.updated_at)}</strong>
                <small>Latest metadata</small>
              </div>
            </div>
          </section>

          <section className="panel settings-project-directory" aria-labelledby="settings-project-directory-title">
            <header className="panel-header">
              <div>
                <h3 id="settings-project-directory-title">
                  <FolderKanban aria-hidden="true" />
                  Project directory
                </h3>
                <p>Use this list when your account has multiple projects. Switching updates the active dashboard scope.</p>
              </div>
              <span className="pill">{rows.length === 1 ? "Single project" : `${rows.length} projects`}</span>
            </header>

            {projectListError ? (
              <div className="alert-strip alert-strip-error">{projectListError}</div>
            ) : null}

            <div className="settings-project-list" role="list">
              {rows.map((row) => {
                const isCurrent = row.project_id === project.project_id;
                return (
                  <div key={row.membership_id || row.project_id} className="settings-project-row" role="listitem">
                    <div className="settings-project-row-main">
                      <strong>{safeString(row.project_name, "Untitled project")}</strong>
                      <span className="mono" title={row.project_id}>
                        {compactIdentifier(row.project_id)}
                      </span>
                    </div>
                    <div className="settings-project-row-meta">
                      <span>{formatRoleLabel(row.role)}</span>
                      <span>Created {formatDateTime(row.created_at)}</span>
                      <span>Updated {formatDateTime(row.updated_at)}</span>
                    </div>
                    <div className="settings-project-row-action">
                      {isCurrent ? (
                        <StatusPill value="active" />
                      ) : (
                        <button type="button" className="btn btn-soft" onClick={() => onSwitchProject(row.project_id)}>
                          Switch
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="settings-project-action-grid" aria-label="Project setup actions">
            <Link href="/settings/keys" className="settings-workspace-card">
              <KeyRound aria-hidden="true" />
              <span>
                <strong>Project key</strong>
                <small>Create or rotate capture credentials.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </Link>
            <Link href="/settings/providers" className="settings-workspace-card">
              <Plug aria-hidden="true" />
              <span>
                <strong>Provider keys</strong>
                <small>Add only when replay needs live model calls.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </Link>
            <Link href="/settings/team" className="settings-workspace-card">
              <Users aria-hidden="true" />
              <span>
                <strong>Members</strong>
                <small>Invite teammates and manage roles.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </Link>
            <Link href="/settings/billing" className="settings-workspace-card">
              <CreditCard aria-hidden="true" />
              <span>
                <strong>Plan & usage</strong>
                <small>Review limits, budget, and upgrade state.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </Link>
          </section>

          <section className="panel settings-control-panel settings-project-utility-panel">
            <header className="panel-header">
              <div>
                <h3>Project export</h3>
                <p>Download a scoped JSON export for support, migration, or offline audit.</p>
              </div>
              <button type="button" className="btn btn-soft" onClick={() => void onExportData()} disabled={exporting}>
                <Download aria-hidden="true" />
                {exporting ? "Preparing..." : "Download JSON"}
              </button>
            </header>
          </section>
        </>
      ) : null}
    </div>
  );
}
