"use client";

import { useState } from "react";
import { Copy, Download, ExternalLink, Printer, ShieldCheck } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import type { EvidenceLedgerRow } from "@/lib/evidence-ledger";
import { actionReceiptPublicKeyUrl } from "@/lib/evidence-verification";
import { formatDateTime, humanize } from "@/lib/format";

type FocusedProofPanelProps = {
  evidenceError: Error | null;
  evidencePack: RuntimePolicyEvidencePackResponse | undefined;
  isExporting: boolean;
  isEvidenceLoading: boolean;
  isReceiptLoading: boolean;
  onExport: () => void;
  onPrint: () => void;
  receipt: ActionReceiptResponse | undefined;
  receiptError: Error | null;
  row: EvidenceLedgerRow | null;
};

type ProofFact = {
  label: string;
  value: string;
  mono?: boolean;
};

type ProofPathStep = {
  detail: string;
  label: string;
  status: string;
  tone: "danger" | "neutral" | "success" | "warning";
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

function valueFrom(record: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value != null && value !== "") return value;
  }
  return null;
}

function readable(value: unknown, fallback = "-"): string {
  const text = typeof value === "string" ? value : value == null ? "" : String(value);
  return text.trim() ? humanize(text) : fallback;
}

function mandateSnapshotLabel(snapshot: unknown): string {
  const record = recordFrom(snapshot);
  const mandate = stringFrom(valueFrom(record, "mandate", "name", "policy_name"));
  if (mandate) return mandate;
  const resolution = recordFrom(record._runtime_policy_resolution);
  const source = stringFrom(resolution.source);
  const fieldCount = Object.keys(record).length;
  if (source) return `${readable(source)} snapshot`;
  if (fieldCount > 0) return `${fieldCount} policy fields captured`;
  return "Captured";
}

function unavailableCopy(row: EvidenceLedgerRow | null): string {
  if (!row) {
    return "Select a ledger row to inspect the signed receipt or Evidence Pack.";
  }
  if (!row.exportable) {
    return row.detail || "This record is visible for honesty, but it is not linked to an exportable receipt or Evidence Pack.";
  }
  return "The selected proof could not be loaded. Keep the row status visible and retry from the source record.";
}

function unavailableTitle(row: EvidenceLedgerRow): string {
  return ["blocked", "denied", "rejected", "expired", "cancelled"].includes(row.status)
    ? "Receipt not expected"
    : "Not linked / not exportable";
}

function verificationSummary({
  evidencePack,
  receipt,
  row,
}: {
  evidencePack: RuntimePolicyEvidencePackResponse | undefined;
  receipt: ActionReceiptResponse | undefined;
  row: EvidenceLedgerRow | null;
}) {
  if (receipt) {
    const hash = receipt.evidence_hash ?? row?.digest ?? null;
    return {
      algorithm: receipt.signature_algorithm,
      digest: receipt.receipt_digest,
      fingerprint: hash ?? receipt.receipt_digest,
      label: "Action Receipt",
      publicKeyHref: actionReceiptPublicKeyUrl(),
      status: receipt.signature_valid ? "Server-attested signature valid" : "Signature review required",
      tone: receipt.signature_valid ? "success" : "danger",
    };
  }
  if (evidencePack) {
    return {
      algorithm: evidencePack.hash_algorithm,
      digest: null,
      fingerprint: evidencePack.evidence_hash,
      label: "Evidence Pack",
      status: evidencePack.verification_status === "pass" ? "Evidence hash passed" : "Evidence needs review",
      tone: evidencePack.verification_status === "pass" ? "success" : "warning",
    };
  }
  if (row?.digest) {
    return {
      algorithm: "sha256",
      digest: row.digest,
      fingerprint: row.digest,
      label: row.sourceLabel,
      status: "Digest available",
      tone: row.tone,
    };
  }
  return null;
}

function receiptProofPath(receipt: ActionReceiptResponse): ProofPathStep[] {
  const core = receipt.receipt;
  const intent = recordFrom(core.intent);
  const policyDecision = recordFrom(core.policy_decision);
  const runnerExecution = recordFrom(core.runner_execution);
  const verification = recordFrom(core.verification);
  const outcomes = recordsFrom(verification.outcomes);
  const firstOutcome = outcomes[0] ?? {};
  const actionType = stringFrom(valueFrom(intent, "action_type")) ?? receipt.action_id;
  const policyStatus = stringFrom(valueFrom(policyDecision, "status", "decision"));
  const runnerStatus = stringFrom(valueFrom(runnerExecution, "status"));
  const verificationStatus = stringFrom(valueFrom(verification, "status", "verdict")) ?? stringFrom(valueFrom(firstOutcome, "verdict"));

  return [
    {
      detail: readable(actionType),
      label: "Intent",
      status: stringFrom(intent.intent_digest) ? "Recorded" : "Missing",
      tone: stringFrom(intent.intent_digest) ? "success" : "warning",
    },
    {
      detail: readable(valueFrom(policyDecision, "decision", "status"), "Not linked"),
      label: "Policy",
      status: readable(policyStatus, "Not linked"),
      tone: policyStatus ? "success" : "warning",
    },
    {
      detail: stringFrom(valueFrom(runnerExecution, "runner_id")) ?? "Runner record",
      label: "Runner",
      status: readable(runnerStatus, "Not attempted"),
      tone: runnerStatus === "failed" ? "danger" : runnerStatus ? "success" : "warning",
    },
    {
      detail: stringFrom(valueFrom(firstOutcome, "system_ref")) ?? "Source record",
      label: "Record",
      status: readable(verificationStatus, "Not verified"),
      tone: verificationStatus === "matched" || verificationStatus === "verified" ? "success" : verificationStatus ? "warning" : "neutral",
    },
    {
      detail: receipt.signature_algorithm,
      label: "Receipt",
      status: receipt.signature_valid ? "Signed" : "Review",
      tone: receipt.signature_valid ? "success" : "danger",
    },
  ];
}

function evidencePackProofPath(pack: RuntimePolicyEvidencePackResponse): ProofPathStep[] {
  return [
    {
      detail: pack.decision.tool_name ?? pack.decision.action_type ?? "Runtime action",
      label: "Decision",
      status: readable(pack.decision.decision),
      tone: pack.decision.allowed ? "success" : "warning",
    },
    {
      detail: pack.decision.resolved_by ?? "Policy owner",
      label: "Approval",
      status: readable(pack.decision.status),
      tone: pack.decision.status === "rejected" ? "danger" : pack.decision.status ? "success" : "warning",
    },
    {
      detail: `${pack.outcome_reconciliation.length} linked`,
      label: "Record",
      status: pack.verification_status === "pass" ? "Verified" : "Review",
      tone: pack.verification_status === "pass" ? "success" : "warning",
    },
  ];
}

function ProofPath({ steps }: { steps: ProofPathStep[] }) {
  return (
    <ol className="ev-proof-path" aria-label="Proof path">
      {steps.map((step) => (
        <li key={step.label} data-tone={step.tone}>
          <span aria-hidden="true" />
          <div>
            <strong>{step.label}</strong>
            <small>{step.detail}</small>
          </div>
          <em>{step.status}</em>
        </li>
      ))}
    </ol>
  );
}

function ProofFacts({ facts }: { facts: ProofFact[] }) {
  return (
    <dl className="ev-proof-facts">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.mono ? <code>{fact.value}</code> : fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CompactReceiptProof({ receipt }: { receipt: ActionReceiptResponse }) {
  const facts: ProofFact[] = [
    { label: "Receipt digest", value: receipt.receipt_digest, mono: true },
    { label: "Evidence hash", value: receipt.evidence_hash ?? "-", mono: true },
    { label: "Signing key", value: receipt.signing_key_id, mono: true },
    { label: "Generated", value: formatDateTime(receipt.generated_at) },
  ];

  return (
    <div className="ev-proof-simple" aria-label="Action Receipt">
      <header className="ev-proof-simple-head">
        <div>
          <span className="ev-eyebrow">Evidence + Signature</span>
          <h3>Receipt is signed and checkable</h3>
        </div>
        <StatusPill
          value={receipt.signature_valid ? "signature_valid" : "signature_invalid"}
          label={receipt.signature_valid ? "Signature valid" : "Signature review"}
          tone={receipt.signature_valid ? "success" : "danger"}
        />
      </header>
      <ProofPath steps={receiptProofPath(receipt)} />
      <ProofFacts facts={facts} />
      <p className="ev-proof-note">
        Signature validity is server-attested here and independently checkable with the published Ed25519 public key.
      </p>
    </div>
  );
}

function CompactEvidencePackProof({ pack }: { pack: RuntimePolicyEvidencePackResponse }) {
  const facts: ProofFact[] = [
    { label: "Decision ID", value: pack.decision_id, mono: true },
    { label: "Evidence hash", value: pack.evidence_hash, mono: true },
    { label: "Generated", value: formatDateTime(pack.generated_at) },
    { label: "Outcome checks", value: String(pack.outcome_reconciliation.length) },
    { label: "Mandate snapshot", value: mandateSnapshotLabel(pack.decision.policy_snapshot) },
    { label: "Approval audit", value: `${pack.audit_log.length} event${pack.audit_log.length === 1 ? "" : "s"}` },
  ];

  return (
    <div className="ev-proof-simple" aria-label="Runtime policy Evidence Pack">
      <header className="ev-proof-simple-head">
        <div>
          <span className="ev-eyebrow">Evidence Pack</span>
          <h3>Runtime decision proof</h3>
        </div>
        <StatusPill value={pack.verification_status} label={readable(pack.verification_status)} tone={pack.verification_status === "pass" ? "success" : "warning"} />
      </header>
      <ProofPath steps={evidencePackProofPath(pack)} />
      <ProofFacts facts={facts} />
    </div>
  );
}

export function FocusedProofPanel({
  evidenceError,
  evidencePack,
  isExporting,
  isEvidenceLoading,
  isReceiptLoading,
  onExport,
  onPrint,
  receipt,
  receiptError,
  row,
}: FocusedProofPanelProps) {
  const [copyState, setCopyState] = useState("");
  const isLoading = isEvidenceLoading || isReceiptLoading;
  const error = receiptError ?? evidenceError;
  const loaded = Boolean(receipt || evidencePack);
  const canExport = Boolean(row?.exportable) && !isLoading && !isExporting;
  const canPrint = loaded && !isLoading;
  const verification = verificationSummary({ evidencePack, receipt, row });

  async function copyFingerprint() {
    if (!verification?.fingerprint) return;
    try {
      await navigator.clipboard.writeText(verification.fingerprint);
      setCopyState("Copied");
    } catch {
      setCopyState("Copy failed");
    }
  }

  return (
    <aside className="ev-proof-panel" aria-label="Focused proof panel">
      <section className="ev-focused-card">
        <div className="ev-focused-head">
          <div className="ev-focused-copy">
            <span className="ev-eyebrow">Selected proof</span>
            <h2>{row?.title ?? "No proof selected"}</h2>
            <p>{row ? `${row.sourceLabel} / ${row.actionType}` : unavailableCopy(row)}</p>
          </div>
          {row ? <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} /> : null}
        </div>
        <div className="ev-proof-actions">
          <DashboardButton icon={<Printer />} disabled={!canPrint} onClick={onPrint} variant="soft">
            Print
          </DashboardButton>
          <DashboardButton icon={<Download />} disabled={!canExport} onClick={onExport} variant="primary">
            {isExporting ? "Exporting" : row?.exportKind === "receipt" ? "Export receipt JSON" : "Export proof JSON"}
          </DashboardButton>
        </div>
        {verification ? (
          <section className="ev-external-verify" aria-label="Independent verification material">
            <div>
              <ShieldCheck size={16} aria-hidden="true" />
              <span>
                <strong>{verification.status}</strong>
                <small>{verification.label} / {verification.algorithm}</small>
              </span>
            </div>
            <code>{verification.fingerprint}</code>
            <div className="ev-external-verify-actions">
              <DashboardButton icon={<Copy size={14} />} onClick={() => void copyFingerprint()} size="sm" variant="soft">
                {copyState || "Copy fingerprint"}
              </DashboardButton>
              {"publicKeyHref" in verification && verification.publicKeyHref ? (
                <DashboardButtonLink
                  href={verification.publicKeyHref}
                  icon={<ExternalLink size={14} />}
                  size="sm"
                  target="_blank"
                  variant="ghost"
                >
                  Open public key
                </DashboardButtonLink>
              ) : null}
            </div>
          </section>
        ) : null}
        {row ? (
          <dl className="ev-focused-meta">
            <div>
              <dt>System</dt>
              <dd>{row.systemRef ?? "-"}</dd>
            </div>
            <div>
              <dt>Export</dt>
              <dd>{row.exportable ? row.exportKind : "not exportable"}</dd>
            </div>
            <div>
              <dt>Checked</dt>
              <dd>{formatDateTime(row.checkedAt)}</dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="ev-proof-detail" aria-label="Selected proof detail">
        {!row ? (
          <div className="ev-empty-state">{unavailableCopy(row)}</div>
        ) : !row.exportable ? (
          <div className="ev-empty-state">
            <strong>{unavailableTitle(row)}</strong>
            <span>{unavailableCopy(row)}</span>
          </div>
        ) : isLoading ? (
          <div className="ev-skeleton-list" aria-label="Loading selected proof">
            <span />
            <span />
            <span />
          </div>
        ) : error ? (
          <div className="ev-empty-state">
            <strong>Proof unavailable</strong>
            <span>{error.message || unavailableCopy(row)}</span>
          </div>
        ) : receipt ? (
          <CompactReceiptProof receipt={receipt} />
        ) : evidencePack ? (
          <CompactEvidencePackProof pack={evidencePack} />
        ) : (
          <div className="ev-empty-state">{unavailableCopy(row)}</div>
        )}
      </section>
    </aside>
  );
}
