"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import {
  disconnectTeamsInstall,
  getTeamsInstallStatus,
  sendTeamsTestMessage,
  upsertTeamsInstall,
} from "@/lib/api";
import type { TeamsInstallStatusResponse } from "@/lib/types";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function isConfigProblem(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("not configured") || text.includes("unavailable") || text.includes("failed") || text.includes("disabled");
}

export default function TeamsIntegrationPage() {
  const [status, setStatus] = useState<TeamsInstallStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [channelName, setChannelName] = useState("");
  const [testText, setTestText] = useState("Zroky test alert: Microsoft Teams integration is connected.");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const next = await getTeamsInstallStatus();
      setStatus(next);
      setChannelName(next.channel_name ?? "");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load Microsoft Teams integration.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveTeams() {
    setWorking(true);
    setMessage("");
    try {
      const next = await upsertTeamsInstall({
        webhook_url: webhookUrl,
        channel_name: channelName || null,
      });
      setStatus(next);
      setWebhookUrl("");
      setMessage("Microsoft Teams connected for this project.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save Microsoft Teams webhook.");
    } finally {
      setWorking(false);
    }
  }

  async function disconnectTeams() {
    setWorking(true);
    setMessage("");
    try {
      const next = await disconnectTeamsInstall();
      setStatus(next);
      setMessage("Microsoft Teams disconnected for this project.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to disconnect Microsoft Teams.");
    } finally {
      setWorking(false);
    }
  }

  async function testTeams() {
    setWorking(true);
    setMessage("");
    try {
      const response = await sendTeamsTestMessage(testText);
      setMessage(response.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to send Microsoft Teams test message.");
    } finally {
      setWorking(false);
    }
  }

  const connected = Boolean(status?.connected);
  const problemMessage = message && isConfigProblem(message);

  return (
    <div className="page-stack">
      <section className="panel settings-hero-panel">
        <div>
          <p className="eyebrow">Integrations</p>
          <h2>Microsoft Teams</h2>
          <p className="hint">Connect a Teams incoming webhook so Zroky can send alerts, replay failures, and reliability events into your team channel.</p>
        </div>
        <Link className="btn btn-soft" href="/settings/integrations">Back to integrations</Link>
      </section>

      {message ? <div className={problemMessage ? "alert-strip alert-strip-error" : "alert-strip"}>{message}</div> : null}

      <section className="grid-two">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Channel connection</h3>
              <p>{connected ? "Microsoft Teams is connected for this project." : "Paste an incoming webhook URL from your Teams channel."}</p>
            </div>
            <span className={connected ? "pill pill-green" : "pill"}>{connected ? "Connected" : "Not connected"}</span>
          </header>

          {loading ? <p className="hint">Loading Microsoft Teams status...</p> : null}
          {!loading && problemMessage ? (
            <div className="settings-config-warning" role="status">
              <AlertTriangle aria-hidden="true" />
              <div>
                <strong>Teams webhook storage is not ready in this environment.</strong>
                <span>{message}</span>
              </div>
            </div>
          ) : null}

          {!loading && (
            <div className="list">
              <div className="list-row">
                <div className="list-main">
                  <strong>Channel</strong>
                  <span>{status?.channel_name || "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Connector</strong>
                  <span>{status?.connector_type ?? "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Installed by</strong>
                  <span>{status?.installed_by_user ?? "-"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Installed at</strong>
                  <span>{formatDate(status?.installed_at ?? null)}</span>
                </div>
              </div>
            </div>
          )}

          <div className="field">
            <label htmlFor="teamsWebhookUrl">Incoming Webhook URL</label>
            <input
              id="teamsWebhookUrl"
              type="password"
              value={webhookUrl}
              onChange={(event) => setWebhookUrl(event.target.value)}
              placeholder="https://...webhook.office.com/..."
              disabled={working}
            />
          </div>
          <div className="field">
            <label htmlFor="teamsChannelName">Channel Label</label>
            <input
              id="teamsChannelName"
              value={channelName}
              onChange={(event) => setChannelName(event.target.value)}
              placeholder="Reliability alerts"
              disabled={working}
            />
          </div>

          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={() => void saveTeams()} disabled={working || !webhookUrl.trim()}>
              {connected ? "Update Teams Webhook" : "Connect Teams"}
            </button>
            {connected ? (
              <button className="btn btn-danger" type="button" onClick={() => void disconnectTeams()} disabled={working}>
                Disconnect
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Test notification</h3>
              <p>Send a test message to confirm the selected Teams channel is receiving Zroky events.</p>
            </div>
          </header>
          <div className="field">
            <label htmlFor="teamsTestText">Message</label>
            <textarea
              id="teamsTestText"
              value={testText}
              onChange={(event) => setTestText(event.target.value)}
              disabled={!connected || working}
            />
          </div>
          <div className="actions">
            <button className="btn btn-soft" type="button" onClick={() => void testTeams()} disabled={!connected || working}>
              Send Test Message
            </button>
          </div>
          <p className="hint">The webhook URL is encrypted at rest and never shown again after save.</p>
        </article>
      </section>
    </div>
  );
}
