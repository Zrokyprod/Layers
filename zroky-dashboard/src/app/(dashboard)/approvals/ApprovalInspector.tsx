"use client";

import { useEffect, useState } from "react";
import { Check, FileText, X } from "lucide-react";

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
  onApprove: (id: string, reason: string) => void;
  onReject: (id: string, reason: string) => void;
};

const TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: "decision", label: "Decision" },
  { id: "evidence", label: "Evidence" },
  { id: "audit", label: "Audit" },
  { id: "raw", label: "Raw" },
];

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
  return required > 1 && remaining > 1 ? "Record Approval" : "Approve";
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

export function ApprovalInspector({
  busy,
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
        <h2>Select a held action</h2>
        <p>High-risk agent actions appear here before commit when policy requires human review.</p>
      </section>
    );
  }

  const canResolve = row.status === "pending_approval";
  const disabled = busy || !canResolve || reason.trim().length < 3;
  const required = requiredApprovals(row);
  const recorded = recordedApprovals(row);
  const approvalCopy = required > 1 ? `${recorded}/${required} approvals recorded` : row.approvalProgress;
  const actionFacts: Fact[] = [
    { label: "Action ID", value: row.actionId, mono: true },
    { label: "Decision ID", value: row.decisionId, mono: true },
    { label: "Digest", value: row.digest, mono: true },
    { label: "System", value: row.systemRef, mono: true },
    { label: "Environment", value: row.environment },
    { label: "Operation", value: row.operationKind ? humanize(row.operationKind) : null },
    { label: "Expires", value: timeUntil(row.expiresAt) },
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
          <span className="approval-v2-eyebrow">Selected hold</span>
          <h2>{row.title}</h2>
          <p>
            {row.agentName} / {row.kind === "guard_only_hold" ? "Guard-only decision" : row.actionType}
          </p>
        </div>
        <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
      </header>

      <section className="approval-v2-console" aria-label="Approve or reject action">
        <div>
          <span className="approval-v2-eyebrow">Decision console</span>
          <strong>{canResolve ? "Approve or reject this exact held action" : "Decision already resolved"}</strong>
          <p>
            {canResolve
              ? "A reason is required. Approval is bound to this decision and the backend advances linked action-intents."
              : "Resolved decisions remain visible here for audit and evidence review."}
          </p>
        </div>
        <div className="approval-v2-resolution">
          <span>{approvalCopy}</span>
          <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
        </div>
        {canResolve ? (
          <div className="approval-v2-actions">
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason for approving or rejecting"
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
              Reject
            </DashboardButton>
          </div>
        ) : null}
      </section>

      <section className="approval-v2-tabs" aria-label="Approval detail tabs">
        <div className="approval-v2-tab-list" role="tablist" aria-label="Approval details">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`approval-v2-tab${activeTab === tab.id ? " is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="approval-v2-tab-panel" role="tabpanel">
          {activeTab === "decision" ? (
            <div className="approval-v2-tab-stack">
              <section className={`approval-v2-intent-card approval-v2-tone-${row.statusTone}`}>
                <div>
                  <span className="approval-v2-eyebrow">Action intent</span>
                  <strong>{row.kind === "guard_only_hold" ? "Guard-only runtime decision" : field(row.intentStatus, "Intent held")}</strong>
                  <p>
                    {row.kind === "guard_only_hold"
                      ? "This guard() decision did not create a kernel action intent, so execution and receipt are partial."
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
                    <strong>Policy gate is the mechanism; the action intent is the thing being held.</strong>
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
