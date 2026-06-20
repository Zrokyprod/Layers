"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Copy,
  DatabaseZap,
  GitPullRequest,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  Save,
} from "lucide-react";

import {
  disconnectGithubRepoConnection,
  getGithubConnectionStatus,
  getLedgerRefundConnectorStatus,
  getSlackInstallStatus,
  listOutcomeReconciliations,
  saveLedgerRefundConnectorConfig,
  testLedgerRefundConnector,
  type LedgerRefundConnectorStatusResponse,
  type OutcomeReconciliationView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
} from "@/lib/types";

type IntegrationState = {
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  ledgerConfig: LedgerRefundConnectorStatusResponse | null;
  outcomeChecks: OutcomeReconciliationView[];
};

type LedgerConnectorForm = {
  baseUrl: string;
  pathTemplate: string;
  recordPath: string;
  bearerToken: string;
  testRefundId: string;
  testAmountUsd: string;
  testCurrency: string;
  testStatus: string;
};

const defaultLedgerForm: LedgerConnectorForm = {
  baseUrl: "",
  pathTemplate: "/refunds/{refund_id}",
  recordPath: "data",
  bearerToken: "",
  testRefundId: "",
  testAmountUsd: "42.50",
  testCurrency: "USD",
  testStatus: "posted",
};

function integrationStatus(connected: boolean) {
  return connected ? "Connected" : "Not connected";
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("could not") || text.includes("error");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function connectorMetadata(item: OutcomeReconciliationView | null): Record<string, unknown> {
  if (!item || !isRecord(item.metadata)) return {};
  const connector = item.metadata.connector;
  return isRecord(connector) ? connector : {};
}

function textValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function isLedgerRefundCheck(item: OutcomeReconciliationView) {
  const metadata = isRecord(item.metadata) ? item.metadata : {};
  return item.connector_type === "ledger_refund_api" || metadata.connector_kind === "ledger_refund_api";
}

function connectorStatus(check: OutcomeReconciliationView | null) {
  if (!check) return "No proof yet";
  if (check.verdict === "matched") return "Verified";
  if (check.verdict === "mismatched") return "Mismatch";
  return "Not verified";
}

function connectorPillClass(check: OutcomeReconciliationView | null) {
  if (!check) return "pill";
  if (check.verdict === "matched") return "pill pill-green";
  if (check.verdict === "mismatched") return "pill pill-red";
  return "pill pill-yellow";
}

function maskHost(hostname: string) {
  const parts = hostname.split(".").filter(Boolean);
  if (parts.length <= 1) return "masked-host";
  return `${parts[0]}.***`;
}

function maskedConnectorUrl(value: unknown) {
  const raw = textValue(value);
  if (!raw) return "Waiting for first check";
  try {
    const url = new URL(raw);
    return `${url.protocol}//${maskHost(url.hostname)}/...`;
  } catch {
    return "Masked connector URL";
  }
}

function ledgerRefundPayloadSnippet() {
  return `curl -X POST "$ZROKY_API_BASE/v1/outcomes/reconciliation/ledger-refund" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "call_id": "call_refund_123",
    "trace_id": "trace_refund_123",
    "action_type": "refund",
    "refund_id": "RF-1001",
    "claimed": {
      "refund_id": "RF-1001",
      "amount_usd": 42.18,
      "currency": "USD",
      "status": "posted"
    },
    "match_fields": ["refund_id", "amount_usd", "currency", "status"],
    "connector": {
      "base_url": "https://ledger.example.com/api",
      "path_template": "/refunds/{refund_id}",
      "record_path": "data",
      "bearer_token": "$LEDGER_TOKEN"
    }
  }'`;
}

function formFromLedgerConfig(
  config: LedgerRefundConnectorStatusResponse | null,
  previous: LedgerConnectorForm,
): LedgerConnectorForm {
  if (!config?.connected) return previous;
  return {
    ...previous,
    baseUrl: config.base_url ?? previous.baseUrl,
    pathTemplate: config.path_template ?? previous.pathTemplate,
    recordPath: config.record_path ?? previous.recordPath,
    bearerToken: "",
  };
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export default function IntegrationsSettingsPage() {
  const [state, setState] = useState<IntegrationState>({
    github: null,
    slack: null,
    ledgerConfig: null,
    outcomeChecks: [],
  });
  const [ledgerForm, setLedgerForm] = useState<LedgerConnectorForm>(defaultLedgerForm);
  const [loading, setLoading] = useState(true);
  const [savingLedger, setSavingLedger] = useState(false);
  const [testingLedger, setTestingLedger] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const [githubResult, slackResult, ledgerConfigResult, outcomeResult] = await Promise.allSettled([
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
      getLedgerRefundConnectorStatus(),
      listOutcomeReconciliations({ limit: 25 }),
    ]);
    const ledgerConfig = ledgerConfigResult.status === "fulfilled" ? ledgerConfigResult.value : null;

    setState({
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      ledgerConfig,
      outcomeChecks: outcomeResult.status === "fulfilled" ? outcomeResult.value.items : [],
    });
    setLedgerForm((prev) => formFromLedgerConfig(ledgerConfig, prev));

    const failures = [githubResult, slackResult, ledgerConfigResult, outcomeResult].filter((result) => result.status === "rejected");
    if (failures.length > 0) {
      setMessage("Some integration status checks could not load. Verify backend connectivity and admin access.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const githubConnected = Boolean(state.github?.connected);
  const slackConnected = Boolean(state.slack?.connected);
  const ledgerConnected = Boolean(state.ledgerConfig?.connected);
  const ledgerRefundChecks = state.outcomeChecks.filter(isLedgerRefundCheck);
  const latestLedgerRefundCheck = ledgerRefundChecks[0] ?? null;
  const ledgerMetadata = connectorMetadata(latestLedgerRefundCheck);
  const ledgerVerified = latestLedgerRefundCheck?.verdict === "matched";
  const readyCount = [githubConnected, slackConnected, ledgerConnected && ledgerVerified].filter(Boolean).length;
  const ledgerHttpStatus = textValue(ledgerMetadata.http_status);
  const ledgerRecordPath = state.ledgerConfig?.record_path ?? textValue(ledgerMetadata.record_path);
  const ledgerRequestUrl = maskedConnectorUrl(state.ledgerConfig?.base_url ?? ledgerMetadata.request_url);
  const ledgerLastChecked = latestLedgerRefundCheck?.checked_at
    ? formatDateTime(latestLedgerRefundCheck.checked_at)
    : state.ledgerConfig?.last_tested_at
      ? formatDateTime(state.ledgerConfig.last_tested_at)
      : "Waiting for first check";
  const tokenStatus = state.ledgerConfig?.has_bearer_token
    ? `Stored token ending ${state.ledgerConfig.bearer_token_last4 ?? "****"}`
    : "No bearer token stored";

  function onStartGithubConnect() {
    window.location.href = "/api/zroky/v1/settings/github/connect/start";
  }

  async function copyLedgerPayload() {
    try {
      await navigator.clipboard.writeText(ledgerRefundPayloadSnippet());
      setMessage("Ledger refund reconciliation payload copied.");
    } catch {
      setMessage("Copy failed. Select the payload and copy it manually.");
    }
  }

  function updateLedgerForm(field: keyof LedgerConnectorForm, value: string) {
    setLedgerForm((prev) => ({ ...prev, [field]: value }));
  }

  async function onSaveLedgerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setSavingLedger(true);
    try {
      const updated = await saveLedgerRefundConnectorConfig({
        base_url: ledgerForm.baseUrl.trim(),
        path_template: ledgerForm.pathTemplate.trim() || "/refunds/{refund_id}",
        record_path: optionalText(ledgerForm.recordPath),
        bearer_token: optionalText(ledgerForm.bearerToken),
      });
      setState((prev) => ({ ...prev, ledgerConfig: updated }));
      setLedgerForm((prev) => formFromLedgerConfig(updated, { ...prev, bearerToken: "" }));
      setMessage("Ledger refund connector saved.");
    } catch (saveError) {
      setMessage(saveError instanceof Error ? saveError.message : "Failed to save ledger refund connector.");
    } finally {
      setSavingLedger(false);
    }
  }

  async function onTestLedgerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setTestingLedger(true);
    const refundId = ledgerForm.testRefundId.trim();
    const amountText = ledgerForm.testAmountUsd.trim();
    const amountUsd = amountText ? Number(amountText) : null;
    const claimed: Record<string, unknown> = { refund_id: refundId };
    if (amountUsd !== null && Number.isFinite(amountUsd)) claimed.amount_usd = amountUsd;
    if (ledgerForm.testCurrency.trim()) claimed.currency = ledgerForm.testCurrency.trim().toUpperCase();
    if (ledgerForm.testStatus.trim()) claimed.status = ledgerForm.testStatus.trim();

    try {
      const result = await testLedgerRefundConnector({
        refund_id: refundId,
        claimed,
        amount_usd: amountUsd !== null && Number.isFinite(amountUsd) ? amountUsd : null,
        currency: ledgerForm.testCurrency.trim() ? ledgerForm.testCurrency.trim().toUpperCase() : null,
        match_fields: Object.keys(claimed),
      });
      setState((prev) => ({
        ...prev,
        ledgerConfig: result.connector,
        outcomeChecks: [
          result.check,
          ...prev.outcomeChecks.filter((item) => item.id !== result.check.id),
        ].slice(0, 25),
      }));
      setMessage(`Ledger refund test recorded ${result.check.verdict}.`);
    } catch (testError) {
      setMessage(testError instanceof Error ? testError.message : "Failed to run ledger refund test.");
    } finally {
      setTestingLedger(false);
    }
  }

  async function onDisconnectGithub() {
    setMessage("");
    try {
      const updated = await disconnectGithubRepoConnection();
      setState((prev) => ({ ...prev, github: updated }));
      setMessage("GitHub connection removed.");
    } catch (disconnectError) {
      setMessage(disconnectError instanceof Error ? disconnectError.message : "Failed to disconnect GitHub.");
    }
  }

  return (
    <div className="page-content settings-integrations-page">
      {message ? (
        <div className={isProblemMessage(message) ? "alert-strip alert-strip-error" : "alert-strip"}>
          {message}
        </div>
      ) : null}

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>Integrations</h3>
            <p>Connect source control for fix PRs and delivery channels for reliability alerts.</p>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
            <RefreshCw aria-hidden="true" />
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </header>
      </section>

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <GitPullRequest aria-hidden="true" />
          <span>GitHub</span>
          <strong>{githubConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.github?.github_login ? `@${state.github.github_login}` : "Connect GitHub before generated fix PRs."}</small>
        </article>
        <article className="panel settings-summary-card">
          <MessageSquare aria-hidden="true" />
          <span>Slack</span>
          <strong>{slackConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.slack?.channel_name ? `#${state.slack.channel_name}` : "OAuth install required before alerts deliver."}</small>
        </article>
        <article className="panel settings-summary-card">
          <CheckCircle2 aria-hidden="true" />
          <span>Ready</span>
          <strong>{readyCount}/3</strong>
          <small>Connected integrations can create PRs, deliver alerts, or prove outcomes.</small>
        </article>
        <article className="panel settings-summary-card">
          <DatabaseZap aria-hidden="true" />
            <span>Outcome proof</span>
          <strong>{ledgerConnected ? connectorStatus(latestLedgerRefundCheck) : "Not configured"}</strong>
          <small>{ledgerConnected ? `Last checked ${ledgerLastChecked}` : "Save a connector before running proof."}</small>
        </article>
      </section>

      <section className="settings-integration-grid">
        <article className="panel settings-integration-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <GitPullRequest aria-hidden="true" />
              <div>
                <h3>GitHub</h3>
                <p>Repository access for generated fix pull requests and source-linked reliability work.</p>
              </div>
            </div>
            <span className={githubConnected ? "pill pill-green" : "pill"}>
              {integrationStatus(githubConnected)}
            </span>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Account</strong>
                <span>{state.github?.github_login ? `@${state.github.github_login}` : "Not connected"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Scopes</strong>
                <span>{state.github?.scopes?.length ? state.github.scopes.join(", ") : "Connect to grant repository access."}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Updated</strong>
                <span>
                  {state.github?.updated_at
                    ? formatDateTime(state.github.updated_at)
                    : state.github?.connected_at
                      ? formatDateTime(state.github.connected_at)
                      : "Waiting for connection"}
                </span>
              </div>
            </div>
          </div>

          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={onStartGithubConnect}>
              {githubConnected ? "Reconnect GitHub" : "Connect GitHub"}
            </button>
            {githubConnected ? (
              <button type="button" className="btn btn-soft" onClick={() => void onDisconnectGithub()}>
                Disconnect
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel settings-integration-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <MessageSquare aria-hidden="true" />
              <div>
                <h3>Slack</h3>
                <p>OAuth app install with workspace, channel, scopes, and test-message support.</p>
              </div>
            </div>
            <span className={slackConnected ? "pill pill-green" : "pill"}>
              {integrationStatus(slackConnected)}
            </span>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Workspace</strong>
                <span>{state.slack?.team_name ?? state.slack?.team_id ?? "Not connected"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Channel</strong>
                <span>{state.slack?.channel_name ? `#${state.slack.channel_name}` : state.slack?.channel_id ?? "Not configured"}</span>
              </div>
            </div>
          </div>

          <div className="actions">
            <Link href="/settings/integrations/slack" className="btn btn-primary">
              Manage Slack
            </Link>
          </div>
        </article>

        <article className="panel settings-integration-card settings-connector-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <DatabaseZap aria-hidden="true" />
              <div>
                <h3>Ledger refund connector</h3>
                <p>System-of-record proof for refund agents and money-touching workflows.</p>
              </div>
            </div>
            <span className={ledgerConnected ? connectorPillClass(latestLedgerRefundCheck) : "pill"}>
              {ledgerConnected ? connectorStatus(latestLedgerRefundCheck) : "Not configured"}
            </span>
          </header>

          <div className="settings-connector-facts" aria-label="Ledger refund connector status">
            <div>
              <span>Masked endpoint</span>
              <strong>{ledgerRequestUrl}</strong>
            </div>
            <div>
              <span>Last HTTP</span>
              <strong>{ledgerHttpStatus ?? "No response yet"}</strong>
            </div>
            <div>
              <span>Record path</span>
              <strong>{ledgerRecordPath ?? "data or data.0"}</strong>
            </div>
            <div>
              <span>Token</span>
              <strong>{tokenStatus}</strong>
            </div>
          </div>

          <form className="settings-connector-form" onSubmit={(event) => void onSaveLedgerConnector(event)}>
            <div className="settings-connector-form-grid">
              <label>
                <span>Base URL</span>
                <input
                  value={ledgerForm.baseUrl}
                  onChange={(event) => updateLedgerForm("baseUrl", event.target.value)}
                  placeholder="https://ledger.example.com/api"
                  required
                />
              </label>
              <label>
                <span>Path template</span>
                <input
                  value={ledgerForm.pathTemplate}
                  onChange={(event) => updateLedgerForm("pathTemplate", event.target.value)}
                  placeholder="/refunds/{refund_id}"
                  required
                />
              </label>
              <label>
                <span>Record path</span>
                <input
                  value={ledgerForm.recordPath}
                  onChange={(event) => updateLedgerForm("recordPath", event.target.value)}
                  placeholder="data"
                />
              </label>
              <label>
                <span>Bearer token</span>
                <input
                  type="password"
                  value={ledgerForm.bearerToken}
                  onChange={(event) => updateLedgerForm("bearerToken", event.target.value)}
                  placeholder={state.ledgerConfig?.has_bearer_token ? "Paste to rotate stored token" : "Optional bearer token"}
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={savingLedger || !ledgerForm.baseUrl.trim()}>
                <Save aria-hidden="true" />
                {savingLedger ? "Saving..." : "Save connector"}
              </button>
            </div>
          </form>

          <form className="settings-connector-test" onSubmit={(event) => void onTestLedgerConnector(event)}>
            <div className="settings-connector-test-grid">
              <label>
                <span>Refund ID</span>
                <input
                  value={ledgerForm.testRefundId}
                  onChange={(event) => updateLedgerForm("testRefundId", event.target.value)}
                  placeholder="RF-1001"
                  required
                />
              </label>
              <label>
                <span>Amount USD</span>
                <input
                  inputMode="decimal"
                  value={ledgerForm.testAmountUsd}
                  onChange={(event) => updateLedgerForm("testAmountUsd", event.target.value)}
                  placeholder="42.50"
                />
              </label>
              <label>
                <span>Currency</span>
                <input
                  value={ledgerForm.testCurrency}
                  onChange={(event) => updateLedgerForm("testCurrency", event.target.value)}
                  placeholder="USD"
                />
              </label>
              <label>
                <span>Status</span>
                <input
                  value={ledgerForm.testStatus}
                  onChange={(event) => updateLedgerForm("testStatus", event.target.value)}
                  placeholder="posted"
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-soft" disabled={!ledgerConnected || testingLedger || !ledgerForm.testRefundId.trim()}>
                <PlayCircle aria-hidden="true" />
                {testingLedger ? "Running..." : "Run test reconciliation"}
              </button>
            </div>
          </form>

          <div className="list settings-connector-proof">
            <div className="list-row">
              <div className="list-main">
                <strong>System reference</strong>
                <span>{latestLedgerRefundCheck?.system_ref ?? "Run the first reconciliation to link a ledger record."}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Last verdict</strong>
                <span>{latestLedgerRefundCheck?.verdict ?? "not_verified"}</span>
              </div>
            </div>
          </div>

          <pre className="settings-connector-payload" aria-label="Ledger refund reconciliation payload">
            <code>{ledgerRefundPayloadSnippet()}</code>
          </pre>

          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void copyLedgerPayload()}>
              <Copy aria-hidden="true" />
              Copy API payload
            </button>
            <Link href="/outcomes" className="btn btn-primary">
              View outcome checks
            </Link>
          </div>
        </article>

      </section>

    </div>
  );
}
