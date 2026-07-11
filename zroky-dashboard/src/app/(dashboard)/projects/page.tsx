"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Plus,
  RefreshCw,
} from "lucide-react";

import {
  createCurrentUserProject,
  getBillingMe,
  getProjectSettings,
  listMyProjects,
} from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type { BillingMeResponse, CurrentUserProjectResponse, ProjectResponse } from "@/lib/types";

type ProjectsState = {
  activeProject: ProjectResponse | null;
  projects: CurrentUserProjectResponse[];
  billing: BillingMeResponse | null;
};

const projectsLoadTimeoutMs = 15_000;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function withProjectsTimeout<T>(promise: Promise<T>, detail: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => reject(new Error(detail)), projectsLoadTimeoutMs);
    promise.then(resolve, reject).finally(() => globalThis.clearTimeout(timeout));
  });
}

function compactIdentifier(value: string | null | undefined, lead = 10, tail = 6): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}...${normalized.slice(-tail)}`;
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

function projectLimitFromBilling(billing: BillingMeResponse | null): number | null {
  const raw = billing?.plan_template?.max_projects;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function projectLimitLabel(projectCount: number, maxProjects: number | null): string {
  if (maxProjects === -1) return `${projectCount} projects - unlimited plan`;
  if (maxProjects == null) return `${projectCount} projects`;
  return `${projectCount} / ${maxProjects} projects used`;
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("error") || text.includes("unavailable") || text.includes("cannot") || text.includes("limit");
}

export default function ProjectsPage() {
  const router = useRouter();
  const [state, setState] = useState<ProjectsState>({ activeProject: null, projects: [], billing: null });
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [projectListError, setProjectListError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const setActiveProject = useDashboardStore((store) => store.setSelectedProject);
  const selectedProject = useDashboardStore((store) => store.selectedProject);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProjectListError(null);

    try {
      const [activeResult, projectsResult, billingResult] = await Promise.allSettled([
        withProjectsTimeout(
          getProjectSettings(),
          `Backend API timed out after ${projectsLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
        ),
        withProjectsTimeout(listMyProjects(), "Project list load timed out."),
        withProjectsTimeout(getBillingMe(), "Billing plan load timed out."),
      ]);

      if (activeResult.status === "rejected") {
        throw activeResult.reason;
      }

      const activeProject = activeResult.value;
      const projects = projectsResult.status === "fulfilled" ? projectsResult.value : [fallbackProjectRow(activeProject)];
      const billing = billingResult.status === "fulfilled" ? billingResult.value : null;
      setState({ activeProject, projects, billing });

      if (projectsResult.status === "rejected") {
        setProjectListError(errorMessage(projectsResult.reason, "Project list could not load."));
      }
      if (billingResult.status === "rejected") {
        setStatusMessage(errorMessage(billingResult.reason, "Billing plan could not load."));
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

  const activeProjectId = state.activeProject?.project_id ?? selectedProject ?? null;
  const maxProjects = projectLimitFromBilling(state.billing);
  const projectLimitReached = maxProjects !== null && maxProjects !== -1 && rows.length >= maxProjects;
  const newProjectNameReady = newProjectName.trim().length >= 2;
  const canCreateProject = !loading && !creating && newProjectNameReady && !projectLimitReached;

  async function onCreateProject() {
    if (!canCreateProject) {
      setStatusMessage(
        projectLimitReached
          ? "Project limit reached for this plan. Upgrade to add more projects."
          : "Enter a project name with at least 2 characters.",
      );
      return;
    }

    setStatusMessage("");
    setCreating(true);
    try {
      const created = await createCurrentUserProject({ name: newProjectName.trim() }, activeProjectId);
      setActiveProject(created.project_id);
      setNewProjectName("");
      setStatusMessage("Project created.");
      router.push(`/projects/${encodeURIComponent(created.project_id)}`);
    } catch (createError) {
      setStatusMessage(errorMessage(createError, "Failed to create project."));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page-content settings-project-page projects-page">
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
        <section className="settings-project-console projects-console" aria-label="Project registry">
          <div className="settings-project-command">
            <div className="settings-project-toolbar">
              <div>
                <h2>Projects</h2>
                <p>Project context controls SDK keys, provider vaults, runner credentials, policies, and evidence.</p>
              </div>
              <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
                <RefreshCw aria-hidden="true" />
                Refresh
              </button>
            </div>

            <div className="projects-limit-strip">
              <span>{state.billing?.plan_code ? `${state.billing.plan_code} plan` : "Current plan"}</span>
              <strong>{projectLimitLabel(rows.length, maxProjects)}</strong>
              {projectLimitReached ? (
                <>
                  <small>Upgrade before adding another project.</small>
                  <Link href="/settings/billing" className="btn btn-soft">
                    Upgrade plan
                  </Link>
                </>
              ) : (
                <small>New projects are created with you as owner.</small>
              )}
            </div>

            <div className="projects-create-panel" aria-label="Create project">
              <label htmlFor="newProjectName">New project</label>
              <div>
                <input
                  id="newProjectName"
                  value={newProjectName}
                  onChange={(event) => setNewProjectName(event.target.value)}
                  placeholder="Refund agent"
                  disabled={creating || projectLimitReached}
                />
                <button type="button" className="btn btn-primary" onClick={() => void onCreateProject()} disabled={!canCreateProject}>
                  <Plus aria-hidden="true" />
                  {projectLimitReached ? "Limit reached" : creating ? "Creating..." : "Create project"}
                </button>
              </div>
            </div>

            {projectListError ? (
              <div className="settings-project-warning" role="status">
                <AlertTriangle aria-hidden="true" />
                <span>{projectListError}</span>
              </div>
            ) : null}
          </div>

          <div className="settings-project-list-panel projects-list-panel">
            <div className="settings-project-section-head">
              <div>
                <span>Accessible projects</span>
                <strong>{rows.length > 0 ? "Choose a project" : "No projects"}</strong>
              </div>
              <small>{rows.length > 0 ? "Open details, switch context, or delete from the detail page." : "Create or join a project to continue."}</small>
            </div>

            <div className="settings-project-table projects-table" role="list" aria-label="Projects">
              <div className="settings-project-table-head" aria-hidden="true">
                <span>Project</span>
                <span>Role</span>
                <span>Status</span>
                <span>Updated</span>
              </div>
              {rows.length > 0 ? (
                rows.map((project) => {
                  const isActive = project.project_id === activeProjectId;
                  return (
                    <Link
                      key={project.project_id}
                      href={`/projects/${encodeURIComponent(project.project_id)}`}
                      className={`settings-project-table-row projects-table-row${isActive ? " is-selected" : ""}`}
                      aria-label={`Open ${project.project_name}`}
                      onClick={() => setActiveProject(project.project_id)}
                    >
                      <span className="settings-project-name-cell">
                        <strong>{safeString(project.project_name, "Untitled project")}</strong>
                        <small className="mono" title={project.project_id}>
                          {compactIdentifier(project.project_id)}
                        </small>
                      </span>
                      <span>{formatRoleLabel(project.role)}</span>
                      <span className={isActive ? "settings-project-state is-active" : "settings-project-state"}>
                        {isActive ? <CheckCircle2 aria-hidden="true" /> : <FolderOpen aria-hidden="true" />}
                        {isActive ? "Active" : "Available"}
                      </span>
                      <span>{formatDateTime(project.updated_at)}</span>
                    </Link>
                  );
                })
              ) : (
                <div className="settings-project-empty" role="status">
                  <FolderOpen aria-hidden="true" />
                  <strong>No active project found</strong>
                  <span>Create or join a project before SDK keys and action evidence can attach to it.</span>
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
