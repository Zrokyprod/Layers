"use client";

import { useMemo, useState } from "react";
import { Bot } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";
import type { AgentFleetRow, AgentFleetView } from "@/lib/agent-fleet";
import { formatCount, formatDateTime, humanize, timeSince } from "@/lib/format";

type AgentFleetWorkspaceProps = {
  fleet: AgentFleetView;
  promoteLocked: boolean;
};

function latestAction(row: AgentFleetRow) {
  return row.actionRows[0] ?? null;
}

function setupHrefForAgent(agentName: string) {
  return `/agents/setup?agentName=${encodeURIComponent(agentName)}`;
}

function runtimeLabel(row: AgentFleetRow): string {
  if (row.kind === "telemetry") return "Telemetry-only / unmanaged";
  const framework = humanize(row.profile?.framework, "Custom runtime");
  const environment = row.profile?.environment ?? "environment unknown";
  return `${framework} / ${environment}`;
}

function coverageValue(row: AgentFleetRow): string {
  return row.coverage.percent == null ? "No signal" : `${row.coverage.percent}%`;
}

function reviewCount(row: AgentFleetRow): number {
  return row.riskSignals.bypassed
    + row.riskSignals.sequenceRisk
    + row.actionRollup.mismatched
    + row.actionRollup.held
    + row.actionRollup.notVerified
    + row.actionRollup.stalled;
}

function AgentFleetList({
  rows,
  selectedId,
  onSelect,
}: {
  rows: AgentFleetRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const managedCount = rows.filter((row) => row.kind === "profile").length;
  const unmanagedCount = rows.length - managedCount;
  const needsReview = rows.reduce((sum, row) => sum + reviewCount(row), 0);

  return (
    <article className="agents-table-panel agents-fleet-panel" aria-label="Agent fleet">
      <div className="agents-panel-head">
        <div>
          <span>Agent fleet</span>
          <strong>{formatCount(rows.length)} identities</strong>
        </div>
        <span className="agents-table-count">{formatCount(managedCount)} managed</span>
      </div>

      <div className="agents-fleet-summary" aria-label="Agent fleet counters">
        <div>
          <strong>{formatCount(managedCount)}</strong>
          <span>Managed</span>
        </div>
        <div>
          <strong>{formatCount(unmanagedCount)}</strong>
          <span>Unmanaged</span>
        </div>
        <div data-tone={needsReview > 0 ? "warning" : "success"}>
          <strong>{formatCount(needsReview)}</strong>
          <span>Needs review</span>
        </div>
      </div>

      <div className="agents-agent-list">
        {rows.map((row) => (
          <button
            key={row.id}
            type="button"
            aria-pressed={selectedId === row.id}
            className={`agents-agent-card${selectedId === row.id ? " is-selected" : ""}`}
            data-tone={row.tone}
            onClick={() => onSelect(row.id)}
          >
            <span className="agents-agent-icon" aria-hidden="true">
              <Bot />
            </span>
            <span className="agents-agent-card-main">
              <span className="agents-agent-card-title">
                <strong>{row.agentName}</strong>
                <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} />
              </span>
              <span>{runtimeLabel(row)}</span>
              <span className="agents-agent-card-signals">
                <small>{row.coverage.label}</small>
                <small>{row.riskSignals.label}</small>
                <small>{row.latestActivityAt ? timeSince(row.latestActivityAt) : "No activity"}</small>
              </span>
            </span>
            <span className="agents-agent-card-metrics" aria-label={`${row.agentName} control summary`}>
              <span>
                <strong>{coverageValue(row)}</strong>
                <small>Coverage</small>
              </span>
              <span>
                <strong>{formatCount(row.riskSignals.bypassed + row.riskSignals.sequenceRisk)}</strong>
                <small>{formatCount(row.riskSignals.bypassed)} bypass / {formatCount(row.riskSignals.sequenceRisk)} sequence</small>
              </span>
              <span>
                <strong>{formatCount(row.runnerCount)}</strong>
                <small>observed compatible</small>
              </span>
            </span>
          </button>
        ))}
      </div>
    </article>
  );
}

function AgentInspector({
  promoteLocked,
  row,
}: {
  promoteLocked: boolean;
  row: AgentFleetRow | null;
}) {
  const action = row ? latestAction(row) : null;

  return (
    <aside className="agents-inspector-panel agents-simple-inspector" aria-label="Selected agent control">
      <div className="agents-panel-head">
        <div>
          <span>Selected agent</span>
          <strong>{row?.agentName ?? "No agent selected"}</strong>
        </div>
        {row ? <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} /> : null}
      </div>

      {row ? (
        <>
          <div className="agents-inspector-verdict" data-tone={row.tone === "danger" || row.tone === "warning" ? "warning" : "success"}>
            <span>{row.kind === "telemetry" ? "Unmanaged identity" : "Managed profile"}</span>
            <strong>{row.statusLabel}</strong>
            <small>
              {row.kind === "telemetry"
                ? "Promote this observed identity before trusting its production actions."
                : row.runnerCount > 0
                  ? `${formatCount(row.runnerCount)} compatible runner${row.runnerCount === 1 ? "" : "s"} observed.`
                  : "No runner execution has been observed yet."}
            </small>
          </div>

          <div className="agents-inspector-score agents-simple-score">
            <div>
              <span>Coverage</span>
              <strong>{coverageValue(row)}</strong>
            </div>
            <div>
              <span>Bypass</span>
              <strong>{formatCount(row.riskSignals.bypassed)}</strong>
            </div>
            <div>
              <span>Sequence risk</span>
              <strong>{formatCount(row.riskSignals.sequenceRisk)}</strong>
            </div>
            <div>
              <span>Receipts</span>
              <strong>{formatCount(row.actionRollup.receiptsGenerated)}</strong>
            </div>
          </div>

          <div className="agents-mandate-card" aria-label="Agent mandate summary">
            <span>What Zroky controls</span>
            <strong>{row.mandate.label}</strong>
            <small>{row.mandate.detail}</small>
            <div>
              <em>{row.mandate.runnerMode ? humanize(row.mandate.runnerMode) : "runner not bound"}</em>
              <em>{formatCount(row.mandate.verifierCount)} verifier{row.mandate.verifierCount === 1 ? "" : "s"}</em>
              <em>{formatCount(row.actionRollup.total)} observed action{row.actionRollup.total === 1 ? "" : "s"}</em>
            </div>
          </div>

          {action ? (
            <div className="agents-latest-action-card" aria-label="Latest protected action">
              <div className="agents-latest-action-head">
                <div>
                  <span>Latest action</span>
                  <strong>{action.title}</strong>
                  <small>{formatDateTime(action.updatedAt ?? action.createdAt)}</small>
                </div>
                <StatusPill value={action.status} label={action.statusLabel} tone={action.statusTone} />
              </div>
              <ProofChainStepper steps={action.proofChain} variant="compact" />
              <div className="agents-inspector-control-grid">
                <div>
                  <span>Action type</span>
                  <strong>{action.actionType}</strong>
                </div>
                <div>
                  <span>Receipt</span>
                  <strong>{action.receiptLabel}</strong>
                </div>
              </div>
            </div>
          ) : (
            <div className="agents-empty-filter">
              <strong>No protected action yet</strong>
              <span>Run this agent through the verified-action path to populate proof and runner context.</span>
            </div>
          )}

          <div className="agents-inspector-actions">
            {row.kind === "profile" ? (
              <DashboardButtonLink href={row.href} variant="soft">
                Open agent
              </DashboardButtonLink>
            ) : (
              <DashboardButtonLink
                aria-disabled={promoteLocked || undefined}
                href={setupHrefForAgent(row.agentName)}
                variant="primary"
              >
                Promote to managed
              </DashboardButtonLink>
            )}
            {action ? (
              <>
                <DashboardButtonLink href={action.hrefs.action ?? "/actions"} variant="soft">
                  Open action
                </DashboardButtonLink>
                <DashboardButtonLink href={action.hrefs.evidence ?? "/evidence"} variant="primary">
                  Open evidence
                </DashboardButtonLink>
              </>
            ) : null}
          </div>
        </>
      ) : (
        <div className="agents-empty-filter">
          <strong>No agent selected</strong>
          <span>Select a managed or telemetry identity to inspect its control state.</span>
        </div>
      )}
    </aside>
  );
}

export function AgentsFleetWorkspace({
  fleet,
  promoteLocked,
}: AgentFleetWorkspaceProps) {
  const [selectedId, setSelectedId] = useState<string | null>(fleet.rows[0]?.id ?? null);
  const selectedRow = useMemo(
    () => fleet.rows.find((row) => row.id === selectedId) ?? fleet.rows[0] ?? null,
    [fleet.rows, selectedId],
  );

  return (
    <section className="agents-workspace">
      <div className="agents-layout-grid">
        <div className="agents-main-column">
          <AgentFleetList
            rows={fleet.rows}
            selectedId={selectedRow?.id ?? null}
            onSelect={setSelectedId}
          />
        </div>
        <AgentInspector row={selectedRow} promoteLocked={promoteLocked} />
      </div>
    </section>
  );
}
