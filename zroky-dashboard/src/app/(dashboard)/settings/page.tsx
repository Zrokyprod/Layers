"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  createProjectApiKey,
  disconnectGithubRepoConnection,
  eraseRetentionData,
  exportProjectData,
  getGithubConnectionStatus,
  getNotifications,
  getPiiPolicy,
  getPricingValidation,
  getProjectSettings,
  getRetention,
  getRollbackDrill,
  listProjectApiKeys,
  listProviderVerifications,
  revokeProjectApiKey,
  testPiiDetector,
  testProviderConnection,
  updateNotifications,
  updatePiiPolicy,
  updatePricingValidation,
  updateRetention,
  updateRollbackDrill,
  verifyRollbackDrill,
} from "@/lib/api";
import { formatDateTime, safeString } from "@/lib/format";
import type {
  ApiKeyResponse,
  GithubConnectionStatusResponse,
  NotificationSettingsResponse,
  PiiDetectorTestResponse,
  PiiPolicyResponse,
  PricingInterviewNote,
  PricingValidationResponse,
  ProjectResponse,
  ProviderVerificationItem,
  RollbackDrillResponse,
  RollbackDrillVerificationResponse,
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
  pricingValidation: PricingValidationResponse | null;
  rollbackDrill: RollbackDrillResponse | null;
  providers: ProviderVerificationItem[];
  apiKeys: ApiKeyResponse[];
};

export default function SettingsPage() {
  const [state, setState] = useState<SettingsState>({
    project: null,
    githubConnection: null,
    pii: null,
    retention: null,
    notifications: null,
    pricingValidation: null,
    rollbackDrill: null,
    providers: [],
    apiKeys: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [exporting, setExporting] = useState(false);
  const [erasingData, setErasingData] = useState(false);
  const [eraseBatchSizeInput, setEraseBatchSizeInput] = useState("500");
  const [eraseSummary, setEraseSummary] = useState<RetentionDataErasureResponse | null>(null);

  const [piiInput, setPiiInput] = useState("");
  const [retentionInput, setRetentionInput] = useState("30");
  const [patternInput, setPatternInput] = useState("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}");
  const [sampleTextInput, setSampleTextInput] = useState("Contact me at test@example.com for setup details.");
  const [detectorResult, setDetectorResult] = useState<PiiDetectorTestResponse | null>(null);

  const [pricingModelInput, setPricingModelInput] = useState<"tiered" | "usage_based" | "undecided">("undecided");
  const [pricingRationaleInput, setPricingRationaleInput] = useState("");
  const [pricingMigrationPathInput, setPricingMigrationPathInput] = useState("");
  const [pricingInterviewsInput, setPricingInterviewsInput] = useState("[]");
  const [lockPricingDecisionInput, setLockPricingDecisionInput] = useState(false);

  const [rollbackDeployRevisionInput, setRollbackDeployRevisionInput] = useState("");
  const [rollbackTargetRevisionInput, setRollbackTargetRevisionInput] = useState("");
  const [rollbackStatusInput, setRollbackStatusInput] = useState<"not_started" | "in_progress" | "passed" | "failed">("not_started");
  const [rollbackDeployPassedInput, setRollbackDeployPassedInput] = useState(false);
  const [rollbackRollbackPassedInput, setRollbackRollbackPassedInput] = useState(false);
  const [rollbackFailureSimulationInput, setRollbackFailureSimulationInput] = useState(false);
  const [rollbackFailureCategoryInput, setRollbackFailureCategoryInput] = useState<
    "TOKEN_OVERFLOW" | "RATE_LIMIT" | "AUTH_FAILURE" | "LOOP_DETECTED" | "COST_SPIKE" | ""
  >("");
  const [rollbackFailureNotesInput, setRollbackFailureNotesInput] = useState("");
  const [rollbackDrillNotesInput, setRollbackDrillNotesInput] = useState("");
  const [rollbackVerificationRunningPhase, setRollbackVerificationRunningPhase] = useState<"deploy" | "rollback" | null>(null);
  const [rollbackVerificationResult, setRollbackVerificationResult] = useState<RollbackDrillVerificationResponse | null>(null);

  const [apiKeyName, setApiKeyName] = useState("Zroky Dashboard Key");
  const [latestCreatedApiKey, setLatestCreatedApiKey] = useState<string>("");

  const canLoadApiKeys = Boolean(state.project?.project_id);

  function applyRollbackDrillToInputs(rollbackDrill: RollbackDrillResponse) {
    setRollbackDeployRevisionInput(rollbackDrill.deploy_revision ?? "");
    setRollbackTargetRevisionInput(rollbackDrill.rollback_revision ?? "");
    setRollbackStatusInput(rollbackDrill.status);
    setRollbackDeployPassedInput(rollbackDrill.deploy_test_passed);
    setRollbackRollbackPassedInput(rollbackDrill.rollback_test_passed);
    setRollbackFailureSimulationInput(rollbackDrill.failure_simulation_performed);
    setRollbackFailureCategoryInput(rollbackDrill.failure_simulation_category ?? "");
    setRollbackFailureNotesInput(rollbackDrill.failure_simulation_notes ?? "");
    setRollbackDrillNotesInput(rollbackDrill.drill_notes ?? "");
  }

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [project, githubConnection, pii, retention, notifications, pricingValidation, rollbackDrill, providersPayload] = await Promise.all([
        getProjectSettings(),
        getGithubConnectionStatus(),
        getPiiPolicy(),
        getRetention(),
        getNotifications(),
        getPricingValidation(),
        getRollbackDrill(),
        listProviderVerifications(),
      ]);

      let apiKeys: ApiKeyResponse[] = [];
      try {
        apiKeys = await listProjectApiKeys(project.project_id);
      } catch {
        apiKeys = [];
      }

      setState({
        project,
        githubConnection,
        pii,
        retention,
        notifications,
        pricingValidation,
        rollbackDrill,
        providers: providersPayload.items,
        apiKeys,
      });

      setPiiInput(pii.custom_patterns.join("\n"));
      setRetentionInput(String(retention.retention_days));
      setPricingModelInput(pricingValidation.selected_launch_model);
      setPricingRationaleInput(pricingValidation.rationale ?? "");
      setPricingMigrationPathInput(pricingValidation.migration_path ?? "");
      setPricingInterviewsInput(JSON.stringify(pricingValidation.interviews, null, 2));
      setLockPricingDecisionInput(pricingValidation.pricing_locked);
      applyRollbackDrillToInputs(rollbackDrill);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Failed to load settings.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const notificationDraft = useMemo(() => {
    return {
      email_enabled: state.notifications?.email_enabled ?? true,
      slack_enabled: state.notifications?.slack_enabled ?? false,
      teams_enabled: state.notifications?.teams_enabled ?? false,
      browser_enabled: state.notifications?.browser_enabled ?? true,
      terminal_enabled: state.notifications?.terminal_enabled ?? true,
    };
  }, [state.notifications]);

  async function onSavePii(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const patterns = piiInput
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
      const updated = await updatePiiPolicy(patterns);
      setState((prev) => ({ ...prev, pii: updated }));
      setStatusMessage("PII policy updated.");
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "Failed to save PII policy.";
      setStatusMessage(message);
    }
  }

  async function onTestDetector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const result = await testPiiDetector(patternInput, sampleTextInput);
      setDetectorResult(result);
      setStatusMessage("PII detector test completed.");
    } catch (detectorError) {
      const message = detectorError instanceof Error ? detectorError.message : "PII detector test failed.";
      setStatusMessage(message);
    }
  }

  async function onSaveRetention(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const retentionDays = Number(retentionInput);
      const updated = await updateRetention(retentionDays);
      setState((prev) => ({ ...prev, retention: updated }));
      setStatusMessage("Retention policy updated.");
    } catch (retentionError) {
      const message = retentionError instanceof Error ? retentionError.message : "Failed to save retention policy.";
      setStatusMessage(message);
    }
  }

  async function onSaveNotifications(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const updated = await updateNotifications(notificationDraft);
      setState((prev) => ({ ...prev, notifications: updated }));
      setStatusMessage("Notification settings updated.");
    } catch (notificationError) {
      const message = notificationError instanceof Error ? notificationError.message : "Failed to update notification settings.";
      setStatusMessage(message);
    }
  }

  async function onSavePricingValidation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const parsedRaw = JSON.parse(pricingInterviewsInput || "[]") as unknown;
      if (!Array.isArray(parsedRaw)) {
        throw new Error("Interviews must be a JSON array.");
      }

      const interviews = parsedRaw as PricingInterviewNote[];
      const updated = await updatePricingValidation({
        selected_launch_model: pricingModelInput,
        rationale: pricingRationaleInput.trim() || null,
        migration_path: pricingMigrationPathInput.trim() || null,
        interviews,
        lock_pricing_decision: lockPricingDecisionInput,
      });

      setState((prev) => ({ ...prev, pricingValidation: updated }));
      setPricingInterviewsInput(JSON.stringify(updated.interviews, null, 2));
      setLockPricingDecisionInput(updated.pricing_locked);
      setStatusMessage(
        updated.pricing_locked
          ? "Pricing validation saved and pricing decision locked."
          : "Pricing validation evidence saved.",
      );
    } catch (pricingError) {
      const message = pricingError instanceof Error ? pricingError.message : "Failed to update pricing validation settings.";
      setStatusMessage(message);
    }
  }

  async function onSaveRollbackDrill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (rollbackStatusInput === "passed" && !state.pricingValidation?.launch_gate_passed) {
      setStatusMessage("Pricing launch gate incomplete. Finish 5 unique beta interviews and lock pricing before marking rollback drill passed.");
      return;
    }

    try {
      const updated = await updateRollbackDrill({
        deploy_revision: rollbackDeployRevisionInput.trim() || null,
        rollback_revision: rollbackTargetRevisionInput.trim() || null,
        deploy_test_passed: rollbackDeployPassedInput,
        rollback_test_passed: rollbackRollbackPassedInput,
        failure_simulation_performed: rollbackFailureSimulationInput,
        failure_simulation_category: rollbackFailureCategoryInput || null,
        failure_simulation_notes: rollbackFailureNotesInput.trim() || null,
        drill_notes: rollbackDrillNotesInput.trim() || null,
        status: rollbackStatusInput,
      });

      setState((prev) => ({ ...prev, rollbackDrill: updated }));
      applyRollbackDrillToInputs(updated);
      setStatusMessage(`Rollback drill status saved: ${updated.status}.`);
    } catch (rollbackError) {
      const message = rollbackError instanceof Error ? rollbackError.message : "Failed to update rollback drill settings.";
      setStatusMessage(message);
    }
  }

  async function onRunRollbackVerification(phase: "deploy" | "rollback") {
    const deployRevision = rollbackDeployRevisionInput.trim() || null;
    const rollbackRevision = rollbackTargetRevisionInput.trim() || null;

    try {
      setRollbackVerificationRunningPhase(phase);
      const verification = await verifyRollbackDrill(
        phase === "deploy"
          ? { phase, deploy_revision: deployRevision }
          : { phase, rollback_revision: rollbackRevision },
      );

      setRollbackVerificationResult(verification);
      setState((prev) => ({ ...prev, rollbackDrill: verification.rollback_drill }));
      applyRollbackDrillToInputs(verification.rollback_drill);

      if (verification.passed) {
        setStatusMessage(`${phase === "deploy" ? "Deploy" : "Rollback"} verification passed.`);
      } else {
        const failedChecks = verification.checks
          .filter((item) => item.status === "failed")
          .map((item) => item.name)
          .join(", ");
        setStatusMessage(
          failedChecks
            ? `${phase === "deploy" ? "Deploy" : "Rollback"} verification failed: ${failedChecks}.`
            : `${phase === "deploy" ? "Deploy" : "Rollback"} verification failed.`,
        );
      }
    } catch (verificationError) {
      const message = verificationError instanceof Error ? verificationError.message : "Rollback verification failed.";
      setStatusMessage(message);
    } finally {
      setRollbackVerificationRunningPhase(null);
    }
  }

  async function onToggleNotification(
    key: "email_enabled" | "slack_enabled" | "teams_enabled" | "browser_enabled" | "terminal_enabled",
  ) {
    const current = state.notifications;
    if (!current) {
      return;
    }

    setState((prev) => ({
      ...prev,
      notifications: prev.notifications
        ? {
            ...prev.notifications,
            [key]: !prev.notifications[key],
          }
        : prev.notifications,
    }));
  }

  async function onTestProvider(provider: string) {
    try {
      await testProviderConnection(provider);
      setStatusMessage(`${provider} verification succeeded.`);
      await load();
    } catch (providerError) {
      const message = providerError instanceof Error ? providerError.message : "Provider test failed.";
      setStatusMessage(message);
    }
  }

  async function onCreateApiKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.project) {
      return;
    }

    try {
      const created = await createProjectApiKey(state.project.project_id, apiKeyName);
      setLatestCreatedApiKey(created.api_key);
      await load();
      setStatusMessage("API key created.");
    } catch (createError) {
      const message = createError instanceof Error ? createError.message : "Failed to create API key.";
      setStatusMessage(message);
    }
  }

  async function onRevokeApiKey(keyId: string) {
    if (!state.project) {
      return;
    }

    try {
      await revokeProjectApiKey(state.project.project_id, keyId);
      await load();
      setStatusMessage("API key revoked.");
    } catch (revokeError) {
      const message = revokeError instanceof Error ? revokeError.message : "Failed to revoke API key.";
      setStatusMessage(message);
    }
  }

  async function onExportData() {
    try {
      setExporting(true);
      const payload = await exportProjectData({
        limit: 500,
        include_payload: true,
      });

      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      link.href = downloadUrl;
      link.download = `zroky-export-${payload.tenant_id}-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);

      setStatusMessage(
        `Export downloaded: ${payload.call_count} calls, ${payload.diagnosis_count} diagnoses, ${payload.alert_count} alerts.`,
      );
    } catch (exportError) {
      const message = exportError instanceof Error ? exportError.message : "Failed to export project data.";
      setStatusMessage(message);
    } finally {
      setExporting(false);
    }
  }

  async function onEraseProjectData(dryRun: boolean) {
    if (!dryRun) {
      const confirmed = window.confirm(
        "This will permanently delete project diagnosis data, calls, alerts, feedback, share links, PR links, and audit logs. Continue?",
      );
      if (!confirmed) {
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

      const touchedTableCount = Object.values(summary.deleted_by_table).filter((count) => count > 0).length;
      setStatusMessage(
        dryRun
          ? `Erasure dry run complete: ${summary.total_deleted} rows across ${touchedTableCount} tables.`
          : `Project data erasure complete: ${summary.total_deleted} rows deleted across ${touchedTableCount} tables.`,
      );
    } catch (erasureError) {
      const message = erasureError instanceof Error ? erasureError.message : "Failed to erase project data.";
      setStatusMessage(message);
    } finally {
      setErasingData(false);
    }
  }

  function onStartGithubConnect() {
    window.location.href = "/api/zroky/v1/settings/github/connect/start";
  }

  async function onDisconnectGithub() {
    try {
      const updated = await disconnectGithubRepoConnection();
      setState((prev) => ({ ...prev, githubConnection: updated }));
      setStatusMessage("GitHub repository connection removed.");
    } catch (disconnectError) {
      const message = disconnectError instanceof Error ? disconnectError.message : "Failed to disconnect GitHub.";
      setStatusMessage(message);
    }
  }

  return (
    <>
      {error ? <section className="panel"><p>{error}</p></section> : null}
      {statusMessage ? <section className="panel"><p>{statusMessage}</p></section> : null}

      {loading ? (
        <section className="panel">
          <div className="loading" />
        </section>
      ) : null}

      {!loading ? (
        <>
          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Project Settings</h3>
                  <p>Core project identity and ownership.</p>
                </div>
              </header>

              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Project ID</strong>
                    <span className="mono">{safeString(state.project?.project_id, "-")}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Name</strong>
                    <span>{safeString(state.project?.name, "-")}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Owner Ref</strong>
                    <span>{safeString(state.project?.owner_ref, "-")}</span>
                  </div>
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Updated</strong>
                    <span>{formatDateTime(state.project?.updated_at ?? null)}</span>
                  </div>
                </div>
              </div>
            </article>

            <article className="panel panel-muted">
              <header className="panel-header">
                <div>
                  <h3>API Keys</h3>
                  <p>Create and revoke project keys.</p>
                </div>
              </header>

              {!canLoadApiKeys ? (
                <div className="empty">Project context missing, API keys cannot load.</div>
              ) : (
                <>
                  <form className="actions" onSubmit={onCreateApiKey}>
                    <div className="field settings-key-field">
                      <label htmlFor="apiKeyName">Key Name</label>
                      <input
                        id="apiKeyName"
                        value={apiKeyName}
                        onChange={(event) => setApiKeyName(event.target.value)}
                        placeholder="Zroky Dashboard Key"
                      />
                    </div>
                    <button className="btn btn-primary" type="submit">
                      Create Key
                    </button>
                  </form>

                  {latestCreatedApiKey ? (
                    <div className="settings-inset">
                      <p className="hint">Copy once:</p>
                      <p className="mono settings-key-reveal">
                        {latestCreatedApiKey}
                      </p>
                    </div>
                  ) : null}

                  <div className="list">
                    {state.apiKeys.length === 0 ? (
                      <div className="empty">No API keys listed. If this stays empty, auth permissions may be missing.</div>
                    ) : (
                      state.apiKeys.map((key) => (
                        <div key={key.key_id} className="list-row">
                          <div className="list-main">
                            <strong>{key.name}</strong>
                            <span className="mono">
                              {key.key_prefix} ┬╖ {formatDateTime(key.created_at)}
                            </span>
                          </div>
                          <div className="actions">
                            <StatusPill value={key.revoked ? "revoked" : "active"} />
                            {!key.revoked ? (
                              <button type="button" className="btn btn-danger" onClick={() => void onRevokeApiKey(key.key_id)}>
                                Revoke
                              </button>
                            ) : null}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </article>
          </section>

          <section className="panel">
            <header className="panel-header">
              <div>
                <h3>GitHub PR Connection</h3>
                <p>Connect your GitHub account so PR generation can use your repo access token.</p>
              </div>
              <StatusPill value={state.githubConnection?.connected ? "verified" : "warning"} />
            </header>

            <div className="list">
              <div className="list-row">
                <div className="list-main">
                  <strong>Connection Status</strong>
                  <span>{state.githubConnection?.connected ? "Connected" : "Not connected"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>GitHub Login</strong>
                  <span>{safeString(state.githubConnection?.github_login, "-")}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Scopes</strong>
                  <span>
                    {state.githubConnection?.scopes && state.githubConnection.scopes.length > 0
                      ? state.githubConnection.scopes.join(", ")
                      : "-"}
                  </span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Connected At</strong>
                  <span>{formatDateTime(state.githubConnection?.connected_at ?? null)}</span>
                </div>
              </div>
            </div>

            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={onStartGithubConnect}>
                {state.githubConnection?.connected ? "Reconnect GitHub" : "Connect GitHub"}
              </button>
              {state.githubConnection?.connected ? (
                <button type="button" className="btn btn-danger" onClick={() => void onDisconnectGithub()}>
                  Disconnect
                </button>
              ) : null}
            </div>
          </section>

          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>PII Policy</h3>
                  <p>Custom detection patterns and validator.</p>
                </div>
              </header>

              <form className="field" onSubmit={onSavePii}>
                <label htmlFor="piiPatterns">Custom Patterns (one per line)</label>
                <textarea
                  id="piiPatterns"
                  value={piiInput}
                  onChange={(event) => setPiiInput(event.target.value)}
                  placeholder="\\d{16}"
                />
                <div className="actions">
                  <button className="btn btn-primary" type="submit">
                    Save PII Policy
                  </button>
                </div>
              </form>

              <form className="grid-two" onSubmit={onTestDetector}>
                <div className="field">
                  <label htmlFor="patternInput">Test Pattern</label>
                  <input
                    id="patternInput"
                    value={patternInput}
                    onChange={(event) => setPatternInput(event.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="sampleInput">Sample Text</label>
                  <input
                    id="sampleInput"
                    value={sampleTextInput}
                    onChange={(event) => setSampleTextInput(event.target.value)}
                  />
                </div>
                <div className="actions settings-grid-full">
                  <button className="btn btn-soft" type="submit">
                    Test Detector
                  </button>
                </div>
              </form>

              {detectorResult ? (
                <div className="settings-inset">
                  <p className="hint">
                    Valid: {String(detectorResult.valid)} ┬╖ Matches: {detectorResult.match_count}
                  </p>
                  {detectorResult.error ? <p className="hint">Error: {detectorResult.error}</p> : null}
                </div>
              ) : null}
            </article>

            <article className="panel panel-muted">
              <header className="panel-header">
                <div>
                  <h3>Retention + Notifications</h3>
                  <p>Data lifecycle and channel toggles.</p>
                </div>
              </header>

              <form className="actions" onSubmit={onSaveRetention}>
                <div className="field">
                  <label htmlFor="retentionDays">Retention Days</label>
                  <input
                    id="retentionDays"
                    value={retentionInput}
                    onChange={(event) => setRetentionInput(event.target.value)}
                  />
                </div>
                <button className="btn btn-primary" type="submit">
                  Save Retention
                </button>
              </form>

              <div className="settings-inset">
                <div className="field">
                  <label htmlFor="erasureBatchSize">Erasure Batch Size</label>
                  <input
                    id="erasureBatchSize"
                    value={eraseBatchSizeInput}
                    onChange={(event) => setEraseBatchSizeInput(event.target.value)}
                  />
                </div>

                <div className="actions">
                  <button
                    type="button"
                    className="btn btn-soft"
                    onClick={() => void onEraseProjectData(true)}
                    disabled={erasingData}
                  >
                    {erasingData ? "Running..." : "Preview Data Erasure"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => void onEraseProjectData(false)}
                    disabled={erasingData}
                  >
                    {erasingData ? "Deleting..." : "Delete All Project Data"}
                  </button>
                </div>

                <p className="hint">Delete-all supports GDPR-style project data erasure. Run preview before permanent deletion.</p>

                {eraseSummary ? (
                  <div className="list">
                    <div className="list-row">
                      <div className="list-main">
                        <strong>Last Erasure Summary</strong>
                        <span>
                          {eraseSummary.dry_run ? "Dry Run" : "Applied"} ┬╖ total deleted: {eraseSummary.total_deleted}
                        </span>
                      </div>
                    </div>
                    {Object.entries(eraseSummary.deleted_by_table).map(([table, count]) => (
                      <div key={table} className="list-row">
                        <div className="list-main">
                          <strong>{table}</strong>
                          <span>{count} rows</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <form className="list" onSubmit={onSaveNotifications}>
                <label className="list-row" htmlFor="emailEnabled">
                  <span>Email</span>
                  <input
                    id="emailEnabled"
                    type="checkbox"
                    checked={notificationDraft.email_enabled}
                    onChange={() => void onToggleNotification("email_enabled")}
                  />
                </label>

                <label className="list-row" htmlFor="slackEnabled">
                  <span>Slack</span>
                  <input
                    id="slackEnabled"
                    type="checkbox"
                    checked={notificationDraft.slack_enabled}
                    onChange={() => void onToggleNotification("slack_enabled")}
                  />
                </label>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Slack App</strong>
                    <span>Connect a workspace and channel for alert delivery.</span>
                  </div>
                  <Link className="btn btn-soft" href="/settings/integrations/slack">
                    Manage Slack
                  </Link>
                </div>

                <label className="list-row" htmlFor="teamsEnabled">
                  <span>Microsoft Teams</span>
                  <input
                    id="teamsEnabled"
                    type="checkbox"
                    checked={notificationDraft.teams_enabled}
                    onChange={() => void onToggleNotification("teams_enabled")}
                  />
                </label>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Teams Webhook</strong>
                    <span>Connect a Teams channel for alert delivery.</span>
                  </div>
                  <Link className="btn btn-soft" href="/settings/integrations/teams">
                    Manage Teams
                  </Link>
                </div>

                <label className="list-row" htmlFor="browserEnabled">
                  <span>Browser</span>
                  <input
                    id="browserEnabled"
                    type="checkbox"
                    checked={notificationDraft.browser_enabled}
                    onChange={() => void onToggleNotification("browser_enabled")}
                  />
                </label>

                <label className="list-row" htmlFor="terminalEnabled">
                  <span>Terminal</span>
                  <input
                    id="terminalEnabled"
                    type="checkbox"
                    checked={notificationDraft.terminal_enabled}
                    onChange={() => void onToggleNotification("terminal_enabled")}
                  />
                </label>

                <div className="actions">
                  <button className="btn btn-soft" type="submit">
                    Save Notification Channels
                  </button>
                </div>
              </form>
            </article>
          </section>

          <section className="grid-two">
            <article className="panel">
              <header className="panel-header">
                <div>
                  <h3>Pricing Validation Interviews</h3>
                  <p>Track at least 5 developer interviews and lock launch pricing decision.</p>
                </div>
                <StatusPill value={state.pricingValidation?.launch_gate_passed ? "verified" : "warning"} />
              </header>

              <form className="field" onSubmit={onSavePricingValidation}>
                <label htmlFor="pricingModel">Selected Launch Model</label>
                <select
                  id="pricingModel"
                  value={pricingModelInput}
                  onChange={(event) => setPricingModelInput(event.target.value as "tiered" | "usage_based" | "undecided")}
                  disabled={Boolean(state.pricingValidation?.pricing_locked)}
                >
                  <option value="undecided">Undecided</option>
                  <option value="tiered">Tiered</option>
                  <option value="usage_based">Usage Based</option>
                </select>

                <label htmlFor="pricingRationale">Decision Rationale</label>
                <textarea
                  id="pricingRationale"
                  value={pricingRationaleInput}
                  onChange={(event) => setPricingRationaleInput(event.target.value)}
                  placeholder="Why this model best fits beta feedback"
                  disabled={Boolean(state.pricingValidation?.pricing_locked)}
                />

                <label htmlFor="pricingMigrationPath">Migration Path</label>
                <textarea
                  id="pricingMigrationPath"
                  value={pricingMigrationPathInput}
                  onChange={(event) => setPricingMigrationPathInput(event.target.value)}
                  placeholder="Post-launch pricing revision path"
                  disabled={Boolean(state.pricingValidation?.pricing_locked)}
                />

                <label htmlFor="pricingInterviews">Interview Notes JSON Array</label>
                <textarea
                  id="pricingInterviews"
                  value={pricingInterviewsInput}
                  onChange={(event) => setPricingInterviewsInput(event.target.value)}
                  placeholder='[{"developer_ref":"dev-a","preferred_model":"tiered","fairness_score":4.5,"call_volume_context":"50k/month","notes":"fair","interviewed_at":"2026-04-25T10:00:00Z"}]'
                  disabled={Boolean(state.pricingValidation?.pricing_locked)}
                />

                <label className="list-row" htmlFor="lockPricingDecision">
                  <span>Lock pricing decision</span>
                  <input
                    id="lockPricingDecision"
                    type="checkbox"
                    checked={lockPricingDecisionInput}
                    onChange={(event) => setLockPricingDecisionInput(event.target.checked)}
                    disabled={Boolean(state.pricingValidation?.pricing_locked)}
                  />
                </label>

                <div className="actions">
                  <button className="btn btn-primary" type="submit" disabled={Boolean(state.pricingValidation?.pricing_locked)}>
                    {state.pricingValidation?.pricing_locked ? "Pricing Locked" : "Save Pricing Validation"}
                  </button>
                </div>
              </form>

              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Interview Coverage</strong>
                    <span>
                      {state.pricingValidation?.unique_developer_count ?? 0} / {state.pricingValidation?.required_interviews ?? 5} unique beta developers
                    </span>
                  </div>
                  <StatusPill value={state.pricingValidation?.minimum_interviews_met ? "verified" : "warning"} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Missing Interviews</strong>
                    <span>{state.pricingValidation?.missing_interviews ?? 0}</span>
                  </div>
                  <StatusPill value={(state.pricingValidation?.missing_interviews ?? 0) === 0 ? "verified" : "warning"} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Decision Lock</strong>
                    <span>
                      {state.pricingValidation?.pricing_locked
                        ? `Locked at ${formatDateTime(state.pricingValidation.locked_at)}`
                        : "Unlocked"}
                    </span>
                  </div>
                  <StatusPill value={state.pricingValidation?.pricing_locked ? "verified" : "warning"} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Week 12 Pricing Gate</strong>
                    <span>{state.pricingValidation?.launch_gate_passed ? "Ready" : "Blocked"}</span>
                  </div>
                  <StatusPill value={state.pricingValidation?.launch_gate_passed ? "verified" : "warning"} />
                </div>
                {!state.pricingValidation?.launch_gate_passed && state.pricingValidation?.blockers?.length ? (
                  state.pricingValidation.blockers.map((blocker) => (
                    <div key={blocker} className="list-row">
                      <div className="list-main">
                        <strong>Blocker</strong>
                        <span>{blocker}</span>
                      </div>
                    </div>
                  ))
                ) : null}
              </div>
            </article>

            <article className="panel panel-muted">
              <header className="panel-header">
                <div>
                  <h3>Rollback Drill</h3>
                  <p>Track deploy + rollback test outcomes and failure simulation evidence.</p>
                </div>
                <StatusPill value={state.rollbackDrill?.status} />
              </header>

              <form className="field" onSubmit={onSaveRollbackDrill}>
                <label htmlFor="rollbackDeployRevision">Deploy Revision</label>
                <input
                  id="rollbackDeployRevision"
                  value={rollbackDeployRevisionInput}
                  onChange={(event) => setRollbackDeployRevisionInput(event.target.value)}
                  placeholder="railway-revision-123"
                />

                <label htmlFor="rollbackTargetRevision">Rollback Revision</label>
                <input
                  id="rollbackTargetRevision"
                  value={rollbackTargetRevisionInput}
                  onChange={(event) => setRollbackTargetRevisionInput(event.target.value)}
                  placeholder="railway-revision-122"
                />

                <div className="actions">
                  <button
                    type="button"
                    className="btn btn-soft"
                    onClick={() => void onRunRollbackVerification("deploy")}
                    disabled={rollbackVerificationRunningPhase !== null}
                  >
                    {rollbackVerificationRunningPhase === "deploy" ? "Verifying Deploy..." : "Run Deploy Verification"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-soft"
                    onClick={() => void onRunRollbackVerification("rollback")}
                    disabled={rollbackVerificationRunningPhase !== null}
                  >
                    {rollbackVerificationRunningPhase === "rollback" ? "Verifying Rollback..." : "Run Rollback Verification"}
                  </button>
                </div>

                {rollbackVerificationResult ? (
                  <div className="settings-inset">
                    <p className="hint">
                      Last verification: {rollbackVerificationResult.phase} ┬╖ {rollbackVerificationResult.passed ? "passed" : "failed"} ┬╖ {formatDateTime(rollbackVerificationResult.verified_at)}
                    </p>
                    <div className="list">
                      {rollbackVerificationResult.checks.map((check) => (
                        <div key={`${check.name}-${rollbackVerificationResult.verified_at}`} className="list-row">
                          <div className="list-main">
                            <strong>{check.name}</strong>
                            <span>{check.detail}</span>
                          </div>
                          <StatusPill value={check.status === "ok" ? "verified" : check.status === "failed" ? "failed" : "warning"} />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                <label htmlFor="rollbackStatus">Drill Status</label>
                <select
                  id="rollbackStatus"
                  value={rollbackStatusInput}
                  onChange={(event) => setRollbackStatusInput(event.target.value as "not_started" | "in_progress" | "passed" | "failed")}
                >
                  <option value="not_started">Not Started</option>
                  <option value="in_progress">In Progress</option>
                  <option value="passed" disabled={!state.pricingValidation?.launch_gate_passed}>Passed</option>
                  <option value="failed">Failed</option>
                </select>

                <label className="list-row" htmlFor="rollbackDeployPassed">
                  <span>Deploy test passed (automated)</span>
                  <input
                    id="rollbackDeployPassed"
                    type="checkbox"
                    checked={rollbackDeployPassedInput}
                    disabled
                  />
                </label>

                <label className="list-row" htmlFor="rollbackRollbackPassed">
                  <span>Rollback test passed (automated)</span>
                  <input
                    id="rollbackRollbackPassed"
                    type="checkbox"
                    checked={rollbackRollbackPassedInput}
                    disabled
                  />
                </label>

                <p className="hint">Deploy/Rollback test flags are updated by verification checks, not manual toggles.</p>

                <label className="list-row" htmlFor="rollbackFailureSimulation">
                  <span>Failure simulation performed</span>
                  <input
                    id="rollbackFailureSimulation"
                    type="checkbox"
                    checked={rollbackFailureSimulationInput}
                    onChange={(event) => setRollbackFailureSimulationInput(event.target.checked)}
                  />
                </label>

                <label htmlFor="rollbackFailureCategory">Failure Simulation Category</label>
                <select
                  id="rollbackFailureCategory"
                  value={rollbackFailureCategoryInput}
                  onChange={(event) => setRollbackFailureCategoryInput(event.target.value as "TOKEN_OVERFLOW" | "RATE_LIMIT" | "AUTH_FAILURE" | "LOOP_DETECTED" | "COST_SPIKE" | "")}
                  disabled={!rollbackFailureSimulationInput}
                >
                  <option value="">Select category</option>
                  <option value="TOKEN_OVERFLOW">TOKEN_OVERFLOW</option>
                  <option value="RATE_LIMIT">RATE_LIMIT</option>
                  <option value="AUTH_FAILURE">AUTH_FAILURE</option>
                  <option value="LOOP_DETECTED">LOOP_DETECTED</option>
                  <option value="COST_SPIKE">COST_SPIKE</option>
                </select>

                <label htmlFor="rollbackFailureNotes">Failure Simulation Notes</label>
                <textarea
                  id="rollbackFailureNotes"
                  value={rollbackFailureNotesInput}
                  onChange={(event) => setRollbackFailureNotesInput(event.target.value)}
                  placeholder="What failed, how it was detected, and mitigation proof"
                />

                <label htmlFor="rollbackDrillNotes">Rollback Drill Notes</label>
                <textarea
                  id="rollbackDrillNotes"
                  value={rollbackDrillNotesInput}
                  onChange={(event) => setRollbackDrillNotesInput(event.target.value)}
                  placeholder="Deployment and rollback observations"
                />

                <div className="actions">
                  <button className="btn btn-soft" type="submit">
                    Save Rollback Drill
                  </button>
                </div>
              </form>

              <div className="list">
                <div className="list-row">
                  <div className="list-main">
                    <strong>Status</strong>
                    <span>{safeString(state.rollbackDrill?.status, "not_started")}</span>
                  </div>
                  <StatusPill value={state.rollbackDrill?.status} />
                </div>
                <div className="list-row">
                  <div className="list-main">
                    <strong>Completed At</strong>
                    <span>{formatDateTime(state.rollbackDrill?.completed_at ?? null)}</span>
                  </div>
                </div>
              </div>
            </article>
          </section>

          <section className="panel">
            <header className="panel-header">
              <div>
                <h3>Provider Verification</h3>
                <p>Per-provider status and test connection.</p>
              </div>
            </header>

            <div className="list">
              {state.providers.length === 0 ? (
                <div className="empty">No provider telemetry yet. Trigger a few calls first.</div>
              ) : (
                state.providers.map((provider) => (
                  <div key={provider.provider} className="list-row">
                    <div className="list-main">
                      <strong>{provider.provider}</strong>
                      <span>
                        tracked calls: {provider.tracked_call_count} ┬╖ checked: {formatDateTime(provider.last_checked_at)}
                      </span>
                    </div>
                    <div className="actions">
                      <StatusPill value={provider.status} />
                      <button type="button" className="btn btn-soft" onClick={() => void onTestProvider(provider.provider)}>
                        Test Connection
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="panel panel-muted">
            <header className="panel-header">
              <div>
                <h3>Data Export</h3>
                <p>Download calls, diagnoses, and alerts for this project.</p>
              </div>
            </header>

            <div className="actions">
              <button type="button" className="btn btn-soft" onClick={() => void onExportData()} disabled={exporting}>
                {exporting ? "Preparing Export..." : "Download JSON Export"}
              </button>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
