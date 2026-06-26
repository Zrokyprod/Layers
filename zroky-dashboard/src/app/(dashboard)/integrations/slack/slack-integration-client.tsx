"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  PlugZap,
  RefreshCw,
  Send,
  ShieldCheck,
  Unplug,
} from "lucide-react";

import {
  disconnectSlackInstall,
  getSlackInstallStatus,
  listAlerts,
  sendSlackTestMessage,
  startSlackInstall,
} from "@/lib/api";
import type { AlertItemResponse, SlackInstallStatusResponse } from "@/lib/types";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatChannel(status: SlackInstallStatusResponse | null): string {
  if (!status?.connected) return "Not connected";
  const channel = status.channel_name
    ? status.channel_name.startsWith("#")
      ? status.channel_name
      : `#${status.channel_name}`
    : status.channel_id ?? "Slack channel";
  return status.team_name ? `${status.team_name} / ${channel}` : channel;
}

function isConfigProblem(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("not configured") || text.includes("unavailable") || text.includes("failed") || text.includes("disabled");
}

function slackNotificationSummary(alerts: AlertItemResponse[]) {
  const actionable = alerts.filter((alert) => ["critical", "high"].includes(alert.severity.toLowerCase()));
  const sent = actionable.filter((alert) => alert.slack_delivery_status === "sent").length;
  const failed = actionable.filter((alert) => alert.slack_delivery_status === "failed").length;
  const missing = actionable.filter((alert) => alert.slack_delivery_status === "not_connected").length;
  const pending = actionable.filter((alert) => alert.slack_delivery_status === "not_attempted").length;
  const retryNeeded = failed + missing;
  const lastAttempt = actionable
    .map((alert) => alert.slack_delivery_attempted_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;

  let verdict = "No Slack alerts sent yet";
  let detail = "High and critical alerts will appear here after they fire.";
  let tone: "ok" | "warning" | "danger" | "neutral" = "neutral";
  if (retryNeeded > 0) {
    verdict = `${retryNeeded} alert${retryNeeded === 1 ? "" : "s"} needs retry`;
    detail = "Open the alert detail to resend it to Slack.";
    tone = "warning";
  } else if (sent > 0) {
    verdict = lastAttempt ? `Last alert sent ${formatDate(lastAttempt)}` : `${sent} alert${sent === 1 ? "" : "s"} sent`;
    detail = "Slack is receiving automatic alert notifications.";
    tone = "ok";
  } else if (pending > 0) {
    verdict = `${pending} alert${pending === 1 ? "" : "s"} waiting to send`;
    detail = "The backend has queued Slack notification.";
    tone = "warning";
  }

  return { failed, missing, pending, retryNeeded, verdict, detail, tone };
}

export default function SlackIntegrationPage() {
  const [status, setStatus] = useState<SlackInstallStatusResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertItemResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [testText, setTestText] = useState("Zroky test alert: Slack integration is connected.");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const [nextStatus, nextAlerts] = await Promise.all([
        getSlackInstallStatus(),
        listAlerts({ limit: 100 }),
      ]);
      setStatus(nextStatus);
      setAlerts(nextAlerts.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load Slack integration.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function connectSlack() {
    setWorking(true);
    setMessage("");
    try {
      const response = await startSlackInstall();
      window.location.href = response.authorization_url;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to start Slack OAuth.");
      setWorking(false);
    }
  }

  async function disconnectSlack() {
    setWorking(true);
    setMessage("");
    try {
      const next = await disconnectSlackInstall();
      setStatus(next);
      setMessage("Slack disconnected for this project.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to disconnect Slack.");
    } finally {
      setWorking(false);
    }
  }

  async function testSlack() {
    setWorking(true);
    setMessage("");
    try {
      const response = await sendSlackTestMessage(testText);
      setMessage(response.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to send Slack test message.");
    } finally {
      setWorking(false);
    }
  }

  const connected = Boolean(status?.connected);
  const problemMessage = message && isConfigProblem(message);
  const summary = useMemo(() => slackNotificationSummary(alerts), [alerts]);

  return (
    <div className="page-stack slack-proof-page">
      <section className="panel settings-hero-panel slack-proof-hero">
        <div>
          <p className="eyebrow">Integrations</p>
          <h2>Slack notifications</h2>
          <p className="hint">
            Connect a Slack channel and Zroky will send high and critical alerts automatically.
          </p>
        </div>
        <div className="slack-proof-hero-actions">
          <button className="btn btn-soft" type="button" onClick={() => void load()} disabled={loading || working}>
            <RefreshCw aria-hidden="true" />
            Refresh status
          </button>
          <Link className="btn btn-soft" href="/integrations">Back to connectors</Link>
        </div>
      </section>

      {message ? <div className={problemMessage ? "alert-strip alert-strip-error" : "alert-strip"}>{message}</div> : null}

      <section className="slack-proof-grid" aria-label="Slack notification summary">
        <article className="panel slack-proof-card">
          <span className={connected ? "slack-proof-icon is-ok" : "slack-proof-icon is-warning"}>
            {connected ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
          </span>
          <div>
            <span>Connection</span>
            <strong>{connected ? "Slack connected" : "Slack not connected"}</strong>
            <small>{formatChannel(status)}</small>
          </div>
        </article>
        <article className="panel slack-proof-card">
          <span className="slack-proof-icon is-ok">
            <ShieldCheck aria-hidden="true" />
          </span>
          <div>
            <span>Auto-send rule</span>
            <strong>High and critical alerts auto-send</strong>
            <small>No manual step is needed after Slack is connected.</small>
          </div>
        </article>
        <article className="panel slack-proof-card">
          <span className={`slack-proof-icon is-${summary.tone}`}>
            <Send aria-hidden="true" />
          </span>
          <div>
            <span>Recent activity</span>
            <strong>{connected ? summary.verdict : "Connect Slack to start"}</strong>
            <small>{connected ? summary.detail : "No alerts are sent until a channel is connected."}</small>
          </div>
        </article>
      </section>

      <section className="grid-two slack-proof-main">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Connected channel</h3>
              <p>{connected ? "Alerts will be sent to this Slack destination." : "Choose where high and critical alerts should be sent."}</p>
            </div>
            <span className={connected ? "pill pill-green" : "pill"}>{connected ? "Connected" : "Not connected"}</span>
          </header>

          {loading ? <p className="hint">Loading Slack status...</p> : null}
          {!loading && problemMessage ? (
            <div className="settings-config-warning" role="status">
              <AlertTriangle aria-hidden="true" />
              <div>
                <strong>Slack OAuth is not ready in this environment.</strong>
                <span>{message}</span>
              </div>
            </div>
          ) : null}

          {!loading && (
            <div className="list">
              <div className="list-row">
                <div className="list-main">
                  <strong>Workspace</strong>
                  <span>{status?.team_name ?? status?.team_id ?? "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Channel</strong>
                  <span>{status?.channel_name ? `#${status.channel_name}` : status?.channel_id ?? "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Connected by</strong>
                  <span>{status?.installed_by_user ?? "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Connected at</strong>
                  <span>{formatDate(status?.installed_at ?? null)}</span>
                </div>
              </div>
            </div>
          )}

          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={() => void connectSlack()} disabled={working}>
              <PlugZap aria-hidden="true" />
              {connected ? "Reconnect Slack" : "Connect Slack"}
            </button>
            {connected ? (
              <button className="btn btn-danger" type="button" onClick={() => void disconnectSlack()} disabled={working}>
                <Unplug aria-hidden="true" />
                Disconnect
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Test message</h3>
              <p>Send a real message to confirm the selected channel.</p>
            </div>
          </header>

          <div className="field">
            <label htmlFor="slackTestText">Message</label>
            <textarea
              id="slackTestText"
              value={testText}
              onChange={(event) => setTestText(event.target.value)}
              disabled={!connected || working}
            />
          </div>
          <div className="actions">
            <button className="btn btn-soft" type="button" onClick={() => void testSlack()} disabled={!connected || working}>
              <Send aria-hidden="true" />
              Send test message
            </button>
          </div>
          <p className="hint">
            {summary.retryNeeded > 0
              ? "Some alerts were not sent. Open Alerts to retry from the alert detail drawer."
              : "High and critical alerts are automatic after Slack is connected."}
          </p>
        </article>
      </section>
    </div>
  );
}
