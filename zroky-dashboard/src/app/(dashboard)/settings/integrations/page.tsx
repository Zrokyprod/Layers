"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, MessageSquare, RefreshCw, Send } from "lucide-react";

import { getSlackInstallStatus, getTeamsInstallStatus } from "@/lib/api";
import type { SlackInstallStatusResponse, TeamsInstallStatusResponse } from "@/lib/types";

type IntegrationState = {
  slack: SlackInstallStatusResponse | null;
  teams: TeamsInstallStatusResponse | null;
};

function integrationStatus(connected: boolean) {
  return connected ? "Connected" : "Not connected";
}

export default function IntegrationsSettingsPage() {
  const [state, setState] = useState<IntegrationState>({ slack: null, teams: null });
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const [slackResult, teamsResult] = await Promise.allSettled([
      getSlackInstallStatus(),
      getTeamsInstallStatus(),
    ]);

    setState({
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      teams: teamsResult.status === "fulfilled" ? teamsResult.value : null,
    });

    const failures = [slackResult, teamsResult].filter((result) => result.status === "rejected");
    if (failures.length > 0) {
      setMessage("Some integration status checks could not load. Verify backend connectivity and admin access.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const slackConnected = Boolean(state.slack?.connected);
  const teamsConnected = Boolean(state.teams?.connected);

  return (
    <div className="page-content settings-integrations-page">
      {message ? <div className="alert-strip alert-strip-error">{message}</div> : null}

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>Notification Integrations</h3>
            <p>Send Zroky alerts, replay failures, and reliability events to the channels your team already watches.</p>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
            <RefreshCw aria-hidden="true" />
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </header>
      </section>

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <MessageSquare aria-hidden="true" />
          <span>Slack</span>
          <strong>{slackConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.slack?.channel_name ? `#${state.slack.channel_name}` : "OAuth install required before alerts deliver."}</small>
        </article>
        <article className="panel settings-summary-card">
          <Send aria-hidden="true" />
          <span>Microsoft Teams</span>
          <strong>{teamsConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.teams?.channel_name || "Webhook storage required before alerts deliver."}</small>
        </article>
        <article className="panel settings-summary-card">
          <CheckCircle2 aria-hidden="true" />
          <span>Delivery ready</span>
          <strong>{[slackConnected, teamsConnected].filter(Boolean).length}/2</strong>
          <small>Connected channels can receive test messages.</small>
        </article>
        <article className="panel settings-summary-card">
          <AlertTriangle aria-hidden="true" />
          <span>Config gated</span>
          <strong>{message ? "Check backend" : "No errors"}</strong>
          <small>{message || "Status endpoints responded."}</small>
        </article>
      </section>

      <section className="settings-integration-grid">
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
                <span>{state.slack?.team_name ?? state.slack?.team_id ?? "-"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Channel</strong>
                <span>{state.slack?.channel_name ? `#${state.slack.channel_name}` : state.slack?.channel_id ?? "-"}</span>
              </div>
            </div>
          </div>

          <div className="actions">
            <Link href="/settings/integrations/slack" className="btn btn-primary">
              Manage Slack
            </Link>
          </div>
        </article>

        <article className="panel settings-integration-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <Send aria-hidden="true" />
              <div>
                <h3>Microsoft Teams</h3>
                <p>Incoming webhook storage, channel label, disconnect, and test-message support.</p>
              </div>
            </div>
            <span className={teamsConnected ? "pill pill-green" : "pill"}>
              {integrationStatus(teamsConnected)}
            </span>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Channel</strong>
                <span>{state.teams?.channel_name || "-"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Connector</strong>
                <span>{state.teams?.connector_type ?? "-"}</span>
              </div>
            </div>
          </div>

          <div className="actions">
            <Link href="/settings/integrations/teams" className="btn btn-primary">
              Manage Teams
            </Link>
          </div>
        </article>
      </section>
    </div>
  );
}
