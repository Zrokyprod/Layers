"use client";

import { useState } from "react";
import { Copy, Download, ExternalLink, Printer, ShieldCheck } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { EvidencePackView } from "@/components/evidence-pack-view";
import { StatusPill } from "@/components/status-pill";
import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import type { EvidenceLedgerRow } from "@/lib/evidence-ledger";
import { formatDateTime } from "@/lib/format";

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

function unavailableCopy(row: EvidenceLedgerRow | null): string {
  if (!row) {
    return "Select a ledger row to inspect the signed receipt or Evidence Pack.";
  }
  if (!row.exportable) {
    return "This record is visible for honesty, but it is not linked to an exportable receipt or Evidence Pack.";
  }
  return "The selected proof could not be loaded. Keep the row status visible and retry from the source record.";
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
      status: receipt.signature_valid ? "Signature valid" : "Signature review required",
      verifyHref: `https://verify.zroky.com/?digest=${encodeURIComponent(receipt.receipt_digest)}`,
    };
  }
  if (evidencePack) {
    return {
      algorithm: evidencePack.hash_algorithm,
      digest: null,
      fingerprint: evidencePack.evidence_hash,
      label: "Evidence Pack",
      status: evidencePack.verification_status === "pass" ? "Evidence hash passed" : "Evidence needs review",
      verifyHref: `https://verify.zroky.com/?hash=${encodeURIComponent(evidencePack.evidence_hash)}`,
    };
  }
  if (row?.digest) {
    return {
      algorithm: "sha256",
      digest: row.digest,
      fingerprint: row.digest,
      label: row.sourceLabel,
      status: "Digest available",
      verifyHref: `https://verify.zroky.com/?digest=${encodeURIComponent(row.digest)}`,
    };
  }
  return null;
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
        <div className="ev-focused-copy">
          <span className="ev-eyebrow">Selected proof</span>
          <h2>{row?.title ?? "No proof selected"}</h2>
          <p>{row ? `${row.sourceLabel} / ${row.actionType}` : unavailableCopy(row)}</p>
        </div>
        {row ? (
          <dl className="ev-focused-meta">
            <div>
              <dt>Status</dt>
              <dd>
                <StatusPill value={row.status} label={row.statusLabel} tone={row.tone} />
              </dd>
            </div>
            <div>
              <dt>Receipt</dt>
              <dd>{row.exportable ? row.exportKind : "not exportable"}</dd>
            </div>
            <div>
              <dt>Checked</dt>
              <dd>{formatDateTime(row.checkedAt)}</dd>
            </div>
          </dl>
        ) : null}
        <div className="ev-proof-actions">
          <DashboardButton icon={<Printer />} disabled={!canPrint} onClick={onPrint} variant="soft">
            Print
          </DashboardButton>
          <DashboardButton icon={<Download />} disabled={!canExport} onClick={onExport} variant="primary">
            {isExporting ? "Exporting" : row?.exportKind === "receipt" ? "Export receipt JSON" : "Export proof JSON"}
          </DashboardButton>
        </div>
        {verification ? (
          <section className="ev-external-verify" aria-label="External hash verification">
            <div>
              <ShieldCheck size={16} aria-hidden="true" />
              <span>
                <strong>External verification</strong>
                <small>{verification.label} / {verification.status} / {verification.algorithm}</small>
              </span>
            </div>
            <code>{verification.fingerprint}</code>
            <div className="ev-external-verify-actions">
              <DashboardButton icon={<Copy size={14} />} onClick={() => void copyFingerprint()} size="sm" variant="soft">
                {copyState || "Copy fingerprint"}
              </DashboardButton>
              <DashboardButtonLink href={verification.verifyHref} icon={<ExternalLink size={14} />} size="sm" target="_blank" variant="ghost">
                Verify externally
              </DashboardButtonLink>
            </div>
          </section>
        ) : null}
      </section>

      <section className="ev-proof-detail" aria-label="Selected proof detail">
        {!row ? (
          <div className="ev-empty-state">{unavailableCopy(row)}</div>
        ) : !row.exportable ? (
          <div className="ev-empty-state">
            <strong>Not linked / not exportable</strong>
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
          <EvidencePackView receipt={receipt} title={row.title} mode="full" />
        ) : evidencePack ? (
          <EvidencePackView pack={evidencePack} title={row.title} mode="full" />
        ) : (
          <div className="ev-empty-state">{unavailableCopy(row)}</div>
        )}
      </section>
    </aside>
  );
}
