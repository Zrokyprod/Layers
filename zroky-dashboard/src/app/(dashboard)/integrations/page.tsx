"use client";

import Link from "next/link";
import { GitPullRequest, Plug, RadioTower } from "lucide-react";

import IntegrationsSettingsPage from "../settings/integrations/page";

export default function IntegrationsPage() {
  return (
    <div className="dashboard-page integrations-page">
      <section className="page-header">
        <div>
          <span className="eyebrow">System-of-record proof</span>
          <h1>Connectors</h1>
          <p>Verify the real-world systems Zroky uses to prove agent outcomes, preflight pilot handoff, and export customer evidence.</p>
        </div>
      </section>

      <section className="settings-summary-grid" aria-label="Connector readiness">
        <article className="panel settings-summary-card">
          <Plug aria-hidden="true" />
          <span>Outcome connectors</span>
          <strong>Ledger + CRM</strong>
          <small>Run preflight and prove matched, mismatched, or not-verified real-world outcomes.</small>
          <Link href="/settings/integrations#ledger-refund-connector" className="btn btn-soft btn-sm">Open setup</Link>
        </article>
        <article className="panel settings-summary-card">
          <GitPullRequest aria-hidden="true" />
          <span>GitHub</span>
          <strong>Fix proof</strong>
          <small>Use GitHub checks and PR comments when replay proof should gate a change.</small>
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
          <strong>Slack</strong>
          <small>Route failure, replay, CI, and policy events to the operating channel.</small>
          <Link href="/settings/integrations/slack" className="btn btn-soft btn-sm">Manage Slack</Link>
        </article>
      </section>

      <IntegrationsSettingsPage />
    </div>
  );
}
