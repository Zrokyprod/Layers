"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
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

type ProjectDetailState = {
  activeProject: ProjectResponse | null;
  projects: CurrentUserProjectResponse[];
};

const projectDetailLoadTimeoutMs = 15_000;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function withProjectTimeout<T>(promise: Promise<T>, detail: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => reject(new Error(detail)), projectDetailLoadTimeoutMs);
    promise.then(resolve, reject).finally(() => globalThis.clearTimeout(timeout));
  });
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

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("error") || text.includes("unavailable") || text.includes("cannot");
}

export default function ProjectDetailPage() {
  const params = useParams<{ projectId?: string }>();
  const router = useRouter();
  const routeProjectId = typeof params.projectId === "string" ? decodeURIComponent(params.projectId) : "";
  const [state, setState] = useState<ProjectDetailState>({ activeProject: null, projects: [] });
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
        withProjectTimeout(
          getProjectSettings(),
          `Backend API timed out after ${projectDetailLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
        ),
        withProjectTimeout(listMyProjects(), "Project list load timed out."),
      ]);

      if (activeResult.status === "rejected") {
        throw activeResult.reason;
      }

      const activeProject = activeResult.value;
      const projects = projectsResult.status === "fulfilled" ? projectsResult.value : [fallbackProjectRow(activeProject)];
      setState({ activeProject, projects });

      if (projectsResult.status === "rejected") {
        setProjectListError(errorMessage(projectsResult.reason, "Project list could not load."));
      }
    } catch (loadError) {
      setError(errorMessage(loadError, "Failed to load project."));
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

  const selectedProject = rows.find((project) => project.project_id === routeProjectId) ?? null;
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
      setDeleteConfirm("");
      setStatusMessage("Project deleted.");
      router.replace(nextProject ? `/projects/${encodeURIComponent(nextProject.project_id)}` : "/projects");
      await load();
    } catch (deleteError) {
      setStatusMessage(errorMessage(deleteError, "Failed to delete project."));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page-content settings-project-page projects-page">
      <Link href="/projects" className="projects-back-link">
        <ArrowLeft aria-hidden="true" />
        Projects
      </Link>

      {error ? (
        <section className="panel settings-error-panel">
          <header className="panel-header">
            <div>
              <h3>Project could not load</h3>
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

      {projectListError ? (
        <div className="settings-project-warning" role="status">
          <AlertTriangle aria-hidden="true" />
          <span>{projectListError}</span>
        </div>
      ) : null}

      {loading ? (
        <section className="panel settings-project-skeleton" aria-label="Loading project">
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
        <section className="settings-project-console projects-detail-console" aria-label="Project details">
          {selectedProject ? (
            <>
              <div className="settings-project-command">
                <div className="settings-project-toolbar">
                  <div>
                    <h2>{safeString(selectedProject.project_name, "Untitled project")}</h2>
                    <p>Manage this project context, active selection, and deletion controls.</p>
                  </div>
                  <StatusPill value={selectedIsActive ? "active" : "verified"} />
                </div>
              </div>

              <div className="settings-project-registry projects-detail-grid">
                <div className="settings-project-details-panel projects-detail-main" aria-label="Project facts">
                  <header>
                    <div>
                      <span>Project context</span>
                      <h3>{selectedIsActive ? "Currently active" : "Available"}</h3>
                    </div>
                    <span className={selectedIsActive ? "settings-project-state is-active" : "settings-project-state"}>
                      {selectedIsActive ? <CheckCircle2 aria-hidden="true" /> : <CircleDot aria-hidden="true" />}
                      {selectedIsActive ? "Active" : "Not active"}
                    </span>
                  </header>

                  <div className="settings-project-context">
                    <div>
                      <span>Last update</span>
                      <strong>{selectedProjectUpdated}</strong>
                    </div>
                    <div>
                      <span>Role</span>
                      <strong>{formatRoleLabel(selectedProject.role)}</strong>
                    </div>
                  </div>

                  <dl className="settings-project-details-list">
                    <div>
                      <dt>Project ID</dt>
                      <dd className="mono">{selectedProject.project_id}</dd>
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
                </div>

                <aside className="settings-project-details-panel" aria-label="Danger zone">
                  <div className="settings-project-delete">
                    <div>
                      <strong>Delete project</strong>
                      <p>
                        Removes this project from the active project list and disables capture keys. Existing evidence stays available for audit.
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
                </aside>
              </div>
            </>
          ) : (
            <div className="settings-project-empty projects-not-found" role="status">
              <FolderOpen aria-hidden="true" />
              <strong>Project not found</strong>
              <span>This account does not have active access to {compactIdentifier(routeProjectId)}.</span>
              <Link href="/projects" className="btn btn-soft">
                View projects
              </Link>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
