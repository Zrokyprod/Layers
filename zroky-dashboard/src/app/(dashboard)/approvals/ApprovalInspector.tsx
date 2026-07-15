"use client";

import { useEffect, useState } from "react";
import { Check, CircleAlert, FileText, MessageSquare, PlugZap, Users, X } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { EvidencePackView } from "@/components/evidence-pack-view";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";
import type { RuntimePolicyEvidencePackResponse } from "@/lib/api";
import type { ApprovalQueueRow } from "@/lib/approval-queue";
import { compactJson, field, formatDateTime, humanize, timeUntil } from "@/lib/format";

type Fact = {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
};

type JsonSection = {
  title: string;
  value: unknown;
};

type InspectorTab = "decision" | "evidence" | "audit" | "raw";

type ApprovalInspectorProps = {
  row: ApprovalQueueRow | null;
  pack: RuntimePolicyEvidencePackResponse | undefined;
  packLoading: boolean;
  packError: Error | null;
  reason: string;
  setReason: (value: string) => void;
  busy: boolean;
  canDecide: boolean;
  onApprove: (id: string, reason: string) => void;
  onReject: (id: string, reason: string) => void;
};

const TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: "decision", label: "Decision" },
  { id: "evidence", label: "Evidence" },
  { id: "audit", label: "Audit" },
  { id: "raw", label: "Developer" },
];

const REASON_CHIPS = [
  "Evidence matches request",
  "Wrong target",
  "Policy violation",
  "Suspicious sequence",
] as const;

function valuePresent(value: unknown): boolean {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function requiredApprovals(row: ApprovalQueueRow): number {
  return Math.max(1, row.decision.required_approval_count ?? 1);
}

function recordedApprovals(row: ApprovalQueueRow): number {
  return Math.max(0, row.decision.approval_count ?? 0);
}

function approveLabel(row: ApprovalQueueRow): string {
  const required = requiredApprovals(row);
  const remaining = Math.max(0, required - recordedApprovals(row));
  return required > 1 && remaining > 1 ? "Record approval" : "Approve action";
}

function displayApprover(subject: string): string {
  if (subject.includes("@")) return subject;
  const [provider, identifier] = subject.split(":", 2);
  if (!identifier) return subject;
  const suffix = identifier.length > 6 ? `...${identifier.slice(-6)}` : identifier;
  return `${humanize(provider, "Identity")} account ${suffix}`;
}

function ApproverChain({ row }: { row: ApprovalQueueRow }) {
  const remaining = Math.max(0, row.requiredApprovalCount - row.recordedApprovalCount);
  const state = row.status === "approved"
    ? {
        title: `${row.recordedApprovalCount}/${row.requiredApprovalCount} approvals completed`,
        badge: "Complete",
        empty: "Approval completed, but the approver identity was not returned.",
      }
    : row.status === "rejected"
      ? {
          title: "Reviewer rejected this action",
          badge: "Closed",
          empty: "The action was rejected before any approval released it.",
        }
      : row.status === "expired"
        ? {
            title: `${row.recordedApprovalCount}/${row.requiredApprovalCount} approvals completed`,
            badge: "Expired",
            empty: "The required approval chain was not completed before the deadline.",
          }
        : {
            title: `${row.recordedApprovalCount}/${row.requiredApprovalCount} approvals recorded`,
            badge: remaining === 0 ? "Complete" : `${remaining} needed`,
            empty: "No approval recorded yet. The action remains held at the runtime gate.",
          };
  return (
    <section className="approval-v2-approver-chain">
      <div className="approval-v2-tab-panel-head">
        <div>
          <span className="approval-v2-eyebrow">Approver chain</span>
          <strong>{state.title}</strong>
        </div>
        <span>{state.badge}</span>
      </div>
      {row.approverSubjects.length > 0 ? (
        <ol>
          {row.approverSubjects.map((subject) => (
            <li key={subject}>
              <Check aria-hidden="true" size={14} />
              <span>{displayApprover(subject)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p>{state.empty}</p>
      )}
    </section>
  );
}

function riskReasons(row: ApprovalQueueRow): string[] {
  const reasons = [row.holdReason.detail, ...row.decision.reasons]
    .map((reason) => humanize(reason, "Runtime policy matched this action."))
    .filter((reason) => reason !== "-");
  return [...new Set(reasons)].slice(0, 3);
}

function decisionSummary(row: ApprovalQueueRow): { eyebrow: string; title: string; reasons: string[] } {
  const policyReasons = riskReasons(row);
  const resolutionReason = row.decision.resolution_reason ? humanize(row.decision.resolution_reason) : null;
  if (row.status === "approved") {
    return {
      eyebrow: "Why it was released",
      title: "Human approval completed",
      reasons: [...new Set([resolutionReason, ...policyReasons].filter((reason): reason is string => Boolean(reason)))],
    };
  }
  if (row.status === "rejected") {
    return {
      eyebrow: "Why the reviewer stopped it",
      title: "Rejected by reviewer",
      reasons: [...new Set([resolutionReason, ...policyReasons].filter((reason): reason is string => Boolean(reason)))],
    };
  }
  if (row.status === "expired") {
    return {
      eyebrow: "Why approval expired",
      title: "Approval window ended",
      reasons: [
        row.expiresAt
          ? `The required approval chain was incomplete at ${formatDateTime(row.expiresAt)}.`
          : "The required approval chain was not completed in time.",
        ...policyReasons,
      ],
    };
  }
  return {
    eyebrow: row.status === "pending_approval" ? "Why review is needed" : "Why policy stopped it",
    title: row.holdReason.title,
    reasons: policyReasons,
  };
}

function DecisionSummary({ row }: { row: ApprovalQueueRow }) {
  const summary = decisionSummary(row);
  return (
    <section className={`approval-v2-risk-summary approval-v2-tone-${row.holdReason.tone}`}>
      <div>
        <span className="approval-v2-eyebrow">{summary.eyebrow}</span>
        <strong>{summary.title}</strong>
        {summary.reasons.length > 0 ? (
          <ul>
            {summary.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p>Runtime policy matched this action before execution.</p>
        )}
      </div>
      <div className="approval-v2-risk-badges">
        {row.isSequenceRisk ? <span>Pattern risk</span> : null}
        {row.isExpiringSoon ? <span>Expiring</span> : null}
      </div>
    </section>
  );
}

function FactGrid({ facts }: { facts: Fact[] }) {
  const shown = facts.filter((fact) => fact.value != null && fact.value !== "");
  if (shown.length === 0) return null;
  return (
    <dl className="approval-v2-fact-grid">
      {shown.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.mono ? <code>{fact.value}</code> : fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function JsonSections({ sections }: { sections: JsonSection[] }) {
  const shown = sections.filter((section) => valuePresent(section.value));
  if (shown.length === 0) return null;
  return (
    <div className="approval-v2-json-grid">
      {shown.map((section) => (
        <details key={section.title} className="approval-v2-json-section">
          <summary>
            <h4>{section.title}</h4>
            <span>JSON</span>
          </summary>
          <pre>{compactJson(section.value)}</pre>
        </details>
      ))}
    </div>
  );
}

function AuditTrail({ row }: { row: ApprovalQueueRow }) {
  const audit = row.decision.audit_log ?? [];
  return (
    <section className="approval-v2-audit">
      <div className="approval-v2-tab-panel-head">
        <div>
          <span className="approval-v2-eyebrow">Approval audit</span>
          <strong>Decision history</strong>
        </div>
        <span>{audit.length} event{audit.length === 1 ? "" : "s"}</span>
      </div>
      {audit.length === 0 ? (
        <p>No approval audit events captured yet.</p>
      ) : (
        <ol>
          {audit.map((event) => (
            <li key={event.id}>
              <div>
                <strong>{humanize(event.event_type, "Audit event")}</strong>
                <span>{formatDateTime(event.created_at)}</span>
              </div>
              <p>
                {event.actor ? `${event.actor}: ` : ""}
                {event.reason ?? "-"}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CompactEvidence({
  pack,
  packError,
  packLoading,
  row,
}: {
  pack: RuntimePolicyEvidencePackResponse | undefined;
  packLoading: boolean;
  packError: Error | null;
  row: ApprovalQueueRow;
}) {
  if (packLoading) {
    return (
      <section className="approval-v2-evidence">
        <span className="approval-v2-eyebrow">Evidence</span>
        <strong>Loading compact evidence</strong>
        <p>Fetching the selected decision evidence pack.</p>
      </section>
    );
  }
  if (packError) {
    return (
      <section className="approval-v2-evidence approval-v2-tone-danger">
        <span className="approval-v2-eyebrow">Evidence</span>
        <strong>Evidence unavailable</strong>
        <p>{packError.message}</p>
      </section>
    );
  }
  if (!pack) {
    return (
      <section className="approval-v2-evidence approval-v2-tone-warning">
        <span className="approval-v2-eyebrow">Evidence</span>
        <strong>No evidence pack loaded</strong>
        <p>Open the full evidence page when this decision needs audit review.</p>
      </section>
    );
  }
  return (
    <section className="approval-v2-evidence">
      <div className="approval-v2-evidence-head">
        <div>
          <span className="approval-v2-eyebrow">Compact evidence</span>
          <strong>{row.title}</strong>
        </div>
        <DashboardButtonLink href={row.hrefs.evidence} icon={<FileText />} variant="soft">
          Open full evidence
        </DashboardButtonLink>
      </div>
      <EvidencePackView pack={pack} title={row.title} mode="compact" />
    </section>
  );
}

function executionWaitingForRunner(row: ApprovalQueueRow): boolean {
  const execution = row.proofChain.find((step) => step.step === "execution");
  if (row.status !== "approved" || row.kind !== "action_intent_hold" || !execution) return false;
  const terminalStatuses = ["succeeded", "completed", "failed", "prevented"];
  return !terminalStatuses.includes(execution.status.toLowerCase());
}

function OperationalHandoff({ row }: { row: ApprovalQueueRow }) {
  const isPending = row.status === "pending_approval";
  const waitingForRunner = executionWaitingForRunner(row);
  if (!isPending && !waitingForRunner && row.agentIdentityKnown) return null;

  return (
    <section className="approval-v2-operational" aria-label="Approval operational handoff">
      {isPending ? (
        <div className="approval-v2-operational-row">
          <Users aria-hidden="true" size={17} />
          <div>
            <span className="approval-v2-eyebrow">Decision ownership</span>
            <strong>Any project admin can decide</strong>
            <p>
              {row.expiresAt
                ? `Decision window ${timeUntil(row.expiresAt)}. Escalate before the hold expires.`
                : "No approval deadline was returned. Keep this hold under active review."}
            </p>
          </div>
          <DashboardButtonLink href="/integrations/slack" icon={<MessageSquare />} variant="soft">
            Slack escalation
          </DashboardButtonLink>
        </div>
      ) : null}

      {waitingForRunner ? (
        <div className="approval-v2-operational-row approval-v2-operational-runner">
          <PlugZap aria-hidden="true" size={17} />
          <div>
            <span className="approval-v2-eyebrow">Execution handoff</span>
            <strong>Approved, waiting for a runner</strong>
            <p>Approval authorized this action, but no protected execution has started yet.</p>
          </div>
          <DashboardButtonLink href="/agents" icon={<PlugZap />} variant="primary">
            Check runner
          </DashboardButtonLink>
        </div>
      ) : null}

      {!row.agentIdentityKnown ? (
        <div className="approval-v2-operational-row approval-v2-operational-warning" role="note">
          <CircleAlert aria-hidden="true" size={17} />
          <div>
            <span className="approval-v2-eyebrow">Runtime identity</span>
            <strong>Agent identity was not reported</strong>
            <p>The decision remains digest-bound, but this runtime should be registered before release is trusted.</p>
          </div>
          <DashboardButtonLink href="/agents" icon={<Users />} variant="soft">
            Review agents
          </DashboardButtonLink>
        </div>
      ) : null}
    </section>
  );
}

export function ApprovalInspector({
  busy,
  canDecide,
  onApprove,
  onReject,
  pack,
  packError,
  packLoading,
  reason,
  row,
  setReason,
}: ApprovalInspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTab>("decision");

  useEffect(() => {
    setActiveTab("decision");
  }, [row?.id]);

  if (!row) {
    return (
      <section className="approval-v2-empty-state approval-v2-inspector-empty" aria-label="Selected action control">
        <h2>Select an action</h2>
        <p>Pending approvals and resolved decisions appear here with policy reason, evidence, and audit history.</p>
      </section>
    );
  }

  const isPendingDecision = row.status === "pending_approval";
  const canResolve = isPendingDecision && canDecide;
  const disabled = busy || !canResolve || reason.trim().length < 3;
  const required = requiredApprovals(row);
  const recorded = recordedApprovals(row);
  const remaining = Math.max(0, required - recorded);
  const approvalCopy = required > 1 ? `${recorded}/${required} approvals recorded` : row.approvalProgress;
  const consoleState = isPendingDecision
    ? {
        title: "Decision required",
        copy: "A reason is required. The decision is bound to this exact action and intent digest.",
        progress: remaining > 1 ? `${recorded}/${required} approvals complete` : "Final decision required",
        previewLabel: remaining > 1 ? "This records one approval" : "Approval will release",
        previewCopy: remaining > 1
          ? `This records approval ${recorded + 1} of ${required}. Execution remains held until distinct approvers complete the chain.`
          : "Approval authorizes this exact action to continue through the protected execution flow.",
      }
    : row.status === "approved"
      ? {
          title: "Approval completed",
          copy: "This decision is locked and preserved with the approver, reason, and evidence.",
          progress: `${recorded}/${required} approvals complete`,
          previewLabel: "Approved action",
          previewCopy: "The exact action was released to the protected execution flow. Execution and verification remain separate stages.",
        }
      : row.status === "rejected"
        ? {
            title: "Rejected by reviewer",
            copy: "This decision is locked and the action cannot execute from this approval.",
            progress: "Human rejection",
            previewLabel: "Action rejected",
            previewCopy: "The reviewer kept this exact action from reaching execution.",
          }
        : row.status === "expired"
          ? {
              title: "Approval expired",
              copy: "The required approval chain did not complete before the deadline.",
              progress: "Deadline passed",
              previewLabel: "Action remained stopped",
              previewCopy: "No protected execution was released from this expired approval.",
            }
          : {
              title: "Blocked by policy",
              copy: "Runtime policy denied this action before it could reach execution.",
              progress: "Policy block",
              previewLabel: "Action blocked",
              previewCopy: "The runtime gate prevented this exact action from reaching a runner.",
            };
  const mechanismCopy = row.status === "pending_approval"
    ? "Policy requires a human decision before this exact action can execute."
    : row.status === "approved"
      ? "Human approval changed this exact gate from held to allowed."
      : row.status === "rejected"
        ? "A human reviewer denied this exact action at the approval gate."
        : row.status === "expired"
          ? "The approval window closed before the required decision chain completed."
          : "Runtime policy denied this exact action before execution.";
  const actionFacts: Fact[] = [
    { label: "Action ID", value: row.actionId, mono: true },
    { label: "Decision ID", value: row.decisionId, mono: true },
    { label: "Digest", value: row.digest, mono: true },
    { label: "System", value: row.systemRef, mono: true },
    { label: "Environment", value: row.environment },
    { label: "Operation", value: row.operationKind ? humanize(row.operationKind) : null },
    {
      label: isPendingDecision ? "Expires" : "Approval deadline",
      value: row.expiresAt
        ? isPendingDecision
          ? timeUntil(row.expiresAt)
          : formatDateTime(row.expiresAt)
        : null,
    },
  ];
  const decisionFacts: Fact[] = [
    { label: "Runtime decision", value: humanize(row.decision.decision) },
    { label: "Risk", value: row.riskLabel },
    { label: "Impact", value: row.impactLabel },
    { label: "Approval progress", value: approvalCopy },
    { label: "Resolved by", value: row.decision.resolved_by },
    { label: "Resolved at", value: formatDateTime(row.decision.resolved_at) },
    { label: "Resolution reason", value: row.decision.resolution_reason },
  ];
  const jsonSections: JsonSection[] = [
    { title: "Request", value: row.decision.request },
    { title: "Policy hit", value: row.decision.policy_hit },
    { title: "Business impact", value: row.decision.business_impact },
    { title: "Mandate snapshot", value: row.decision.policy_snapshot },
    { title: "Intended action", value: row.decision.intended_action },
  ];

  return (
    <section className="approval-v2-inspector-panel" aria-label="Selected action control">
      <header className="approval-v2-inspector-header">
        <div>
          <span className="approval-v2-eyebrow">{isPendingDecision ? "Selected approval" : "Resolved decision"}</span>
          <h2>{row.title}</h2>
          <p>
            {row.agentName} / {row.kind === "guard_only_hold" ? "Guard-only decision" : row.actionType}
          </p>
        </div>
        <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
      </header>

      <DecisionSummary row={row} />

      <section className="approval-v2-console" aria-label="Approval decision control">
        <div>
          <span className="approval-v2-eyebrow">Decision console</span>
          <strong>{consoleState.title}</strong>
          <p>{consoleState.copy}</p>
        </div>
        <div className="approval-v2-resolution">
          <span>{consoleState.progress}</span>
          <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
        </div>
        <div className="approval-v2-action-preview">
          <div>
            <span className="approval-v2-eyebrow">{consoleState.previewLabel}</span>
            <strong>{row.approvalAction}</strong>
          </div>
          <p>{consoleState.previewCopy}</p>
        </div>
        {canResolve ? (
          <div className="approval-v2-actions">
            <div className="approval-v2-reason-chips" aria-label="Quick decision reasons">
              {REASON_CHIPS.map((chip) => (
                <button key={chip} type="button" onClick={() => setReason(chip)}>
                  {chip}
                </button>
              ))}
            </div>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Decision reason (required)"
              aria-label="Decision reason"
            />
            <DashboardButton
              icon={<Check />}
              disabled={disabled}
              onClick={() => onApprove(row.decisionId, reason)}
              variant="primary"
            >
              {approveLabel(row)}
            </DashboardButton>
            <DashboardButton
              icon={<X />}
              disabled={disabled}
              onClick={() => onReject(row.decisionId, reason)}
              variant="soft"
            >
              Reject action
            </DashboardButton>
          </div>
        ) : isPendingDecision ? (
          <div className="approval-v2-permission-note" role="note">
            Admin access is required to approve or reject production actions. You can still review the decision, evidence, and audit history.
          </div>
        ) : null}
      </section>

      <OperationalHandoff row={row} />

      <section className="approval-v2-tabs" aria-label="Approval detail tabs">
        <div className="approval-v2-tab-list" role="tablist" aria-label="Approval details">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`approval-tab-${tab.id}`}
              aria-controls={`approval-panel-${tab.id}`}
              aria-selected={activeTab === tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`approval-v2-tab${activeTab === tab.id ? " is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div
          className="approval-v2-tab-panel"
          role="tabpanel"
          id={`approval-panel-${activeTab}`}
          aria-labelledby={`approval-tab-${activeTab}`}
        >
          {activeTab === "decision" ? (
            <div className="approval-v2-tab-stack">
              {row.status === "blocked" ? null : <ApproverChain row={row} />}
              <section className={`approval-v2-intent-card approval-v2-tone-${row.statusTone}`}>
                <div>
                  <span className="approval-v2-eyebrow">Action intent</span>
                  <strong>{row.kind === "guard_only_hold" ? "Guard-only runtime decision" : field(row.intentStatus, "Intent held")}</strong>
                  <p>
                    {row.kind === "guard_only_hold"
                      ? "This lower-level guard decision did not create a kernel action intent, so execution and receipt are partial."
                      : `${row.actionType} / ${row.operationKind ?? "operation"} / ${row.environment ?? "environment"}`}
                  </p>
                </div>
                <div className="approval-v2-status-stack">
                  <StatusPill value={row.proofStatus ?? "not_verified"} />
                  <StatusPill value={row.receiptStatus ?? "missing"} />
                </div>
              </section>
              <ProofChainStepper steps={row.proofChain} variant="compact" />
              <FactGrid facts={actionFacts} />
              <section className="approval-v2-mechanism">
                <div className="approval-v2-section-head">
                  <div>
                    <span className="approval-v2-eyebrow">Decision mechanism</span>
                    <strong>{mechanismCopy}</strong>
                  </div>
                  <StatusPill value={row.decision.decision} label={humanize(row.decision.decision)} tone={row.statusTone} />
                </div>
                <FactGrid facts={decisionFacts} />
              </section>
            </div>
          ) : null}

          {activeTab === "evidence" ? (
            <CompactEvidence
              pack={pack}
              packError={packError}
              packLoading={packLoading}
              row={row}
            />
          ) : null}

          {activeTab === "audit" ? <AuditTrail row={row} /> : null}

          {activeTab === "raw" ? <JsonSections sections={jsonSections} /> : null}
        </div>
      </section>
    </section>
  );
}
