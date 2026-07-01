"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import type {
  ActionReceiptResponse,
  OutcomeReconciliationView,
  RuntimePolicyEvidenceAuditEventResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { statusLabel, statusTone, type StatusTone } from "@/lib/action-status";
import { compactJson, field, formatDateTime, humanize } from "@/lib/format";
import type { ProofChainStep, ProofChainStepId } from "@/lib/action-view";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";

export type EvidencePackMode = "compact" | "full";

type EvidencePackViewProps =
  | {
      pack: RuntimePolicyEvidencePackResponse;
      title?: string;
      mode?: EvidencePackMode;
    }
  | {
      receipt: ActionReceiptResponse;
      title?: string;
      mode?: EvidencePackMode;
    };

type EvidenceFact = {
  label: string;
  value: ReactNode;
  compact?: boolean;
  mono?: boolean;
  className?: string;
};

type EvidenceSection = {
  id: string;
  title: string;
  meta?: ReactNode;
  compact?: boolean;
  render: () => ReactNode;
};

type ReceiptAccordionSection = EvidenceSection & {
  tone: StatusTone;
  defaultOpen?: boolean;
};

type JsonGroup = {
  title: string;
  value: unknown;
};

function recordFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function recordsFrom(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordFrom).filter((item) => Object.keys(item).length > 0) : [];
}

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function receiptField(receipt: ActionReceiptResponse, key: string): string | null {
  return stringFrom(receipt.receipt[key]);
}

function valueFrom(record: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value != null && value !== "") {
      return value;
    }
  }
  return null;
}

function visibleFacts(facts: EvidenceFact[], mode: EvidencePackMode): EvidenceFact[] {
  return facts.filter((fact) => mode === "full" || fact.compact);
}

function visibleSections(sections: EvidenceSection[], mode: EvidencePackMode): EvidenceSection[] {
  return sections.filter((section) => mode === "full" || section.compact);
}

function FactValue({ fact }: { fact: EvidenceFact }) {
  if (fact.mono) {
    return <code>{fact.value}</code>;
  }
  return <>{fact.value}</>;
}

function FactGrid({ facts, mode }: { facts: EvidenceFact[]; mode: EvidencePackMode }) {
  const shown = visibleFacts(facts, mode);
  if (shown.length === 0) {
    return null;
  }
  return (
    <dl className={`evidence-pack-proof-grid${mode === "compact" ? " compact" : ""}`}>
      {shown.map((fact) => (
        <div key={fact.label} className={fact.className}>
          <dt>{fact.label}</dt>
          <dd>
            <FactValue fact={fact} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function EvidenceSections({ sections, mode }: { sections: EvidenceSection[]; mode: EvidencePackMode }) {
  return (
    <>
      {visibleSections(sections, mode).map((section) => (
        <section key={section.id} className="evidence-pack-section">
          <div className="evidence-pack-section-heading">
            <h4>{section.title}</h4>
            {section.meta == null ? null : <span>{section.meta}</span>}
          </div>
          {section.render()}
        </section>
      ))}
    </>
  );
}

function ReceiptAccordionSections({
  openIds,
  sections,
  setOpenIds,
}: {
  openIds: Set<string>;
  sections: ReceiptAccordionSection[];
  setOpenIds: (updater: (current: Set<string>) => Set<string>) => void;
}) {
  return (
    <div className="evidence-receipt-accordions">
      {sections.map((section) => {
        const open = openIds.has(section.id);
        return (
          <details
            key={section.id}
            id={`receipt-section-${section.id}`}
            className="evidence-receipt-accordion"
            data-tone={section.tone}
            open={open}
            onToggle={(event) => {
              const isOpen = event.currentTarget.open;
              setOpenIds((current) => {
                const next = new Set(current);
                if (isOpen) {
                  next.add(section.id);
                } else {
                  next.delete(section.id);
                }
                return next;
              });
            }}
          >
            <summary>
              <span className="evidence-receipt-accordion-dot" aria-hidden="true" />
              <span>{section.title}</span>
              {section.meta == null ? null : <small>{section.meta}</small>}
            </summary>
            <div className="evidence-receipt-accordion-body">{section.render()}</div>
          </details>
        );
      })}
    </div>
  );
}

function monoReference(value: string | null | undefined): ReactNode {
  if (!value) {
    return "-";
  }
  return <code>{value}</code>;
}

function hasJsonValue(value: unknown): boolean {
  if (value == null || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(recordFrom(value)).length > 0;
  }
  return true;
}

function JsonGrid({ groups }: { groups: JsonGroup[] }) {
  const visible = groups.filter((group) => hasJsonValue(group.value));
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className="evidence-pack-json-grid">
      {visible.map((group) => (
        <section key={group.title}>
          <h4>{group.title}</h4>
          <pre>{compactJson(group.value)}</pre>
        </section>
      ))}
    </div>
  );
}

function formatOutcomeAmount(outcome: OutcomeReconciliationView): string {
  if (outcome.amount_usd == null) {
    return "-";
  }
  return `${outcome.amount_usd} ${outcome.currency ?? "USD"}`;
}

function outcomeJsonGroups(outcome: OutcomeReconciliationView): Array<{ title: string; value: unknown }> {
  return [
    { title: "Agent claim", value: outcome.claimed },
    { title: "Actual system record", value: outcome.actual },
    { title: "Field comparison", value: outcome.comparison },
  ];
}

function OutcomeJson({ outcome, mode }: { outcome: OutcomeReconciliationView; mode: EvidencePackMode }) {
  const groups = outcomeJsonGroups(outcome);
  if (mode === "compact") {
    return (
      <pre>
        {compactJson({
          claimed: groups[0]?.value,
          actual: groups[1]?.value,
          comparison: groups[2]?.value,
        })}
      </pre>
    );
  }
  return <JsonGrid groups={groups} />;
}

function OutcomeArticle({ outcome, mode }: { outcome: OutcomeReconciliationView; mode: EvidencePackMode }) {
  const tone = statusTone(outcome.verdict, "proof");
  const facts: EvidenceFact[] = [
    { label: "Action", value: humanize(outcome.action_type), compact: false },
    { label: "Amount", value: formatOutcomeAmount(outcome), compact: false },
    { label: "Checked", value: formatDateTime(outcome.checked_at), compact: false },
    { label: "Check ID", value: outcome.id, compact: false, mono: true },
  ];

  return (
    <article className={`evidence-pack-outcome tone-${tone} evidence-pack-outcome-${tone}`}>
      <div className="evidence-pack-outcome-head">
        <div>
          <span className="eyebrow">{outcome.connector_type}</span>
          <strong>{outcome.system_ref ?? outcome.id}</strong>
          <p>{outcome.reason ? humanize(outcome.reason) : "Outcome comparison"}</p>
        </div>
        <StatusPill value={outcome.verdict} kind="proof" />
      </div>
      <FactGrid facts={facts} mode={mode} />
      <OutcomeJson outcome={outcome} mode={mode} />
    </article>
  );
}

function AuditList({ auditLog }: { auditLog: RuntimePolicyEvidenceAuditEventResponse[] }) {
  if (auditLog.length === 0) {
    return <p className="evidence-pack-muted">No approval audit events captured.</p>;
  }
  return (
    <ol className="evidence-pack-audit-list">
      {auditLog.map((event) => (
        <li key={event.id}>
          <div>
            <strong>{humanize(event.event_type)}</strong>
            <span>{event.created_at ? formatDateTime(event.created_at) : "-"}</span>
          </div>
          <p>
            {event.actor ? `${event.actor}: ` : ""}
            {event.reason ?? "-"}
          </p>
        </li>
      ))}
    </ol>
  );
}

function RuntimePolicyEvidencePackView({
  pack,
  title,
  mode,
}: {
  pack: RuntimePolicyEvidencePackResponse;
  title?: string;
  mode: EvidencePackMode;
}) {
  const decisionTitle =
    title ??
    (typeof pack.decision.intended_action.summary === "string" && pack.decision.intended_action.summary.trim()
      ? pack.decision.intended_action.summary
      : pack.decision.tool_name ?? pack.decision.action_type ?? pack.decision_id);
  const decisionFacts: EvidenceFact[] = [
    { label: "Status", value: pack.decision.status, compact: false },
    { label: "Runtime decision", value: pack.decision.decision, compact: false },
    { label: "Tool", value: pack.decision.tool_name ?? "-", compact: false },
    { label: "Approval scope", value: pack.decision.approval_scope_hash ?? "-", compact: false, mono: true },
    { label: "Resolved by", value: pack.decision.resolved_by ?? "-", compact: false },
    { label: "Resolved", value: formatDateTime(pack.decision.resolved_at), compact: false },
  ];
  const proofFacts: EvidenceFact[] = [
    { label: "Decision ID", value: pack.decision_id, compact: true, mono: true },
    { label: "Generated", value: formatDateTime(pack.generated_at), compact: true },
    { label: "Evidence hash", value: pack.evidence_hash, compact: true, mono: true, className: "evidence-pack-hash-cell" },
    { label: "Outcome checks", value: pack.outcome_reconciliation.length, compact: true },
    { label: "Audit events", value: pack.audit_log.length, compact: true },
    { label: "Schema", value: pack.schema_version, compact: true },
    { label: "Hash algorithm", value: pack.hash_algorithm, mono: true },
    { label: "Hash excludes", value: pack.hash_payload_excludes.join(", ") || "nothing" },
    { label: "Trace evidence", value: monoReference(pack.decision.trace_id) },
    { label: "Call evidence", value: monoReference(pack.decision.call_id) },
  ];
  const sections: EvidenceSection[] = [
    {
      id: "policy-decision",
      title: "Policy decision",
      meta: `${humanize(pack.decision.decision)} / ${humanize(pack.decision.status)}`,
      compact: true,
      render: () => (
        <>
          <FactGrid facts={decisionFacts} mode={mode} />
          <pre>{compactJson(pack.decision.intended_action)}</pre>
        </>
      ),
    },
    {
      id: "mandate-snapshot",
      title: "Mandate snapshot",
      meta: "Mandate at decision time",
      compact: false,
      render: () => <pre>{compactJson(pack.decision.policy_snapshot)}</pre>,
    },
    {
      id: "approval-audit",
      title: "Approval audit",
      meta: `${pack.audit_log.length} event${pack.audit_log.length === 1 ? "" : "s"}`,
      compact: false,
      render: () => <AuditList auditLog={pack.audit_log} />,
    },
    {
      id: "outcome-reconciliation",
      title: "Outcome reconciliation",
      meta: `${pack.outcome_reconciliation.length} linked`,
      compact: true,
      render: () =>
        pack.outcome_reconciliation.length === 0 ? (
          <p className="evidence-pack-muted">No system-of-record outcome proof is linked.</p>
        ) : (
          <div className="evidence-pack-outcomes">
            {pack.outcome_reconciliation.map((outcome) => (
              <OutcomeArticle key={outcome.id} outcome={outcome} mode={mode} />
            ))}
          </div>
        ),
    },
  ];

  return (
    <section className="evidence-pack-view" aria-label="Runtime policy Evidence Pack">
      <header className="evidence-pack-section-heading">
        <div>
          <span className="eyebrow">Evidence Pack</span>
          <h3>{decisionTitle}</h3>
          {mode === "full" ? (
            <p className="evidence-pack-muted">
              Proof is based on runtime policy, approval audit, and system-of-record verification. AI summaries are advisory and are not proof.
            </p>
          ) : null}
        </div>
        <StatusPill
          value={pack.verification_status}
          label={statusLabel(pack.verification_status)}
          tone={statusTone(pack.verification_status)}
        />
      </header>

      <FactGrid facts={proofFacts} mode={mode} />
      <EvidenceSections sections={sections} mode={mode} />
    </section>
  );
}

function ReceiptOutcomeList({ outcomes }: { outcomes: Record<string, unknown>[] }) {
  if (outcomes.length === 0) {
    return <p className="evidence-pack-muted">No system-of-record outcome proof is linked.</p>;
  }
  return (
    <div className="evidence-pack-receipt-outcomes">
      {outcomes.map((outcome, index) => {
        const verdict = field(valueFrom(outcome, "verdict", "verification_status"), "not_verified");
        return (
          <article key={field(valueFrom(outcome, "id"), `outcome-${index}`)} className="evidence-pack-receipt-outcome">
            <div className="evidence-pack-outcome-head">
              <div>
                <span className="eyebrow">{field(valueFrom(outcome, "connector_type"), "connector")}</span>
                <strong>{field(valueFrom(outcome, "system_ref", "id"), `Outcome ${index + 1}`)}</strong>
                <p>{humanize(stringFrom(valueFrom(outcome, "reason")) ?? "Outcome proof")}</p>
              </div>
              <StatusPill value={verdict} label={statusLabel(verdict)} tone={statusTone(verdict)} />
            </div>
            <FactGrid
              facts={[
                { label: "Outcome ID", value: field(valueFrom(outcome, "id")), mono: true },
                { label: "Verification", value: field(valueFrom(outcome, "verification_status")) },
                { label: "Idempotency", value: field(valueFrom(outcome, "idempotency_key")), mono: true },
                { label: "Checked", value: formatDateTime(stringFrom(valueFrom(outcome, "checked_at"))) },
              ]}
              mode="full"
            />
          </article>
        );
      })}
    </div>
  );
}

function ReceiptTimeline({ timeline }: { timeline: Record<string, unknown>[] }) {
  if (timeline.length === 0) {
    return <p className="evidence-pack-muted">No action timeline events captured.</p>;
  }
  return (
    <ol className="evidence-pack-audit-list evidence-pack-timeline-list">
      {timeline.map((event, index) => (
        <li key={field(valueFrom(event, "id"), `event-${index}`)}>
          <div>
            <strong>{humanize(stringFrom(valueFrom(event, "event_type")) ?? "Timeline event")}</strong>
            <span>{formatDateTime(stringFrom(valueFrom(event, "created_at")))}</span>
          </div>
          <p>
            {stringFrom(valueFrom(event, "actor")) ? `${stringFrom(valueFrom(event, "actor"))}: ` : ""}
            <code>{field(valueFrom(event, "event_digest"))}</code>
          </p>
        </li>
      ))}
    </ol>
  );
}

function FullReceiptJson({ receipt }: { receipt: ActionReceiptResponse }) {
  return (
    <details className="evidence-pack-raw-json">
      <summary>Full receipt JSON</summary>
      <pre>{compactJson(receipt.receipt)}</pre>
    </details>
  );
}

function normalizeStatusValue(value: unknown): string {
  return stringFrom(value)?.toLowerCase() ?? "";
}

function policyTone(policyDecision: Record<string, unknown>): StatusTone {
  if (Object.keys(policyDecision).length === 0) {
    return "warning";
  }
  return statusTone(stringFrom(valueFrom(policyDecision, "status", "decision")), "runtime_policy");
}

function executionTone(runnerExecution: Record<string, unknown>): StatusTone {
  if (Object.keys(runnerExecution).length === 0) {
    return "warning";
  }
  const status = normalizeStatusValue(runnerExecution.status);
  if (["failed", "error", "cancelled"].includes(status)) {
    return "danger";
  }
  if (["completed", "succeeded", "success", "successful"].includes(status)) {
    return "success";
  }
  if (["ambiguous", "running", "planned", "dispatched", "pending"].includes(status)) {
    return "warning";
  }
  return statusTone(status || "not_verified");
}

function verificationTone(verificationStatus: string): StatusTone {
  return statusTone(verificationStatus, "proof");
}

function sectionShouldOpen(tone: StatusTone): boolean {
  return tone === "danger" || tone === "warning";
}

function receiptSectionForStep(step: ProofChainStepId): string {
  if (step === "action") return "action-intent";
  if (step === "policy") return "policy-decision";
  if (step === "execution") return "runner-execution";
  if (step === "verification") return "verification";
  return "evidence-signature";
}

function ProofSeal({
  evidence,
  receipt,
}: {
  evidence: Record<string, unknown>;
  receipt: ActionReceiptResponse;
}) {
  return (
    <section className="evidence-proof-seal" aria-label="Proof seal">
      <div>
        <span className="eyebrow">Proof seal</span>
        <h4>Tamper-evident receipt</h4>
        <p>Signature and hashes are verified server-side; the browser never receives the signing secret.</p>
      </div>
      <dl>
        <div>
          <dt>Signature</dt>
          <dd>
            <StatusPill
              value={receipt.signature_valid ? "signature_valid" : "signature_invalid"}
              label={receipt.signature_valid ? "Valid" : "Invalid"}
              tone={receipt.signature_valid ? "success" : "danger"}
            />
          </dd>
        </div>
        <div>
          <dt>Receipt digest</dt>
          <dd>
            <code>{receipt.receipt_digest}</code>
          </dd>
        </div>
        <div>
          <dt>Evidence hash</dt>
          <dd>
            <code>{field(valueFrom(evidence, "evidence_hash") ?? receipt.evidence_hash)}</code>
          </dd>
        </div>
        <div>
          <dt>Hash algorithm</dt>
          <dd>
            <code>{field(valueFrom(evidence, "hash_algorithm"), "sha256")}</code>
          </dd>
        </div>
        <div>
          <dt>Signing key</dt>
          <dd>
            <code>{receipt.signing_key_id}</code>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ActionReceiptView({
  receipt,
  title,
  mode,
}: {
  receipt: ActionReceiptResponse;
  title?: string;
  mode: EvidencePackMode;
}) {
  const core = receipt.receipt;
  const intent = recordFrom(core.intent);
  const actionContract = recordFrom(core.action_contract);
  const policyDecision = recordFrom(core.policy_decision);
  const runnerExecution = recordFrom(core.runner_execution);
  const verification = recordFrom(core.verification);
  const evidence = recordFrom(core.evidence);
  const outcomes = recordsFrom(verification.outcomes);
  const timeline = recordsFrom(core.timeline);
  const finalStatus = stringFrom(core.final_status) ?? receiptField(receipt, "proof_status") ?? "generated";
  const policyStepTone = policyTone(policyDecision);
  const executionStepTone = executionTone(runnerExecution);
  const verificationStatus = stringFrom(valueFrom(verification, "status", "verdict")) ?? finalStatus;
  const verificationStepTone = verificationTone(verificationStatus);
  const receiptStepTone: StatusTone = receipt.signature_valid ? "success" : "danger";
  const actionStepTone: StatusTone = stringFrom(intent.intent_digest) || stringFrom(actionContract.id) ? "success" : "warning";
  const actionType = stringFrom(intent.action_type) ?? stringFrom(actionContract.action_type) ?? receipt.action_id;
  const operationKind = stringFrom(intent.operation_kind) ?? stringFrom(actionContract.operation_kind);
  const receiptTitle = title ?? actionType ?? receipt.action_id;
  const steps: ProofChainStep[] = [
    {
      step: "action",
      label: "Action",
      status: actionStepTone === "success" ? "recorded" : "incomplete",
      tone: actionStepTone,
      detail: actionStepTone === "success" ? "Action intent is recorded." : "Action intent is incomplete.",
    },
    {
      step: "policy",
      label: "Policy",
      status: statusLabel(stringFrom(valueFrom(policyDecision, "decision", "status")) ?? "not_verified"),
      tone: policyStepTone,
      detail: "Runtime policy decision attached to this receipt.",
    },
    {
      step: "execution",
      label: "Execution",
      status: statusLabel(stringFrom(runnerExecution.status) ?? "not_started"),
      tone: executionStepTone,
      detail: "Protected runner execution attached to this receipt.",
    },
    {
      step: "verification",
      label: "Verification",
      status: statusLabel(verificationStatus, "proof"),
      tone: verificationStepTone,
      detail: "Independent source-of-record verification attached to this receipt.",
    },
    {
      step: "receipt",
      label: "Receipt",
      status: receipt.signature_valid ? "signed" : "invalid",
      tone: receiptStepTone,
      detail: receipt.signature_valid ? "Receipt signature is valid." : "Receipt signature is invalid.",
    },
  ];
  const facts: EvidenceFact[] = [
    { label: "Action ID", value: receipt.action_id, compact: true, mono: true },
    { label: "Receipt ID", value: receipt.receipt_id, compact: true, mono: true },
    { label: "Final status", value: statusLabel(finalStatus), compact: true },
    { label: "Generated", value: formatDateTime(receipt.generated_at), compact: true },
    { label: "Receipt digest", value: receipt.receipt_digest, compact: true, mono: true, className: "evidence-pack-hash-cell" },
    { label: "Evidence hash", value: receipt.evidence_hash ?? "-", compact: true, mono: true, className: "evidence-pack-hash-cell" },
  ];
  const actionFacts: EvidenceFact[] = [
    { label: "Action type", value: humanize(actionType), compact: true },
    { label: "Operation", value: humanize(operationKind), compact: true },
    { label: "Intent digest", value: field(intent.intent_digest), compact: true, mono: true, className: "evidence-pack-hash-cell" },
    { label: "Contract", value: field(valueFrom(intent, "contract_version") ?? valueFrom(actionContract, "contract_version")), compact: true },
    { label: "Idempotency", value: field(intent.idempotency_key), mono: true },
    { label: "Verification profile", value: field(intent.verification_profile) },
    { label: "Created", value: formatDateTime(stringFrom(intent.created_at)) },
    { label: "Authorized", value: formatDateTime(stringFrom(intent.authorized_at)) },
  ];
  const policyFacts: EvidenceFact[] = [
    { label: "Decision", value: field(policyDecision.decision) },
    { label: "Status", value: field(policyDecision.status) },
    { label: "Approval ID", value: field(policyDecision.approval_id), mono: true },
    { label: "Approval scope", value: field(policyDecision.approval_scope_hash), mono: true, className: "evidence-pack-hash-cell" },
    { label: "Resolved by", value: field(policyDecision.resolved_by) },
    { label: "Resolved", value: formatDateTime(stringFrom(policyDecision.resolved_at)) },
    { label: "Approvals", value: `${field(policyDecision.approval_count, "0")} / ${field(policyDecision.required_approval_count, "0")}` },
    { label: "Consumed", value: formatDateTime(stringFrom(policyDecision.consumed_at)) },
  ];
  const runnerFacts: EvidenceFact[] = [
    { label: "Runner", value: field(runnerExecution.runner_id), mono: true },
    { label: "Attempt", value: field(runnerExecution.id), mono: true },
    { label: "Attempt #", value: field(runnerExecution.attempt_number) },
    { label: "Status", value: field(runnerExecution.status) },
    { label: "Credential ref", value: field(runnerExecution.credential_ref), mono: true },
    { label: "Plan digest", value: field(runnerExecution.plan_digest), mono: true, className: "evidence-pack-hash-cell" },
    { label: "Protected credential returned", value: field(runnerExecution.protected_credential_returned) },
    { label: "Finished", value: formatDateTime(stringFrom(runnerExecution.finished_at)) },
  ];
  const verificationFacts: EvidenceFact[] = [
    { label: "Verification status", value: field(valueFrom(verification, "status", "verdict")) },
    { label: "Outcome count", value: outcomes.length },
    { label: "Evidence hash", value: field(valueFrom(evidence, "evidence_hash") ?? receipt.evidence_hash), mono: true, className: "evidence-pack-hash-cell" },
    { label: "Hash algorithm", value: field(valueFrom(evidence, "hash_algorithm"), "sha256"), mono: true },
  ];
  const signatureFacts: EvidenceFact[] = [
    { label: "Signature valid", value: receipt.signature_valid ? "true" : "false", compact: true },
    { label: "Signing key", value: receipt.signing_key_id, compact: true, mono: true },
    { label: "Signature algorithm", value: receipt.signature_algorithm, compact: true },
    { label: "Signature", value: receipt.signature, mono: true, className: "evidence-pack-hash-cell" },
  ];
  const sections: ReceiptAccordionSection[] = [
    {
      id: "action-intent",
      title: "Action / Intent",
      meta: humanize(actionType),
      compact: true,
      defaultOpen: sectionShouldOpen(actionStepTone),
      tone: actionStepTone,
      render: () => (
        <>
          <FactGrid facts={actionFacts} mode={mode} />
          {mode === "full" ? (
            <JsonGrid
              groups={[
                { title: "Principal", value: intent.principal },
                { title: "Actor chain", value: intent.actor_chain },
                { title: "Purpose", value: intent.purpose },
                { title: "Resource", value: intent.resource },
                { title: "Parameters", value: intent.parameters },
                { title: "Canonical intent", value: intent.canonical_intent },
              ]}
            />
          ) : null}
        </>
      ),
    },
    {
      id: "policy-decision",
      title: "Policy decision",
      meta: humanize(stringFrom(policyDecision.status) ?? "not linked"),
      compact: false,
      defaultOpen: sectionShouldOpen(policyStepTone),
      tone: policyStepTone,
      render: () => (
        <>
          <FactGrid facts={policyFacts} mode="full" />
          <JsonGrid
            groups={[
              { title: "Reasons", value: policyDecision.reasons },
              { title: "Approvers", value: policyDecision.approver_subjects },
            ]}
          />
        </>
      ),
    },
    {
      id: "runner-execution",
      title: "Runner execution",
      meta: humanize(stringFrom(runnerExecution.status) ?? "not attempted"),
      compact: false,
      defaultOpen: sectionShouldOpen(executionStepTone),
      tone: executionStepTone,
      render: () => (
        <>
          <FactGrid facts={runnerFacts} mode="full" />
          <JsonGrid groups={[{ title: "Execution plan", value: runnerExecution.plan }]} />
        </>
      ),
    },
    {
      id: "verification",
      title: "Verification",
      meta: humanize(verificationStatus),
      compact: false,
      defaultOpen: sectionShouldOpen(verificationStepTone),
      tone: verificationStepTone,
      render: () => (
        <>
          <FactGrid facts={verificationFacts} mode="full" />
          <ReceiptOutcomeList outcomes={outcomes} />
        </>
      ),
    },
    {
      id: "evidence-signature",
      title: "Evidence + Signature",
      meta: receipt.signature_valid ? "Signature valid" : "Signature invalid",
      compact: true,
      defaultOpen: sectionShouldOpen(receiptStepTone),
      tone: receiptStepTone,
      render: () => (
        <>
          <FactGrid facts={signatureFacts} mode={mode} />
          {mode === "full" ? (
            <p className="evidence-pack-muted">
              Signature validity is verified by the backend; the browser never receives the signing secret.
            </p>
          ) : null}
        </>
      ),
    },
    {
      id: "timeline",
      title: "Timeline",
      meta: `${timeline.length} event${timeline.length === 1 ? "" : "s"}`,
      compact: false,
      defaultOpen: false,
      tone: "neutral",
      render: () => <ReceiptTimeline timeline={timeline} />,
    },
    {
      id: "full-receipt-json",
      title: "Full receipt JSON",
      meta: "Canonical payload",
      compact: false,
      defaultOpen: false,
      tone: "neutral",
      render: () => <FullReceiptJson receipt={receipt} />,
    },
  ];
  const defaultOpenIds = useMemo(() => {
    const ids = new Set<string>();
    if (sectionShouldOpen(actionStepTone)) ids.add("action-intent");
    if (sectionShouldOpen(policyStepTone)) ids.add("policy-decision");
    if (sectionShouldOpen(executionStepTone)) ids.add("runner-execution");
    if (sectionShouldOpen(verificationStepTone)) ids.add("verification");
    if (sectionShouldOpen(receiptStepTone)) ids.add("evidence-signature");
    return ids;
  }, [actionStepTone, executionStepTone, policyStepTone, receiptStepTone, verificationStepTone]);
  const [openSectionIds, setOpenSectionIds] = useState<Set<string>>(defaultOpenIds);

  useEffect(() => {
    setOpenSectionIds(defaultOpenIds);
  }, [defaultOpenIds, receipt.receipt_id]);

  function openSection(id: string) {
    setOpenSectionIds((current) => new Set([...current, id]));
    window.requestAnimationFrame(() => {
      document.getElementById(`receipt-section-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }

  return (
    <section className="evidence-pack-view" aria-label="Action Receipt">
      <header className="evidence-pack-section-heading">
        <div>
          <span className="eyebrow">Action Receipt</span>
          <h3>{receiptTitle}</h3>
          {mode === "full" ? (
            <p className="evidence-pack-muted">
              This signed receipt is deterministic proof. AI summaries may explain it, but cannot change policy or verification status.
            </p>
          ) : null}
        </div>
        <StatusPill
          value={receipt.signature_valid ? "signature_valid" : "signature_invalid"}
          label={receipt.signature_valid ? "Signature valid" : "Signature invalid"}
          tone={receipt.signature_valid ? "success" : "danger"}
        />
      </header>

      <FactGrid facts={facts} mode={mode} />
      <ProofChainStepper
        steps={steps}
        variant="evidence"
        onStepSelect={(step) => openSection(receiptSectionForStep(step.step))}
      />
      <ProofSeal receipt={receipt} evidence={evidence} />
      <ReceiptAccordionSections sections={sections} openIds={openSectionIds} setOpenIds={setOpenSectionIds} />
    </section>
  );
}

export function EvidencePackView(props: EvidencePackViewProps) {
  const mode = props.mode ?? "compact";
  if ("receipt" in props) {
    return <ActionReceiptView receipt={props.receipt} title={props.title} mode={mode} />;
  }
  return <RuntimePolicyEvidencePackView pack={props.pack} title={props.title} mode={mode} />;
}
