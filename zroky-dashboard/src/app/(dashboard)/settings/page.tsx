"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  FolderOpen,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { deleteProject, getProjectSettings, listMyProjects } from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type { CurrentUserProjectResponse, ProjectResponse } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type SettingsState = {
  activeProject: ProjectResponse | null;
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
  return text.includes("failed") || text.includes("error") || text.includes("unavailable") || text.includes("cannot");
}

function compactIdentifier(value: string | null | undefined, lead = 10, tail = 6): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}...${normalized.slice(-tail)}`;
}

function formatOwnerRef(ownerRef: string | null): string {
  const raw = ownerRef?.trim();
  if (!raw) return "Current account";

  const separatorIndex = raw.indexOf(":");
  if (separatorIndex === -1) return compactIdentifier(raw, 8, 5);

  const provider = raw.slice(0, separatorIndex).toLowerCase();
  const subject = raw.slice(separatorIndex + 1);
  if (provider === "email") return subject || "Email account";
  if (provider === "google") return "Google account";
  if (provider === "github") return "GitHub account";
  return compactIdentifier(subject || raw, 8, 5);
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

function fallbackProjectRow(project: ProjectResponse): CurrentUserProjectResponse {
  return {
    membership_id: project.project_id,
    project_id: project.project_id,
    project_name: project.name,
    role: "owner",
    is_active: project.is_active,
    created_at: project.created_at,
    updated_at: project.updated_at,
  };
}

export default function SettingsPage() {
  const [state, setState] = useState<SettingsState>({ activeProject: null, projects: [] });
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectListError, setProjectListError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const setActiveProject = useDashboardStore((store) => store.setSelectedProject);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProjectListError(null);

    try {
      const [activeResult, projectsResult] = await Promise.allSettled([
        withSettingsTimeout(
          getProjectSettings(),
          `Backend API timed out after ${settingsLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
        ),
        withSettingsTimeout(listMyProjects(), "Project list load timed out."),
      ]);

      if (activeResult.status === "rejected") {
        throw activeResult.reason;
      }

      const activeProject = activeResult.value;
      const projects = projectsResult.status === "fulfilled" ? projectsResult.value : [fallbackProjectRow(activeProject)];
      setState({ activeProject, projects });
      setSelectedProjectId((current) =>
        current && projects.some((project) => project.project_id === current)
          ? current
          : null,
      );

      if (projectsResult.status === "rejected") {
        setProjectListError(errorMessage(projectsResult.reason, "Project list could not load."));
      }
    } catch (loadError) {
      setError(errorMessage(loadError, "Failed to load projects."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => {
    if (state.projects.length > 0) return state.projects;
    return state.activeProject ? [fallbackProjectRow(state.activeProject)] : [];
  }, [state.activeProject, state.projects]);

  const selectedProject = selectedProjectId
    ? rows.find((project) => project.project_id === selectedProjectId) ?? null
    : null;
  const activeProjectId = state.activeProject?.project_id ?? null;
  const selectedIsActive = Boolean(selectedProject && selectedProject.project_id === activeProjectId);
  const selectedRole = selectedProject?.role?.trim().toLowerCase() ?? "";
  const selectedProjectUpdated = selectedProject ? formatDateTime(selectedProject.updated_at) : "Unavailable";
  const canDeleteSelected = Boolean(
    selectedProject &&
      rows.length > 1 &&
      selectedRole === "owner" &&
      deleteConfirm.trim() === selectedProject.project_name,
  );
  const deleteDisabledReason =
    !selectedProject
      ? "Select a project first."
      : rows.length <= 1
        ? "You need another active project before deleting this one."
        : selectedRole !== "owner"
          ? "Only a project owner can delete this project."
          : "Type the project name exactly to enable delete.";

  function onSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    setDeleteConfirm("");
  }

  function onMakeActive(projectId: string) {
    if (projectId === activeProjectId) return;
    setStatusMessage("Active project changed.");
    setActiveProject(projectId);
    window.setTimeout(() => void load(), 0);
  }

  async function onDeleteSelectedProject() {
    if (!selectedProject || !canDeleteSelected) {
      setStatusMessage(deleteDisabledReason);
      return;
    }

    setStatusMessage("");
    setDeleting(true);
    try {
      await deleteProject(
        selectedProject.project_id,
        { confirm_project_name: selectedProject.project_name },
        selectedProject.project_id,
      );
      const remaining = rows.filter((project) => project.project_id !== selectedProject.project_id);
      const nextProject = remaining.find((project) => project.project_id === activeProjectId) ?? remaining[0] ?? null;
      if (selectedProject.project_id === activeProjectId) {
        setActiveProject(nextProject?.project_id ?? null);
      }
      setSelectedProjectId(nextProject?.project_id ?? null);
      setDeleteConfirm("");
      setStatusMessage("Project deleted.");
      await load();
    } catch (deleteError) {
      setStatusMessage(errorMessage(deleteError, "Failed to delete project."));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page-content settings-project-page">
      {error ? (
        <section className="panel settings-error-panel">
          <header className="panel-header">
            <div>
              <h3>Projects could not load</h3>
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
        <section className="panel settings-project-skeleton" aria-label="Loading projects">
          <div>
            <span />
            <span />
            <span />
          </div>
          <div>
            <span />
            <span />
            <span />
          </div>
          <div>
            <span />
            <span />
            <span />
          </div>
        </section>
      ) : null}

      {!loading && !error ? (
        <section className="settings-project-console" aria-label="Project registry">
          <div className="settings-project-command">
            <div className="settings-project-toolbar">
              <div>
                <h2>Projects</h2>
                <p>Manage the exact project context used for capture, replay, goldens, and CI gates.</p>
              </div>
              <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
                <RefreshCw aria-hidden="true" />
                Refresh
              </button>
            </div>

            {projectListError ? (
              <div className="settings-project-warning" role="status">
                <AlertTriangle aria-hidden="true" />
                <span>{projectListError}</span>
              </div>
            ) : null}
          </div>

          <div className="settings-project-registry">
            <div className="settings-project-list-panel">
              <div className="settings-project-section-head">
                <div>
                  <span>Active workspace</span>
                  <strong>Select a project</strong>
                </div>
                <small>{selectedProject ? `Selected: ${safeString(selectedProject.project_name, "Untitled project")}` : "No project selected"}</small>
              </div>

              <div className="settings-project-table" role="list" aria-label="Active projects">
                <div className="settings-project-table-head" aria-hidden="true">
                  <span>Project</span>
                  <span>Role</span>
                  <span>Status</span>
                  <span>Updated</span>
                </div>
                {rows.length > 0 ? (
                  rows.map((project) => {
                    const isSelected = project.project_id === selectedProject?.project_id;
                    const isActive = project.project_id === activeProjectId;
                    return (
                      <button
                        key={project.project_id}
                        type="button"
                        className={`settings-project-table-row${isSelected ? " is-selected" : ""}`}
                        aria-label={`View ${project.project_name}`}
                        aria-pressed={isSelected}
                        onClick={() => onSelectProject(project.project_id)}
                      >
                        <span className="settings-project-name-cell">
                          <strong>{safeString(project.project_name, "Untitled project")}</strong>
                          <small className="mono" title={project.project_id}>
                            {compactIdentifier(project.project_id)}
                          </small>
                        </span>
                        <span>{formatRoleLabel(project.role)}</span>
                        <span className={isActive ? "settings-project-state is-active" : "settings-project-state"}>
                          {isActive ? (
                            <CheckCircle2 aria-hidden="true" />
                          ) : (
                            <CircleDot aria-hidden="true" />
                          )}
                          {isActive ? "Active" : "Available"}
                        </span>
                        <span>{formatDateTime(project.updated_at)}</span>
                      </button>
                    );
                  })
                ) : (
                  <div className="settings-project-empty" role="status">
                    <FolderOpen aria-hidden="true" />
                    <strong>No active project found</strong>
                    <span>Create or join a project before capture keys and replay evidence can attach to a workspace.</span>
                  </div>
                )}
              </div>
            </div>

            <aside className="settings-project-details-panel" aria-label="Project details">
              {selectedProject ? (
                <>
                  <header>
                    <div>
                      <span>Selected project</span>
                      <h3>{safeString(selectedProject.project_name, "Untitled project")}</h3>
                    </div>
                    <StatusPill value={selectedIsActive ? "active" : "verified"} />
                  </header>

                  <div className="settings-project-context">
                    <div>
                      <span>Capture context</span>
                      <strong>{selectedIsActive ? "Currently active" : "Not active"}</strong>
                    </div>
                    <div>
                      <span>Last update</span>
                      <strong>{selectedProjectUpdated}</strong>
                    </div>
                  </div>

                  <dl className="settings-project-details-list">
                    <div>
                      <dt>Project ID</dt>
                      <dd className="mono">{selectedProject.project_id}</dd>
                    </div>
                    <div>
                      <dt>Role</dt>
                      <dd>{formatRoleLabel(selectedProject.role)}</dd>
                    </div>
                    <div>
                      <dt>Owner</dt>
                      <dd>{selectedProject.project_id === activeProjectId ? formatOwnerRef(state.activeProject?.owner_ref ?? null) : "Project member"}</dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDateTime(selectedProject.created_at)}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{formatDateTime(selectedProject.updated_at)}</dd>
                    </div>
                  </dl>

                  {!selectedIsActive ? (
                    <button
                      type="button"
                      className="btn btn-primary settings-project-active-button"
                      onClick={() => onMakeActive(selectedProject.project_id)}
                    >
                      <CheckCircle2 aria-hidden="true" />
                      Make active
                    </button>
                  ) : null}

                  <div className="settings-project-delete">
                    <div>
                      <strong>Delete project</strong>
                      <p>
                        Removes this project from the active workspace list and disables capture keys. Existing evidence stays available for audit.
                      </p>
                    </div>
                    <label htmlFor="projectDeleteConfirm">Type project name</label>
                    <input
                      id="projectDeleteConfirm"
                      value={deleteConfirm}
                      onChange={(event) => setDeleteConfirm(event.target.value)}
                      placeholder={selectedProject.project_name}
                      disabled={deleting || rows.length <= 1 || selectedRole !== "owner"}
                    />
                    {!canDeleteSelected ? <small>{deleteDisabledReason}</small> : null}
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => void onDeleteSelectedProject()}
                      disabled={deleting || !canDeleteSelected}
                    >
                      <Trash2 aria-hidden="true" />
                      {deleting ? "Deleting..." : "Delete project"}
                    </button>
                  </div>
                </>
              ) : (
                <div className="settings-project-empty" role="status">
                  <FolderOpen aria-hidden="true" />
                  <strong>No project selected</strong>
                  <span>Select a project from the active workspace list.</span>
                </div>
              )}
            </aside>
          </div>
        </section>
      ) : null}
    </div>
  );
}
