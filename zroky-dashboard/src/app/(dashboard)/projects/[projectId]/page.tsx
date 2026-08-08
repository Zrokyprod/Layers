"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleDot,
  Copy,
  FolderOpen,
  RefreshCw,
  Server,
  Terminal,
  Trash2,
} from "lucide-react";

import {
  deleteProject,
  getProjectSettings,
  listActionRunners,
  listMyProjects,
  registerActionRunner,
  type ActionRunnerResponse,
} from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type { CurrentUserProjectResponse, ProjectResponse } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type ProjectDetailState = {
  activeProject: ProjectResponse | null;
  projects: CurrentUserProjectResponse[];
  runners: ActionRunnerResponse[];
};

const runnerOperationKinds = ["TRANSFER", "UPDATE", "SEND", "EXECUTE"] as const;

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

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("error") || text.includes("unavailable") || text.includes("cannot");
}

function runnerCredentialRef(runner: ActionRunnerResponse): string | null {
  const direct = runner.credential_scope.default_credential_ref;
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  const prefixes = runner.credential_scope.allowed_prefixes;
  if (!Array.isArray(prefixes)) return null;
  const first = prefixes.find((value): value is string => typeof value === "string" && Boolean(value.trim()));
  return first?.trim() ?? null;
}

function credentialEnvName(credentialRef: string): string {
  const withoutScheme = credentialRef.trim().replace(
    /^(customer-runner-secret|zroky-secret|vault|aws-secretsmanager|gcp-secretmanager|azure-keyvault):\/\//,
    "",
  );
  const token = withoutScheme.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase();
  return `ZROKY_RUNNER_SECRET_${token || "YOUR_CREDENTIAL"}`;
}

function runnerSetupText(projectId: string, runner: ActionRunnerResponse): string {
  const credentialRef = runnerCredentialRef(runner) ?? "customer-runner-secret://your/credential";
  const operationArgs = runner.supported_operation_kinds
    .map((kind) => ` --supported-operation-kind ${kind}`)
    .join("");
  return [
    `ZROKY_PROJECT_ID=${projectId}`,
    "ZROKY_API_KEY=<project-api-key>",
    `ZROKY_RUNNER_ID=${runner.runner_id}`,
    "ZROKY_RUNNER_INSTANCE_ID=<unique-host-name>",
    `${credentialEnvName(credentialRef)}=<local-secret-or-json>`,
    "",
    "python -m pip install zroky",
    `zroky runner daemon${operationArgs}`,
  ].join("\n");
}

export default function ProjectDetailPage() {
  const params = useParams<{ projectId?: string }>();
  const router = useRouter();
  const routeProjectId = typeof params.projectId === "string" ? decodeURIComponent(params.projectId) : "";
  const [state, setState] = useState<ProjectDetailState>({ activeProject: null, projects: [], runners: [] });
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectListError, setProjectListError] = useState<string | null>(null);
  const [runnerListError, setRunnerListError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [registeringRunner, setRegisteringRunner] = useState(false);
  const [runnerName, setRunnerName] = useState("Protected action runner");
  const [runnerEnvironment, setRunnerEnvironment] = useState("production");
  const [credentialRef, setCredentialRef] = useState("");
  const [operationKinds, setOperationKinds] = useState<string[]>(["TRANSFER"]);
  const setActiveProject = useDashboardStore((store) => store.setSelectedProject);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProjectListError(null);
    setRunnerListError(null);

    try {
      const [activeResult, projectsResult, runnersResult] = await Promise.allSettled([
        withProjectTimeout(
          getProjectSettings(),
          `Backend API timed out after ${projectDetailLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
        ),
        withProjectTimeout(listMyProjects(), "Project list load timed out."),
        withProjectTimeout(listActionRunners(), "Runner status load timed out."),
      ]);

      if (activeResult.status === "rejected") {
        throw activeResult.reason;
      }

      const activeProject = activeResult.value;
      const projects = projectsResult.status === "fulfilled" ? projectsResult.value : [];
      const runners = runnersResult.status === "fulfilled" ? runnersResult.value.items : [];
      setState({ activeProject, projects, runners });

      if (projectsResult.status === "rejected") {
        setProjectListError(errorMessage(projectsResult.reason, "Project list could not load."));
      }
      if (runnersResult.status === "rejected") {
        setRunnerListError(errorMessage(runnersResult.reason, "Runner status could not load."));
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

  const rows = state.projects;

  const selectedProject = rows.find((project) => project.project_id === routeProjectId) ?? null;
  const activeProjectId = state.activeProject?.project_id ?? null;
  const selectedIsActive = Boolean(selectedProject && selectedProject.project_id === activeProjectId);
  const selectedRole = selectedProject?.role?.trim().toLowerCase() ?? "";
  const canManageRunners = selectedIsActive && ["owner", "admin"].includes(selectedRole);
  const canRegisterRunner = Boolean(
    canManageRunners &&
      runnerName.trim().length >= 3 &&
      credentialRef.trim() &&
      operationKinds.length > 0 &&
      !registeringRunner,
  );
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

  function toggleOperationKind(kind: string) {
    setOperationKinds((current) =>
      current.includes(kind) ? current.filter((value) => value !== kind) : [...current, kind],
    );
  }

  async function onRegisterRunner(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !canRegisterRunner) {
      setStatusMessage("Enter a runner name, credential reference, and at least one operation kind.");
      return;
    }
    setStatusMessage("");
    setRegisteringRunner(true);
    try {
      const normalizedCredentialRef = credentialRef.trim();
      const runner = await registerActionRunner({
        name: runnerName.trim(),
        runner_type: "customer_hosted",
        environment: runnerEnvironment,
        supported_operation_kinds: operationKinds,
        credential_scope: {
          allowed_prefixes: [normalizedCredentialRef],
          default_credential_ref: normalizedCredentialRef,
        },
      });
      setState((current) => ({
        ...current,
        runners: [runner, ...current.runners.filter((item) => item.runner_id !== runner.runner_id)],
      }));
      setStatusMessage("Runner registered. Start it in your environment to confirm the heartbeat.");
    } catch (registerError) {
      setStatusMessage(errorMessage(registerError, "Failed to register runner."));
    } finally {
      setRegisteringRunner(false);
    }
  }

  async function copyRunnerSetup(projectId: string, runner: ActionRunnerResponse) {
    try {
      await navigator.clipboard.writeText(runnerSetupText(projectId, runner));
      setStatusMessage("Runner setup copied.");
    } catch {
      setStatusMessage("Runner setup could not be copied. Select the command text manually.");
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
                  <StatusPill value={selectedIsActive ? "active" : "available"} />
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
                        Deactivates this project and revokes active API keys. Project data is not immediately erased.
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

              {selectedIsActive ? (
                <section className="project-runner-section" aria-label="Protected action runners">
                  <header className="project-runner-header">
                    <div>
                      <span>Protected execution</span>
                      <h3>Action runners</h3>
                      <p>Runners execute approved actions with credentials that stay in your environment.</p>
                    </div>
                    <span className="project-runner-count">
                      <Server aria-hidden="true" />
                      {state.runners.length} registered
                    </span>
                  </header>

                  {runnerListError ? (
                    <div className="settings-project-warning" role="status">
                      <AlertTriangle aria-hidden="true" />
                      <span>{runnerListError}</span>
                    </div>
                  ) : null}

                  {state.runners.length > 0 ? (
                    <div className="project-runner-list" role="list">
                      {state.runners.map((runner) => {
                        const localCredentialRef = runnerCredentialRef(runner);
                        return (
                          <article className="project-runner-card" key={runner.runner_id} role="listitem">
                            <div className="project-runner-card-head">
                              <div>
                                <strong>{runner.name}</strong>
                                <span>{runner.environment} / {runner.runner_type.replace(/_/g, " ")}</span>
                              </div>
                              <StatusPill value={runner.status} />
                            </div>
                            <dl className="project-runner-facts">
                              <div>
                                <dt>Runner ID</dt>
                                <dd className="mono">{runner.runner_id}</dd>
                              </div>
                              <div>
                                <dt>Last heartbeat</dt>
                                <dd>{runner.last_heartbeat_at ? formatDateTime(runner.last_heartbeat_at) : "Not received"}</dd>
                              </div>
                              <div>
                                <dt>Allowed operations</dt>
                                <dd>{runner.supported_operation_kinds.join(", ") || "None"}</dd>
                              </div>
                              <div>
                                <dt>Credential reference</dt>
                                <dd className="mono">{localCredentialRef ?? "Not configured"}</dd>
                              </div>
                            </dl>
                            <details className="project-runner-launch">
                              <summary>
                                <Terminal aria-hidden="true" />
                                Launch this runner
                              </summary>
                              <p>
                                Create a project API key, keep the real credential on this host, then run the daemon.
                              </p>
                              <pre>{runnerSetupText(selectedProject.project_id, runner)}</pre>
                              <div className="project-runner-actions">
                                <button
                                  type="button"
                                  className="btn btn-soft"
                                  onClick={() => void copyRunnerSetup(selectedProject.project_id, runner)}
                                >
                                  <Copy aria-hidden="true" />
                                  Copy setup
                                </button>
                                <Link href="/settings/keys" className="btn btn-soft">
                                  Create API key
                                </Link>
                              </div>
                            </details>
                          </article>
                        );
                      })}
                    </div>
                  ) : runnerListError ? null : (
                    <div className="project-runner-empty" role="status">
                      <Server aria-hidden="true" />
                      <div>
                        <strong>No runner registered</strong>
                        <span>Register one before protected actions can execute.</span>
                      </div>
                    </div>
                  )}

                  {canManageRunners ? (
                    <details className="project-runner-register" open={state.runners.length === 0}>
                      <summary>Register a customer-hosted runner</summary>
                      <form onSubmit={(event) => void onRegisterRunner(event)}>
                        <div className="project-runner-fields">
                          <div className="project-runner-field">
                            <label htmlFor="runnerName">Runner name</label>
                            <input
                              id="runnerName"
                              value={runnerName}
                              onChange={(event) => setRunnerName(event.target.value)}
                              minLength={3}
                              required
                            />
                          </div>
                          <div className="project-runner-field">
                            <label htmlFor="runnerEnvironment">Environment</label>
                            <select
                              id="runnerEnvironment"
                              value={runnerEnvironment}
                              onChange={(event) => setRunnerEnvironment(event.target.value)}
                            >
                              <option value="production">Production</option>
                              <option value="staging">Staging</option>
                              <option value="development">Development</option>
                            </select>
                          </div>
                          <div className="project-runner-field project-runner-credential-field">
                            <label htmlFor="runnerCredentialRef">Credential reference</label>
                            <input
                              id="runnerCredentialRef"
                              value={credentialRef}
                              onChange={(event) => setCredentialRef(event.target.value)}
                              placeholder="customer-runner-secret://payments/stripe"
                              aria-describedby="runnerCredentialHelp"
                              required
                            />
                            <small id="runnerCredentialHelp">This is a name only. The credential value stays on the runner host.</small>
                          </div>
                        </div>
                        <fieldset className="project-runner-operation-fieldset">
                          <legend>Allowed operation kinds</legend>
                          {runnerOperationKinds.map((kind) => (
                            <label key={kind}>
                              <input
                                type="checkbox"
                                checked={operationKinds.includes(kind)}
                                onChange={() => toggleOperationKind(kind)}
                              />
                              {kind.charAt(0) + kind.slice(1).toLowerCase()}
                            </label>
                          ))}
                        </fieldset>
                        <button type="submit" className="btn btn-primary" disabled={!canRegisterRunner}>
                          <Server aria-hidden="true" />
                          {registeringRunner ? "Registering..." : "Register runner"}
                        </button>
                      </form>
                    </details>
                  ) : (
                    <p className="project-runner-permission">Only a project owner or admin can register a runner.</p>
                  )}
                </section>
              ) : null}
            </>
          ) : projectListError ? (
            <div className="settings-project-empty projects-not-found" role="status">
              <AlertTriangle aria-hidden="true" />
              <strong>Project access unavailable</strong>
              <span>Retry before relying on project roles or deletion controls.</span>
              <button type="button" className="btn btn-soft" onClick={() => void load()}>
                Retry
              </button>
            </div>
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
