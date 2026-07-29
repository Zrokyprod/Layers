"use client";

import { Download, ExternalLink } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import type { EvidenceLedgerRow, OutcomeGraphEffectRow } from "@/lib/evidence-ledger";
import { formatDateTime, humanize, timeUntil } from "@/lib/format";

type FocusedProofPanelProps = {
  isExporting: boolean;
  onExport: () => void;
  row: EvidenceLedgerRow | null;
};

function flag(value: boolean): string {
  return value ? "yes" : "no";
}

function effectTone(effect: OutcomeGraphEffectRow): "danger" | "neutral" | "success" | "warning" {
  if (effect.conflicted || !effect.observed) return "warning";
  return effect.matched && !effect.stale ? "success" : "danger";
}

function ReasonCodeAction({ row }: { row: EvidenceLedgerRow }) {
  if (row.classification !== "pending" && row.classification !== "unknown") return null;
  if (row.reasonCode === "no_connector") {
    return (
      <div className="ev-empty-state">
        <strong>Is system ka connector configured nahi hai</strong>
        <DashboardButtonLink href="/integrations" icon={<ExternalLink size={14} />} variant="primary">
          Open integrations
        </DashboardButtonLink>
      </div>
    );
  }
  if (row.reasonCode === "runner_offline") {
    return (
      <div className="ev-empty-state">
        <strong>Private runner offline hai</strong>
        <DashboardButtonLink href="/operations" icon={<ExternalLink size={14} />} variant="primary">
          Open runner status
        </DashboardButtonLink>
      </div>
    );
  }
  if (row.reasonCode === "sor_unreachable") {
    return (
      <div className="ev-empty-state">
        <strong>System reachable nahi tha, retry hoga</strong>
        <span>Next check {timeUntil(row.nextCheckAt)}</span>
      </div>
    );
  }
  if (row.reasonCode === "no_sor_trace") {
    return (
      <div className="ev-empty-state">
        <strong>System of record mein koi matching record nahi mila</strong>
        <span>This is the finding.</span>
      </div>
    );
  }
  return null;
}

function EffectRow({ effect }: { effect: OutcomeGraphEffectRow }) {
  return (
    <div className="outcomes-diff-row" data-tone={effectTone(effect)}>
      <strong>{effect.effectKey}</strong>
      <span>{humanize(String(effect.expected.object_type ?? "-"))}</span>
      <span>observed {flag(effect.observed)}</span>
      <span>matched {flag(effect.matched)}</span>
      <span>stale {flag(effect.stale)}</span>
      <span>conflicted {flag(effect.conflicted)}</span>
      <code>{effect.observationDigest ?? "no observation digest"}</code>
    </div>
  );
}

export function FocusedProofPanel({ isExporting, onExport, row }: FocusedProofPanelProps) {
  return (
    <aside className="ev-proof-panel" aria-label="Focused proof panel">
      <section className="ev-focused-card">
        <div className="ev-focused-head">
          <div className="ev-focused-copy">
            <span className="ev-eyebrow">Selected proof</span>
            <h2>{row?.title ?? "No proof selected"}</h2>
            <p>{row ? `${row.environment ?? "env"} / ${row.intentId ?? "no intent"}` : "Select a ledger row to inspect effect-level proof."}</p>
          </div>
          {row ? <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} /> : null}
        </div>
        <div className="ev-proof-actions">
          <DashboardButton icon={<Download />} disabled={!row || isExporting} onClick={onExport} variant="primary">
            {isExporting ? "Exporting" : "Export graph JSON"}
          </DashboardButton>
        </div>
        {row ? (
          <dl className="ev-focused-meta">
            <div>
              <dt>Intent</dt>
              <dd><code>{row.intentId ?? "-"}</code></dd>
            </div>
            <div>
              <dt>Checked</dt>
              <dd>{formatDateTime(row.checkedAt)}</dd>
            </div>
            <div>
              <dt>Digest</dt>
              <dd><code>{row.digest ?? "-"}</code></dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="ev-proof-detail" aria-label="Selected proof detail">
        {!row ? (
          <div className="ev-empty-state">Select a proof row.</div>
        ) : (
          <div className="ev-proof-simple" aria-label="Outcome graph proof">
            <header className="ev-proof-simple-head">
              <div>
                <span className="ev-eyebrow">Outcome graph</span>
                <h3>Expected vs actual effects</h3>
              </div>
              {row.reasonCode && (row.classification === "pending" || row.classification === "unknown") ? (
                <StatusPill value={row.reasonCode} label={humanize(row.reasonCode)} tone="warning" />
              ) : null}
            </header>
            <div className="outcomes-diff-table">
              <div className="outcomes-diff-head">
                <span>Effect</span>
                <span>Object</span>
                <span>Observed</span>
                <span>Matched</span>
                <span>Stale</span>
                <span>Conflict</span>
                <span>Proof ref</span>
              </div>
              {(row.effects ?? []).length > 0 ? (
                (row.effects ?? []).map((effect) => <EffectRow effect={effect} key={effect.effectKey} />)
              ) : (
                <div className="outcomes-diff-empty">No effect rows in this graph.</div>
              )}
            </div>
            <ReasonCodeAction row={row} />
          </div>
        )}
      </section>
    </aside>
  );
}
