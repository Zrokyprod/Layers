"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Bot, Cpu, PlayCircle } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";
import type {
  ActionExecutionAttemptResponse,
  ActionRunnerResponse,
} from "@/lib/api";
import type { AgentFleetRow, AgentFleetView } from "@/lib/agent-fleet";
import { formatCount, formatDateTime, humanize, timeSince } from "@/lib/format";

type AgentFleetWorkspaceProps = {
  fleet: AgentFleetView;
  runners: ActionRunnerResponse[];
  attempts: ActionExecutionAttemptResponse[];
  staleAttemptIds: string[];
  promoteLocked: boolean;
};

type AgentTab = "agents" | "runners" | "attempts";

function latestAction(row: AgentFleetRow) {
  return row.actionRows[0] ?? null;
}

function setupHrefForAgent(agentName: string) {
  return `/agents/setup?agentName=${encodeURIComponent(agentName)}`;
}

function AgentFleetTable({
  rows,
  selectedId,
  onSelect,
  promoteLocked,
}: {
  rows: AgentFleetRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  promoteLocked: boolean;
}) {
  return (
    <article className="agents-table-panel" aria-label="Agent fleet table">
      <div className="agents-panel-head">
        <div>
          <span>Managed fleet</span>
          <strong>{formatCount(rows.length)} shown</strong>
        </div>
      </div>
      <div className="agents-table-wrap">
        <table className="agents-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Status</th>
              <th>Coverage</th>
              <th>Signals</th>
              <th>Runners</th>
              <th>Last activity</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className={`agents-table-row${selectedId === row.id ? " is-selected" : ""}`}
                tabIndex={0}
                onClick={() => onSelect(row.id)}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  onSelect(row.id);
                }}
              >
                <td>
                  <div className="agents-name-cell">
                    <span className="agents-agent-icon" aria-hidden="true">
                      <Bot />
                    </span>
                    <div>
                      <strong>{row.agentName}</strong>
                      <span>{row.kind === "telemetry" ? "Telemetry-only / unmanaged" : row.profile?.runtime_path}</span>
                      <small>{row.profile?.environment ?? "environment unknown"}</small>
                    </div>
                  </div>
                </td>
                <td>
                  <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} />
                </td>
                <td>
                  <strong>{row.coverage.label}</strong>
                  <span className="agents-cell-note">
                    {row.coverage.detail}
                  </span>
                </td>
                <td>
                  <div className="agents-proof-cell">
                    <span>{row.riskSignals.label}</span>
                    <span className="agents-cell-note">
                      {formatCount(row.riskSignals.bypassed)} bypass / {formatCount(row.riskSignals.sequenceRisk)} sequence
                    </span>
                  </div>
                </td>
                <td>
                  <strong>{formatCount(row.runnerCount)}</strong>
                  <span className="agents-cell-note">observed compatible</span>
                </td>
                <td>
                  <strong>{formatDateTime(row.latestActivityAt)}</strong>
                  <span className="agents-cell-note">{row.latestActivityAt ? timeSince(row.latestActivityAt) : "No activity"}</span>
                </td>
                <td>
                  {row.kind === "profile" ? (
                    <DashboardButtonLink className="agents-row-action" href={row.href} size="sm" variant="soft">
                      Open agent
                    </DashboardButtonLink>
                  ) : (
                    <DashboardButtonLink
                      aria-disabled={promoteLocked || undefined}
                      className="agents-row-action"
                      href={setupHrefForAgent(row.agentName)}
                      size="sm"
                      title={promoteLocked ? "Plan cap reached" : "Create managed profile from telemetry identity"}
                      variant="soft"
                    >
                      Promote
                    </DashboardButtonLink>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
    <aside className="agents-inspector-panel" aria-label="Selected agent control">
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
                ? "Observed in action telemetry, but no AgentProfile is configured yet."
                : row.runnerCount > 0
                  ? `${formatCount(row.runnerCount)} compatible runner${row.runnerCount === 1 ? "" : "s"} observed from executions.`
                  : "No observed runner execution yet."}
            </small>
          </div>

          <div className="agents-mandate-card" aria-label="Agent mandate summary">
            <span>Mandate scope</span>
            <strong>{row.mandate.label}</strong>
            <small>{row.mandate.detail}</small>
            <div>
              <em>{row.mandate.runnerMode ? humanize(row.mandate.runnerMode) : "runner not bound"}</em>
              <em>{formatCount(row.mandate.verifierCount)} verifier{row.mandate.verifierCount === 1 ? "" : "s"}</em>
              <em>{formatCount(row.actionRollup.total)} observed action{row.actionRollup.total === 1 ? "" : "s"}</em>
            </div>
          </div>

          <div className="agents-inspector-score">
            <div>
              <span>Coverage</span>
              <strong>{row.coverage.percent == null ? "No signal" : `${row.coverage.percent}%`}</strong>
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

          {action ? (
            <>
              <ProofChainStepper steps={action.proofChain} />
              <div className="agents-inspector-control-grid">
                <div>
                  <span>Latest action</span>
                  <strong>{action.title}</strong>
                </div>
                <div>
                  <span>Action type</span>
                  <strong>{action.actionType}</strong>
                </div>
                <div>
                  <span>Digest</span>
                  <strong>{action.digest ?? "-"}</strong>
                </div>
                <div>
                  <span>Receipt</span>
                  <strong>{action.receiptLabel}</strong>
                </div>
              </div>
              <div className="agents-inspector-actions">
                <DashboardButtonLink href={action.hrefs.action ?? "/actions"} variant="soft">
                  Open action
                </DashboardButtonLink>
                <DashboardButtonLink href={action.hrefs.evidence ?? "/evidence"} variant="primary">
                  Open evidence
                </DashboardButtonLink>
                {row.kind === "telemetry" ? (
                  <DashboardButtonLink
                    aria-disabled={promoteLocked || undefined}
                    href={setupHrefForAgent(row.agentName)}
                    variant="soft"
                  >
                    Promote to managed
                  </DashboardButtonLink>
                ) : null}
              </div>
            </>
          ) : (
            <div className="agents-empty-filter">
              <strong>No protected action yet</strong>
              <span>Run this agent through the verified-action path to populate proof and runner context.</span>
            </div>
          )}
        </>
      ) : (
        <div className="agents-empty-filter">
          <strong>No row selected</strong>
          <span>Select a managed or telemetry agent to inspect its proof chain.</span>
        </div>
      )}
    </aside>
  );
}

function RunnersPanel({ runners }: { runners: ActionRunnerResponse[] }) {
  return (
    <article className="agents-table-panel" aria-label="Project runners">
      <div className="agents-panel-head">
        <div>
          <span>Runners</span>
          <strong>{formatCount(runners.length)} project runners</strong>
        </div>
      </div>
      <div className="agents-card-list">
        {runners.length > 0 ? runners.map((runner) => (
          <div key={runner.runner_id} className="agents-runner-card">
            <div>
              <Cpu aria-hidden="true" />
              <strong>{runner.name}</strong>
              <span>{runner.runner_type} / {runner.environment}</span>
            </div>
            <StatusPill value={runner.status} />
            <small>{runner.supported_operation_kinds.map((kind) => humanize(kind)).join(" / ") || "all operations"}</small>
            <small>Heartbeat {formatDateTime(runner.last_heartbeat_at)}</small>
          </div>
        )) : (
          <div className="agents-empty-filter">
            <strong>No runners registered</strong>
            <span>Connect a protected runner so authorized actions can execute with isolated credentials.</span>
          </div>
        )}
      </div>
    </article>
  );
}

function AttemptsPanel({
  attempts,
  staleAttemptIds,
}: {
  attempts: ActionExecutionAttemptResponse[];
  staleAttemptIds: string[];
}) {
  const stale = new Set(staleAttemptIds);
  return (
    <article className="agents-table-panel" aria-label="Execution attempts">
      <div className="agents-panel-head">
        <div>
          <span>Attempts</span>
          <strong>{formatCount(attempts.length)} recent attempts</strong>
        </div>
      </div>
      <div className="agents-card-list">
        {attempts.length > 0 ? attempts.map((attempt) => (
          <div key={attempt.attempt_id} className="agents-attempt-card" data-stale={stale.has(attempt.attempt_id) ? "true" : "false"}>
            <div>
              <PlayCircle aria-hidden="true" />
              <strong>{attempt.action_id}</strong>
              <span>{attempt.runner_id}</span>
            </div>
            <StatusPill
              value={attempt.status}
              tone={stale.has(attempt.attempt_id) ? "danger" : undefined}
              label={stale.has(attempt.attempt_id) ? "Stalled" : undefined}
            />
            <small>Attempt {attempt.attempt_number} / updated {formatDateTime(attempt.updated_at)}</small>
          </div>
        )) : (
          <div className="agents-empty-filter">
            <strong>No execution attempts</strong>
            <span>Attempts appear when authorized actions become runner-claimable.</span>
          </div>
        )}
      </div>
    </article>
  );
}

export function AgentsFleetWorkspace({
  attempts,
  fleet,
  promoteLocked,
  runners,
  staleAttemptIds,
}: AgentFleetWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<AgentTab>("agents");
  const [selectedId, setSelectedId] = useState<string | null>(fleet.rows[0]?.id ?? null);
  const selectedRow = useMemo(
    () => fleet.rows.find((row) => row.id === selectedId) ?? fleet.rows[0] ?? null,
    [fleet.rows, selectedId],
  );

  return (
    <section className="agents-workspace">
      <div className="agents-tabs" role="tablist" aria-label="Agent fleet views">
        {([
          ["agents", "Agents", Bot],
          ["runners", "Runners", Cpu],
          ["attempts", "Attempts", AlertTriangle],
        ] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={`agents-tab${activeTab === id ? " is-active" : ""}`}
            onClick={() => setActiveTab(id)}
          >
            <Icon aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {activeTab === "agents" ? (
        <div className="agents-layout-grid">
          <div className="agents-main-column">
            <AgentFleetTable
              rows={fleet.rows}
              selectedId={selectedRow?.id ?? null}
              onSelect={setSelectedId}
              promoteLocked={promoteLocked}
            />
          </div>
          <AgentInspector row={selectedRow} promoteLocked={promoteLocked} />
        </div>
      ) : null}
      {activeTab === "runners" ? <RunnersPanel runners={runners} /> : null}
      {activeTab === "attempts" ? <AttemptsPanel attempts={attempts} staleAttemptIds={staleAttemptIds} /> : null}
    </section>
  );
}
