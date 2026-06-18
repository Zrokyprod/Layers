"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, GitPullRequest, MessageSquare, RefreshCw, Send } from "lucide-react";

import {
  disconnectGithubRepoConnection,
  getGithubConnectionStatus,
  getSlackInstallStatus,
  getTeamsInstallStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
  TeamsInstallStatusResponse,
} from "@/lib/types";

type IntegrationState = {
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  teams: TeamsInstallStatusResponse | null;
};

function integrationStatus(connected: boolean) {
  return connected ? "Connected" : "Not connected";
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("could not") || text.includes("error");
}

export default function IntegrationsSettingsPage() {
  const [state, setState] = useState<IntegrationState>({ github: null, slack: null, teams: null });
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const [githubResult, slackResult, teamsResult] = await Promise.allSettled([
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
      getTeamsInstallStatus(),
    ]);

    setState({
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      teams: teamsResult.status === "fulfilled" ? teamsResult.value : null,
    });

    const failures = [githubResult, slackResult, teamsResult].filter((result) => result.status === "rejected");
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
  const teamsConnected = Boolean(state.teams?.connected);
  const readyCount = [githubConnected, slackConnected, teamsConnected].filter(Boolean).length;

  function onStartGithubConnect() {
    window.location.href = "/api/zroky/v1/settings/github/connect/start";
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
          <Send aria-hidden="true" />
          <span>Microsoft Teams</span>
          <strong>{teamsConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.teams?.channel_name || "Webhook storage required before alerts deliver."}</small>
        </article>
        <article className="panel settings-summary-card">
          <CheckCircle2 aria-hidden="true" />
          <span>Ready</span>
          <strong>{readyCount}/3</strong>
          <small>Connected integrations can create PRs or deliver alerts.</small>
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
                <span>{state.teams?.channel_name || "Not configured"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Connector</strong>
                <span>{state.teams?.connector_type ?? "Not connected"}</span>
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
