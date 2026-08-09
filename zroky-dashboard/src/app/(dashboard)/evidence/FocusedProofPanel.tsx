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

function effectTone(effect: OutcomeGraphEffectRow): "danger" | "neutral" | "success" | "warning" {
  if (effect.conflicted || !effect.observed) return "warning";
  return effect.matched && !effect.stale ? "success" : "danger";
}

function effectStatus(effect: OutcomeGraphEffectRow): string {
  if (effect.conflicted) return "Conflicted";
  if (effect.stale) return "Stale";
  if (!effect.observed) return "Not observed";
  return effect.matched ? "Matched" : "Mismatch";
}

function objectLabel(value: Record<string, unknown>, fallback: string): string {
  return humanize(String(value.object_type ?? fallback));
}

function ReasonCodeAction({ row }: { row: EvidenceLedgerRow }) {
  if (row.classification !== "pending" && row.classification !== "unknown") return null;
  if (row.reasonCode === "no_connector") {
    return (
      <div className="ev-empty-state">
        <strong>This system does not have a configured connector</strong>
        <DashboardButtonLink href="/integrations" icon={<ExternalLink size={14} />} variant="primary">
          Open integrations
        </DashboardButtonLink>
      </div>
    );
  }
  if (row.reasonCode === "runner_offline") {
    return (
      <div className="ev-empty-state">
        <strong>The private runner is offline</strong>
        <DashboardButtonLink href="/operations?view=unverifiable" icon={<ExternalLink size={14} />} variant="primary">
          Open runner status
        </DashboardButtonLink>
      </div>
    );
  }
  if (row.reasonCode === "sor_unreachable") {
    return (
      <div className="ev-empty-state">
        <strong>The system was unreachable; Zroky will retry</strong>
        <span>Next check {timeUntil(row.nextCheckAt)}</span>
      </div>
    );
  }
  if (row.reasonCode === "no_sor_trace") {
    return (
      <div className="ev-empty-state">
        <strong>No matching record was found in the system of record</strong>
        <span>This is the finding.</span>
      </div>
    );
  }
  return null;
}

function EffectRow({ effect }: { effect: OutcomeGraphEffectRow }) {
  return (
    <article className="ev-effect-card" data-tone={effectTone(effect)} aria-label={`Effect ${effect.effectKey}`}>
      <header>
        <strong>{effect.effectKey}</strong>
        <StatusPill value={effectStatus(effect)} label={effectStatus(effect)} tone={effectTone(effect)} />
      </header>
      <div className="ev-effect-comparison">
        <div>
          <span>Expected</span>
          <strong>{objectLabel(effect.expected, "declared effect")}</strong>
        </div>
        <div>
          <span>Observed</span>
          <strong>{objectLabel(effect.actual, effect.observed ? "observed record" : "no observation")}</strong>
        </div>
      </div>
      <dl className="ev-effect-flags">
        <div><dt>Observed</dt><dd>{effect.observed ? "Yes" : "No"}</dd></div>
        <div><dt>Matched</dt><dd>{effect.matched ? "Yes" : "No"}</dd></div>
        <div><dt>Stale</dt><dd>{effect.stale ? "Yes" : "No"}</dd></div>
        <div><dt>Conflicted</dt><dd>{effect.conflicted ? "Yes" : "No"}</dd></div>
      </dl>
      <div className="ev-effect-proof">
        <span>Proof reference</span>
        <code>{effect.observationDigest ?? "No observation digest"}</code>
      </div>
    </article>
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
            {isExporting ? "Exporting" : "Export evidence pack"}
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
            <div className="ev-effect-list">
              {(row.effects ?? []).length > 0 ? (
                (row.effects ?? []).map((effect) => <EffectRow effect={effect} key={effect.effectKey} />)
              ) : (
                <div className="ev-empty-state">No effect rows in this graph.</div>
              )}
            </div>
            <ReasonCodeAction row={row} />
          </div>
        )}
      </section>
    </aside>
  );
}
