"use client";

import Link from "next/link";
import { GitPullRequest, KeyRound, Plug, RadioTower } from "lucide-react";

import IntegrationsSettingsPage from "../settings/integrations/page";

export default function IntegrationsPage() {
  return (
    <main className="dashboard-page integrations-page">
      <section className="page-header">
        <div>
          <span className="eyebrow">Reliability connections</span>
          <h1>Integrations</h1>
          <p>Is this agent safe to scale? Verify provider keys, PR gates, capture delivery, and team notification channels.</p>
        </div>
      </section>

      <section className="settings-summary-grid" aria-label="Integration readiness">
        <article className="panel settings-summary-card">
          <KeyRound aria-hidden="true" />
          <span>Provider keys</span>
          <strong>Replay proof</strong>
          <small>Connect provider keys only when verified replay requires them.</small>
          <Link href="/settings/providers" className="btn btn-soft btn-sm">Manage providers</Link>
        </article>
        <article className="panel settings-summary-card">
          <GitPullRequest aria-hidden="true" />
          <span>GitHub</span>
          <strong>CI gates</strong>
          <small>Use GitHub checks and PR comments to block repeat failures.</small>
          <Link href="/ci-gates" className="btn btn-soft btn-sm">Open CI gates</Link>
        </article>
        <article className="panel settings-summary-card">
          <RadioTower aria-hidden="true" />
          <span>Capture</span>
          <strong>Gateway health</strong>
          <small>Capture loss and spool backlog should be visible before scale.</small>
          <Link href="/home" className="btn btn-soft btn-sm">Open health</Link>
        </article>
        <article className="panel settings-summary-card">
          <Plug aria-hidden="true" />
          <span>Notifications</span>
          <strong>Slack / Teams</strong>
          <small>Route failure, replay, CI, and policy events to operating channels.</small>
          <Link href="/integrations" className="btn btn-soft btn-sm">Refresh status</Link>
        </article>
      </section>

      <IntegrationsSettingsPage />
    </main>
  );
}
