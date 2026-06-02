"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Database,
  Download,
  GitPullRequest,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import {
  disconnectGithubRepoConnection,
  eraseRetentionData,
  exportProjectData,
  getGithubConnectionStatus,
  getNotifications,
  getPiiPolicy,
  getProjectSettings,
  getRetention,
  testPiiDetector,
  updateNotifications,
  updatePiiPolicy,
  updateRetention,
} from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  NotificationSettingsResponse,
  PiiDetectorTestResponse,
  PiiPolicyResponse,
  ProjectResponse,
  RetentionDataErasureResponse,
  RetentionPolicyResponse,
} from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type SettingsState = {
  project: ProjectResponse | null;
  githubConnection: GithubConnectionStatusResponse | null;
  pii: PiiPolicyResponse | null;
  retention: RetentionPolicyResponse | null;
  notifications: NotificationSettingsResponse | null;
};

type SectionKey = "github" | "pii" | "retention" | "notifications";

const defaultNotifications: NotificationSettingsResponse = {
  email_enabled: true,
  slack_enabled: false,
  teams_enabled: false,
  browser_enabled: true,
  terminal_enabled: true,
  updated_at: "",
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

export default function SettingsPage() {
  const [state, setState] = useState<SettingsState>({
    project: null,
    githubConnection: null,
    pii: null,
    retention: null,
    notifications: null,
  });
  const [sectionErrors, setSectionErrors] = useState<Partial<Record<SectionKey, string>>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [exporting, setExporting] = useState(false);
  const [erasingData, setErasingData] = useState(false);
  const [eraseBatchSizeInput, setEraseBatchSizeInput] = useState("500");
  const [eraseConfirmInput, setEraseConfirmInput] = useState("");
  const [eraseSummary, setEraseSummary] = useState<RetentionDataErasureResponse | null>(null);

  const [piiInput, setPiiInput] = useState("");
  const [retentionInput, setRetentionInput] = useState("30");
  const [patternInput, setPatternInput] = useState("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}");
  const [sampleTextInput, setSampleTextInput] = useState("Contact me at test@example.com for setup details.");
  const [detectorResult, setDetectorResult] = useState<PiiDetectorTestResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSectionErrors({});
    try {
      const project = await withSettingsTimeout(
        getProjectSettings(),
        `Backend API timed out after ${settingsLoadTimeoutMs}ms. Start the Zroky backend and retry.`,
      );
      const [githubResult, piiResult, retentionResult, notificationsResult] = await Promise.allSettled([
        withSettingsTimeout(getGithubConnectionStatus(), "GitHub connection status timed out."),
        withSettingsTimeout(getPiiPolicy(), "PII policy load timed out."),
        withSettingsTimeout(getRetention(), "Retention policy load timed out."),
        withSettingsTimeout(getNotifications(), "Notification settings load timed out."),
      ]);

      const nextErrors: Partial<Record<SectionKey, string>> = {};
      if (githubResult.status === "rejected") nextErrors.github = errorMessage(githubResult.reason, "GitHub connection could not load.");
      if (piiResult.status === "rejected") nextErrors.pii = errorMessage(piiResult.reason, "PII policy could not load.");
      if (retentionResult.status === "rejected") nextErrors.retention = errorMessage(retentionResult.reason, "Retention policy could not load.");
      if (notificationsResult.status === "rejected") {
        nextErrors.notifications = errorMessage(notificationsResult.reason, "Notification settings could not load.");
      }

      const pii = piiResult.status === "fulfilled" ? piiResult.value : null;
      const retention = retentionResult.status === "fulfilled" ? retentionResult.value : null;
      const notifications = notificationsResult.status === "fulfilled" ? notificationsResult.value : null;

      setState({
        project,
        githubConnection: githubResult.status === "fulfilled" ? githubResult.value : null,
        pii,
        retention,
        notifications,
      });
      setSectionErrors(nextErrors);

      if (pii) setPiiInput(pii.custom_patterns.join("\n"));
      if (retention) setRetentionInput(String(retention.retention_days));
    } catch (loadError) {
      setError(errorMessage(loadError, "Failed to load project settings."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const notificationDraft = useMemo(() => state.notifications ?? defaultNotifications, [state.notifications]);
  const invalidPiiPatterns = useMemo(() => {
    return piiInput
      .split("\n")
      .map((line, index) => ({ line: line.trim(), index: index + 1 }))
      .filter((item) => item.line.length > 0)
      .map((item) => {
        try {
          new RegExp(item.line);
          return null;
        } catch (error) {
          return {
            index: item.index,
            message: error instanceof Error ? error.message : "Invalid regular expression.",
          };
        }
      })
      .filter((item): item is { index: number; message: string } => Boolean(item));
  }, [piiInput]);

  const enabledNotificationChannels = useMemo(() => {
    return [
      notificationDraft.email_enabled,
      notificationDraft.slack_enabled,
      notificationDraft.teams_enabled,
      notificationDraft.browser_enabled,
      notificationDraft.terminal_enabled,
    ].filter(Boolean).length;
  }, [notificationDraft]);

  function setNotification(key: keyof Omit<NotificationSettingsResponse, "updated_at">) {
    setState((prev) => ({
      ...prev,
      notifications: {
        ...(prev.notifications ?? defaultNotifications),
        [key]: !(prev.notifications ?? defaultNotifications)[key],
      },
    }));
  }

  async function onSavePii(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage("");
    if (invalidPiiPatterns.length > 0) {
      setStatusMessage(`Fix ${invalidPiiPatterns.length} invalid PII pattern${invalidPiiPatterns.length === 1 ? "" : "s"} before saving.`);
      return;
    }
    try {
      const patterns = piiInput
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const updated = await updatePiiPolicy(patterns);
      setState((prev) => ({ ...prev, pii: updated }));
      setSectionErrors((prev) => ({ ...prev, pii: undefined }));
      setStatusMessage("PII policy updated.");
    } catch (saveError) {
      setStatusMessage(errorMessage(saveError, "Failed to save PII policy."));
    }
  }

  async function onTestDetector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage("");
    try {
      const result = await testPiiDetector(patternInput, sampleTextInput);
      setDetectorResult(result);
      setStatusMessage("PII detector test completed.");
    } catch (detectorError) {
      setStatusMessage(errorMessage(detectorError, "PII detector test failed."));
    }
  }

  async function onSaveRetention(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage("");
    try {
      const retentionDays = Number(retentionInput);
      const updated = await updateRetention(Number.isFinite(retentionDays) ? retentionDays : 30);
      setState((prev) => ({ ...prev, retention: updated }));
      setSectionErrors((prev) => ({ ...prev, retention: undefined }));
      setStatusMessage("Retention policy updated.");
    } catch (retentionError) {
      setStatusMessage(errorMessage(retentionError, "Failed to save retention policy."));
    }
  }

  async function onSaveNotifications(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage("");
    try {
      const updated = await updateNotifications({
        email_enabled: notificationDraft.email_enabled,
        slack_enabled: notificationDraft.slack_enabled,
        teams_enabled: notificationDraft.teams_enabled,
        browser_enabled: notificationDraft.browser_enabled,
        terminal_enabled: notificationDraft.terminal_enabled,
      });
      setState((prev) => ({ ...prev, notifications: updated }));
      setSectionErrors((prev) => ({ ...prev, notifications: undefined }));
      setStatusMessage("Notification settings updated.");
    } catch (notificationError) {
      setStatusMessage(errorMessage(notificationError, "Failed to update notification settings."));
    }
  }

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

  async function onEraseProjectData(dryRun: boolean) {
    setStatusMessage("");
    if (!dryRun) {
      if (!eraseSummary?.dry_run) {
        setStatusMessage("Run a preview before permanent erasure so the affected tables are visible.");
        return;
      }
      if (!project || eraseConfirmInput.trim() !== project.project_id) {
        setStatusMessage("Type the exact project ID before deleting project data.");
        return;
      }
    }

    try {
      setErasingData(true);
      const batchSize = Number(eraseBatchSizeInput);
      const summary = await eraseRetentionData({
        dry_run: dryRun,
        batch_size: Number.isFinite(batchSize) ? batchSize : undefined,
      });
      setEraseSummary(summary);
      if (dryRun) setEraseConfirmInput("");
      const touchedTableCount = Object.values(summary.deleted_by_table).filter((count) => count > 0).length;
      setStatusMessage(
        dryRun
          ? `Erasure preview complete: ${summary.total_deleted} rows across ${touchedTableCount} tables.`
          : `Project data erasure complete: ${summary.total_deleted} rows deleted across ${touchedTableCount} tables.`,
      );
    } catch (erasureError) {
      setStatusMessage(errorMessage(erasureError, "Failed to erase project data."));
    } finally {
      setErasingData(false);
    }
  }

  function onStartGithubConnect() {
    window.location.href = "/api/zroky/v1/settings/github/connect/start";
  }

  async function onDisconnectGithub() {
    setStatusMessage("");
    try {
      const updated = await disconnectGithubRepoConnection();
      setState((prev) => ({ ...prev, githubConnection: updated }));
      setSectionErrors((prev) => ({ ...prev, github: undefined }));
      setStatusMessage("GitHub repository connection removed.");
    } catch (disconnectError) {
      setStatusMessage(errorMessage(disconnectError, "Failed to disconnect GitHub."));
    }
  }

  const project = state.project;
  const githubConnected = Boolean(state.githubConnection?.connected);
  const eraseConfirmMatches = Boolean(project && eraseConfirmInput.trim() === project.project_id);
  const previewReadyForDelete = Boolean(eraseSummary?.dry_run);
  const retentionDays = state.retention?.retention_days ?? null;
  const retentionBand = retentionDays == null ? "unknown" : retentionDays >= 30 ? "ready" : "short";

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
        <section className="panel">
          <div className="loading" />
        </section>
      ) : null}

      {!loading && project ? (
        <>
          <section className="settings-summary-grid">
            <article className="panel settings-summary-card">
              <Database aria-hidden="true" />
              <span>Project</span>
              <strong>{safeString(project.name, "Project")}</strong>
              <small className="mono">{project.project_id}</small>
            </article>
            <article className="panel settings-summary-card">
              <GitPullRequest aria-hidden="true" />
              <span>GitHub PRs</span>
              <strong>{githubConnected ? "Connected" : "Not connected"}</strong>
              <small>{state.githubConnection?.github_login ? `@${state.githubConnection.github_login}` : "Connect repo access for generated PRs"}</small>
            </article>
            <article className="panel settings-summary-card">
              <ShieldCheck aria-hidden="true" />
              <span>Retention</span>
              <strong>{retentionDays ?? "-"} days</strong>
              <small>{retentionBand === "short" ? "Short retention, review compliance needs" : `Updated ${formatDateTime(state.retention?.updated_at ?? null)}`}</small>
            </article>
            <article className="panel settings-summary-card">
              <BellRing aria-hidden="true" />
              <span>Alert channels</span>
              <strong>{enabledNotificationChannels}/5 enabled</strong>
              <small>Delivery toggles are project scoped.</small>
            </article>
          </section>

          <section className="settings-readiness-grid" aria-label="Project settings readiness">
            <div className="settings-readiness-item">
              <CheckCircle2 aria-hidden="true" />
              <span>PII detector saves only valid regex patterns.</span>
            </div>
            <div className="settings-readiness-item">
              <LockKeyhole aria-hidden="true" />
              <span>Data erasure requires preview plus exact project ID.</span>
            </div>
            <div className={githubConnected ? "settings-readiness-item" : "settings-readiness-item settings-readiness-warn"}>
              {githubConnected ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
              <span>{githubConnected ? "GitHub PR generation can use connected repo access." : "GitHub PR generation needs repo OAuth connection."}</span>
            </div>
          </section>

          {Object.values(sectionErrors).some(Boolean) ? (
            <section className="panel panel-muted">
              <header className="panel-header">
                <h3>Partial Settings Access</h3>
                <p>Some admin-only or backend-backed settings did not load. The available controls remain usable.</p>
              </header>
              <div className="list">
                {Object.entries(sectionErrors).map(([key, value]) =>
                  value ? (
                    <div key={key} className="list-row">
                      <div className="list-main">
                        <strong>{key}</strong>
                        <span>{value}</span>
                      </div>
                    </div>
                  ) : null,
                )}
              </div>
            </section>
          ) : null}

          <section className="grid-two settings-grid-row">
            <article className="panel settings-control-panel">
              <header className="panel-header">
                <div>
                  <h3>Project Metadata</h3>
                  <p>Identity and ownership for the active Zroky project.</p>
                </div>
                <button type="button" className="btn btn-soft" onClick={() => void load()}>
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </button>
              </header>

              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Project ID</strong>
                    <span className="mono">{project.project_id}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Name</strong>
                    <span>{project.name}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Owner reference</strong>
                    <span>{safeString(project.owner_ref, "-")}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Status</strong>
                    <span>{project.is_active ? "Active" : "Inactive"}</span>
                  </div>
                  <StatusPill value={project.is_active ? "active" : "inactive"} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Updated</strong>
                    <span>{formatDateTime(project.updated_at)}</span>
                  </div>
                </div>
              </div>
            </article>

            <article className="panel settings-control-panel">
              <header className="panel-header">
                <div>
                  <h3>GitHub PR Connection</h3>
                  <p>Connect your GitHub account so generated fixes can open pull requests.</p>
                </div>
                <StatusPill value={githubConnected ? "verified" : "warning"} />
              </header>

              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Connection</strong>
                    <span>{githubConnected ? "Connected" : "Not connected"}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>GitHub login</strong>
                    <span>{safeString(state.githubConnection?.github_login, "-")}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Scopes</strong>
                    <span>{state.githubConnection?.scopes.length ? state.githubConnection.scopes.join(", ") : "-"}</span>
                  </div>
                </div>
              </div>

              <div className="actions">
                <button type="button" className="btn btn-primary" onClick={onStartGithubConnect}>
                  <GitPullRequest aria-hidden="true" />
                  {githubConnected ? "Reconnect GitHub" : "Connect GitHub"}
                </button>
                {githubConnected ? (
                  <button type="button" className="btn btn-danger" onClick={() => void onDisconnectGithub()}>
                    Disconnect
                  </button>
                ) : null}
              </div>
            </article>
          </section>

          <section className="grid-two settings-grid-row">
            <article className="panel settings-control-panel">
              <header className="panel-header">
                <div>
                  <h3>PII Policy</h3>
                  <p>Custom redaction patterns used before storing captured call evidence.</p>
                </div>
              </header>

              <form className="field" onSubmit={onSavePii}>
                <label htmlFor="piiPatterns">Custom patterns, one per line</label>
                <textarea
                  id="piiPatterns"
                  value={piiInput}
                  onChange={(event) => setPiiInput(event.target.value)}
                  placeholder="\\d{16}"
                />
                {invalidPiiPatterns.length > 0 ? (
                  <div className="settings-validation-box" role="alert">
                    {invalidPiiPatterns.map((item) => (
                      <p key={item.index}>Line {item.index}: {item.message}</p>
                    ))}
                  </div>
                ) : piiInput.trim() ? (
                  <p className="field-success">All custom patterns compile locally.</p>
                ) : null}
                <div className="actions">
                  <button className="btn btn-primary" type="submit" disabled={invalidPiiPatterns.length > 0}>
                    Save PII policy
                  </button>
                </div>
              </form>

              <form className="grid-two settings-detector-form" onSubmit={onTestDetector}>
                <div className="field">
                  <label htmlFor="patternInput">Test pattern</label>
                  <input
                    id="patternInput"
                    value={patternInput}
                    onChange={(event) => setPatternInput(event.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="sampleInput">Sample text</label>
                  <input
                    id="sampleInput"
                    value={sampleTextInput}
                    onChange={(event) => setSampleTextInput(event.target.value)}
                  />
                </div>
                <div className="actions settings-grid-full">
                  <button className="btn btn-soft" type="submit">
                    Test detector
                  </button>
                </div>
              </form>

              {detectorResult ? (
                <div className="settings-inset">
                  <p className="hint">
                    Valid: {String(detectorResult.valid)}. Matches: {detectorResult.match_count}
                  </p>
                  {detectorResult.error ? <p className="field-error">{detectorResult.error}</p> : null}
                  {detectorResult.matches.length > 0 ? (
                    <p className="mono settings-key-reveal">{detectorResult.matches.join(", ")}</p>
                  ) : null}
                </div>
              ) : null}
            </article>

            <article className="panel settings-control-panel">
              <header className="panel-header">
                <div>
                  <h3>Retention & Notifications</h3>
                  <p>Control data lifecycle and delivery channels for operational alerts.</p>
                </div>
              </header>

              <form className="settings-inline-form" onSubmit={onSaveRetention}>
                <div className="field">
                  <label htmlFor="retentionDays">Retention days</label>
                  <input
                    id="retentionDays"
                    type="number"
                    min="1"
                    max="3650"
                    inputMode="numeric"
                    value={retentionInput}
                    onChange={(event) => setRetentionInput(event.target.value)}
                  />
                </div>
                <button className="btn btn-primary" type="submit">
                  Save retention
                </button>
              </form>

              <form className="list settings-notification-list" onSubmit={onSaveNotifications}>
                <label className="list-row" htmlFor="emailEnabled">
                  <span>Email</span>
                  <input id="emailEnabled" type="checkbox" checked={notificationDraft.email_enabled} onChange={() => setNotification("email_enabled")} />
                </label>
                <label className="list-row" htmlFor="slackEnabled">
                  <span>Slack</span>
                  <input id="slackEnabled" type="checkbox" checked={notificationDraft.slack_enabled} onChange={() => setNotification("slack_enabled")} />
                </label>
                <label className="list-row" htmlFor="teamsEnabled">
                  <span>Microsoft Teams</span>
                  <input id="teamsEnabled" type="checkbox" checked={notificationDraft.teams_enabled} onChange={() => setNotification("teams_enabled")} />
                </label>
                <label className="list-row" htmlFor="browserEnabled">
                  <span>Browser</span>
                  <input id="browserEnabled" type="checkbox" checked={notificationDraft.browser_enabled} onChange={() => setNotification("browser_enabled")} />
                </label>
                <label className="list-row" htmlFor="terminalEnabled">
                  <span>Terminal</span>
                  <input id="terminalEnabled" type="checkbox" checked={notificationDraft.terminal_enabled} onChange={() => setNotification("terminal_enabled")} />
                </label>
                <div className="actions">
                  <button className="btn btn-soft" type="submit">
                    Save channels
                  </button>
                  <Link className="btn btn-soft" href="/settings/integrations">
                    Manage integrations
                  </Link>
                </div>
              </form>
            </article>
          </section>

          <section className="grid-two settings-grid-row">
            <article className="panel settings-control-panel">
              <header className="panel-header">
                <div>
                  <h3>Data Export</h3>
                  <p>Download calls, diagnoses, and alerts for portability or offline audit.</p>
                </div>
              </header>
              <div className="actions">
                <button type="button" className="btn btn-soft" onClick={() => void onExportData()} disabled={exporting}>
                  <Download aria-hidden="true" />
                  {exporting ? "Preparing export..." : "Download JSON export"}
                </button>
              </div>
            </article>

            <article className="panel settings-control-panel profile-danger-zone">
              <header className="panel-header">
                <div>
                  <h3 className="profile-danger-title">Project Data Erasure</h3>
                  <p>Preview or permanently delete project operational data. Run preview before deleting.</p>
                </div>
              </header>
              <div className="settings-inline-form">
                <div className="field">
                  <label htmlFor="erasureBatchSize">Batch size</label>
                  <input
                    id="erasureBatchSize"
                    type="number"
                    min="1"
                    max="5000"
                    inputMode="numeric"
                    value={eraseBatchSizeInput}
                    onChange={(event) => setEraseBatchSizeInput(event.target.value)}
                  />
                </div>
                <button type="button" className="btn btn-soft" onClick={() => void onEraseProjectData(true)} disabled={erasingData}>
                  {erasingData ? "Running..." : "Preview"}
                </button>
              </div>
              <div className="settings-delete-confirm">
                <label htmlFor="erasureConfirmProject">Type project ID to unlock deletion</label>
                <input
                  id="erasureConfirmProject"
                  value={eraseConfirmInput}
                  onChange={(event) => setEraseConfirmInput(event.target.value)}
                  placeholder={project.project_id}
                  disabled={erasingData || !previewReadyForDelete}
                />
                <p className="hint">
                  {previewReadyForDelete
                    ? "Preview is ready. Permanent delete stays locked until the project ID matches."
                    : "Run preview first to see exactly what will be touched."}
                </p>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => void onEraseProjectData(false)}
                  disabled={erasingData || !previewReadyForDelete || !eraseConfirmMatches}
                >
                  <Trash2 aria-hidden="true" />
                  Delete data
                </button>
              </div>

              {eraseSummary ? (
                <div className="settings-inset">
                  <p className="hint">
                    Last result: {eraseSummary.dry_run ? "Preview" : "Applied"}. Total rows: {eraseSummary.total_deleted}
                  </p>
                  <div className="list">
                    {Object.entries(eraseSummary.deleted_by_table).map(([table, count]) => (
                      <div key={table} className="list-row">
                        <div className="list-main">
                          <strong>{table}</strong>
                          <span>{count} rows</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
