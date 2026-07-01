"use client";

import { ExternalLink } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import { buildActionView } from "@/lib/action-view";
import { compactJson, formatDateTime } from "@/lib/format";
import type { HomeQueueRow } from "@/lib/home-queue";
import type { ActionIntentResponse } from "@/lib/api";

type SelectedProofRailProps = {
  row: HomeQueueRow | null;
  intent: ActionIntentResponse | null;
};

export function SelectedProofRail({ row, intent }: SelectedProofRailProps) {
  if (!row) {
    return (
      <aside className="mc-proof-rail" aria-label="Selected proof">
        <p className="mc-eyebrow">Selected proof</p>
        <h2>No queued action</h2>
        <p className="mc-muted">When an action needs review, its digest and receipt state appear here.</p>
      </aside>
    );
  }

  const view = intent ? buildActionView(intent) : null;

  return (
    <aside className={`mc-proof-rail mc-tone-${row.tone}`} aria-label="Selected proof">
      <div className="mc-section-head mc-section-head-rail">
        <div>
          <p className="mc-eyebrow">Selected proof</p>
          <h2>{row.title}</h2>
        </div>
        <StatusPill value={row.status} tone={row.tone} />
      </div>
      <dl className="mc-proof-facts">
        <div>
          <dt>Action</dt>
          <dd>{row.actionId ?? "-"}</dd>
        </div>
        <div>
          <dt>Agent</dt>
          <dd>{row.agentName}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{row.reason}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(row.createdAt)}</dd>
        </div>
        {view ? (
          <>
            <div>
              <dt>Proof</dt>
              <dd>
                <StatusPill value={view.proofStatus} kind="proof" tone={view.proofTone} />
              </dd>
            </div>
            <div>
              <dt>Receipt</dt>
              <dd>
                <StatusPill value={view.receiptStatus} kind="receipt" tone={view.receiptTone} />
              </dd>
            </div>
            <div className="mc-proof-digest">
              <dt>Digest</dt>
              <dd>{view.digest}</dd>
            </div>
            <div className="mc-proof-json">
              <dt>Intent</dt>
              <dd>
                <pre>{compactJson(intent?.canonical_intent)}</pre>
              </dd>
            </div>
          </>
        ) : (
          <div>
            <dt>Context</dt>
            <dd>{row.detail}</dd>
          </div>
        )}
      </dl>
      <DashboardButtonLink
        className="mc-rail-link"
        href={row.href}
        icon={<ExternalLink />}
        iconPosition="right"
        variant="soft"
      >
        {row.actionLabel}
      </DashboardButtonLink>
    </aside>
  );
}
