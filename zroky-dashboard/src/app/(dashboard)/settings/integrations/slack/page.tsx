"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  disconnectSlackInstall,
  getSlackInstallStatus,
  sendSlackTestMessage,
  startSlackInstall,
} from "@/lib/api";
import type { SlackInstallStatusResponse } from "@/lib/types";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function SlackIntegrationPage() {
  const [status, setStatus] = useState<SlackInstallStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [testText, setTestText] = useState("Zroky test alert: Slack integration is connected.");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      setStatus(await getSlackInstallStatus());
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

  return (
    <div className="page-stack">
      <section className="panel settings-hero-panel">
        <div>
          <p className="eyebrow">Integrations</p>
          <h2>Slack</h2>
          <p className="hint">Connect your workspace so Zroky can send alerts, replay failures, and reliability events into the right incident channel.</p>
        </div>
        <Link className="btn btn-soft" href="/settings">Back to settings</Link>
      </section>

      {message ? <div className="alert-strip">{message}</div> : null}

      <section className="grid-two">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Workspace connection</h3>
              <p>{connected ? "Slack is connected for this project." : "Install the Zroky Slack app for this project."}</p>
            </div>
            <span className={connected ? "pill pill-success" : "pill"}>{connected ? "Connected" : "Not connected"}</span>
          </header>

          {loading ? <p className="hint">Loading Slack status…</p> : null}

          {!loading && (
            <div className="list">
              <div className="list-row">
                <div className="list-main">
                  <strong>Workspace</strong>
                  <span>{status?.team_name ?? status?.team_id ?? "—"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Channel</strong>
                  <span>{status?.channel_name ? `#${status.channel_name}` : status?.channel_id ?? "—"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Installed by</strong>
                  <span>{status?.installed_by_user ?? "—"}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Installed at</strong>
                  <span>{formatDate(status?.installed_at ?? null)}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Scopes</strong>
                  <span>{status?.scopes.length ? status.scopes.join(", ") : "—"}</span>
                </div>
              </div>
            </div>
          )}

          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={() => void connectSlack()} disabled={working}>
              {connected ? "Reconnect Slack" : "Connect Slack"}
            </button>
            {connected ? (
              <button className="btn btn-danger" type="button" onClick={() => void disconnectSlack()} disabled={working}>
                Disconnect
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Test notification</h3>
              <p>Send a test message to confirm the selected Slack channel is receiving Zroky events.</p>
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
              Send Test Message
            </button>
          </div>
          <p className="hint">Slack alerts also respect the Slack channel toggle on the main Settings page.</p>
        </article>
      </section>
    </div>
  );
}
