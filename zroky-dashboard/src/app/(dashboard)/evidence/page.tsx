"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, FileJson, Fingerprint, Printer, ShieldCheck } from "lucide-react";

import {
  getRuntimePolicyEvidencePack,
  listOutcomeReconciliations,
  listRuntimePolicyApprovals,
  type OutcomeReconciliationView,
  type RuntimePolicyDecisionResponse,
  type RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type EvidenceRow = {
  key: string;
  decisionId: string | null;
  agentName: string | null;
  actionType: string | null;
  decisionStatus: string | null;
  decision: string | null;
  outcomeVerdict: string | null;
  systemRef: string | null;
  sourceLabel: string;
  createdAt: string | null;
};

function safeFilePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]+/g, "_");
}

function evidencePackHref(decisionId: string): string {
  return `/evidence?decision_id=${encodeURIComponent(decisionId)}`;
}

function downloadJsonFile(payload: RuntimePolicyEvidencePackResponse, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function selectedDecisionIdFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("decision_id")?.trim();
  return value || null;
}

function printEvidenceReport() {
  if (typeof window !== "undefined") {
    window.print();
  }
}

function compactJson(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.length > 0 ? JSON.stringify(value, null, 2) : "[]";
  const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item != null && item !== "");
  if (entries.length === 0) return "-";
  return JSON.stringify(Object.fromEntries(entries), null, 2);
}

function summary(value: Record<string, unknown> | null | undefined, fallback: string): string {
  const candidate = value?.summary;
  return typeof candidate === "string" && candidate.trim() ? candidate : fallback;
}

function humanize(value: string | null | undefined): string {
  if (!value) return "-";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (char) => char.toUpperCase());
}

type RuntimePolicyActionLike = Pick<
  RuntimePolicyEvidencePackResponse["decision"],
  "action_type" | "tool_name" | "intended_action" | "policy_hit"
>;

const ACTION_CLASS_RULES: { label: string; terms: string[] }[] = [
  { label: "Financial action", terms: ["refund", "payment", "payout", "charge", "invoice", "ledger", "credit", "debit"] },
  { label: "Customer communication", terms: ["email", "sms", "message", "notification", "ticket", "campaign"] },
  { label: "Record/data mutation", terms: ["crm", "record", "database", "delete", "update", "create", "write", "export"] },
  { label: "Deployment/IT operation", terms: ["deploy", "rollback", "restart", "config", "infra", "server", "job", "workflow"] },
  { label: "Access/permission change", terms: ["access", "permission", "role", "credential", "token", "key", "user", "invite"] },
];

function actionClassFor(item: RuntimePolicyActionLike): string {
  const haystack = [
    item.action_type,
    item.tool_name,
    compactJson(item.intended_action),
    compactJson(item.policy_hit),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return ACTION_CLASS_RULES.find((rule) => rule.terms.some((term) => haystack.includes(term)))?.label ?? "High-stakes action";
}

function verificationCopy(pack: RuntimePolicyEvidencePackResponse): string {
  if (pack.verification_status === "pass") {
    return "Outcome verified against the system of record.";
  }
  if (pack.verification_status === "fail") {
    return "Outcome verification failed. Check the reconciliation record before trusting this action.";
  }
  if (pack.outcome_reconciliation.length === 0) {
    return "No system-of-record outcome verification is linked yet.";
  }
  return "Outcome is not verified yet.";
}

function statusLabel(value: string | null) {
  if (!value) return "not_verified";
  if (value === "not_verified") return value;
  return value.replace(/_/g, " ");
}

function verificationState(value: string | null) {
  const normalized = value ?? "not_verified";
  if (["allow", "allowed", "approved", "matched", "pass", "completed", "protected"].includes(normalized)) {
    return "pass";
  }
  if (["block", "blocked", "rejected", "mismatched", "fail", "failed"].includes(normalized)) {
    return "fail";
  }
  if (normalized === "not_verified" || !value) {
    return "not-verified";
  }
  return "warn";
}

function pillClass(value: string | null) {
  return `evidence-state-pill evidence-state-${verificationState(value)}`;
}

type EvidenceHeroState = {
  badge: string;
  copy: string;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
};

function evidenceHeroState({
  error,
  failedCount,
  loading,
  proofMissingCount,
  readyPackCount,
  totalRows,
}: {
  error: unknown;
  failedCount: number;
  loading: boolean;
  proofMissingCount: number;
  readyPackCount: number;
  totalRows: number;
}): EvidenceHeroState {
  if (error) {
    return {
      badge: "Unavailable",
      copy: "Evidence Packs cannot be trusted until the runtime decision index and outcome reconciliation index load cleanly.",
      title: "Evidence ledger unavailable",
      tone: "danger",
    };
  }

  if (loading) {
    return {
      badge: "Syncing",
      copy: "Loading protected decisions, outcome checks, and exportable Evidence Pack metadata.",
      title: "Loading evidence ledger",
      tone: "neutral",
    };
  }

  if (totalRows === 0) {
    return {
      badge: "Setup required",
      copy: "Run a protected action and connect a system-of-record reconciliation before an Evidence Pack can be exported.",
      title: "No Evidence Packs yet",
      tone: "warning",
    };
  }

  if (failedCount > 0) {
    return {
      badge: "Exception",
      copy: "At least one protected action has failed or mismatched outcome verification. Review the selected Evidence Pack before customer handoff.",
      title: "Evidence exception needs review",
      tone: "danger",
    };
  }

  if (proofMissingCount > 0) {
    return {
      badge: "Needs verification",
      copy: "Some runtime decisions are linked but still missing matched system-of-record outcome verification.",
      title: "Evidence incomplete before handoff",
      tone: "warning",
    };
  }

  return {
    badge: "Ready",
    copy:
      readyPackCount > 0
        ? "Runtime decisions, approval audit, outcome reconciliation, and evidence hash are ready to export."
        : "Evidence records are loaded. Select a linked decision to prepare an auditor-ready pack.",
    title: readyPackCount > 0 ? "Evidence ready for handoff" : "Evidence ledger ready",
    tone: "success",
  };
}

function EvidenceExportContract() {
  const items = [
    {
      label: "Runtime decision",
      title: "Policy gate recorded",
      body: "Allow, hold, block, approval, or rejection must be linked to the action.",
      status: "pass",
    },
    {
      label: "Approval audit",
      title: "Human decision trace",
      body: "Held actions need resolver, timestamp, reason, and scope hash.",
      status: "pass",
    },
    {
      label: "Outcome proof",
      title: "Real system checked",
      body: "Export-ready packs require matched outcome verification; missing proof stays not_verified.",
      status: "not_verified",
    },
    {
      label: "Evidence hash",
      title: "Tamper-evident export",
      body: "JSON export includes the hash and excluded fields used for regeneration.",
      status: "pass",
    },
  ];

  return (
    <section className="panel evidence-export-contract" aria-label="Evidence Pack export contract">
      <div className="evidence-export-contract-head">
        <div>
          <span className="eyebrow">Export contract</span>
          <h2>Evidence Pack is exportable only when control, audit, outcome, and hash are present.</h2>
          <p>Matched means customer-ready. Mismatched or not_verified stays visible but should not be used as proof of success.</p>
        </div>
      </div>
      <div className="evidence-export-contract-grid">
        {items.map((item) => (
          <article key={item.label}>
            <span className={pillClass(item.status)}>{statusLabel(item.status)}</span>
            <strong>{item.label}</strong>
            <em>{item.title}</em>
            <small>{item.body}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidencePackDetail({
  decisionId,
  pack,
  isLoading,
  error,
  isDownloading,
  onDownload,
}: {
  decisionId: string;
  pack: RuntimePolicyEvidencePackResponse | undefined;
  isLoading: boolean;
  error: Error | null;
  isDownloading: boolean;
  onDownload: (decisionId: string, pack?: RuntimePolicyEvidencePackResponse) => void;
}) {
  const outcomes = pack?.outcome_reconciliation ?? [];
  const decision = pack?.decision;
  const title = decision
    ? summary(decision.intended_action, decision.tool_name ?? decision.action_type ?? "Agent action")
    : decisionId;

  return (
    <section className="panel evidence-pack-detail" aria-label="Evidence Pack detail">
      <header className="evidence-pack-detail-header">
        <div>
          <span className="eyebrow">Evidence Pack detail</span>
          <h2>{title}</h2>
          <p>
            {decision
              ? `${decision.agent_name ?? "unknown agent"} / ${actionClassFor(decision)} / ${decisionId}`
              : "Loading policy decision, approval audit, real outcome, and evidence hash."}
          </p>
        </div>
        <div className="evidence-pack-actions">
          <button
            className="btn btn-soft evidence-print-button"
            type="button"
            disabled={!pack}
            onClick={printEvidenceReport}
          >
            <Printer aria-hidden="true" />
            Print report
          </button>
          <button
            className="btn btn-primary evidence-download-button evidence-pack-download"
            type="button"
            disabled={!pack || isDownloading}
            onClick={() => onDownload(decisionId, pack)}
          >
            <Download aria-hidden="true" />
            {isDownloading ? "Exporting..." : "Export Evidence JSON"}
          </button>
        </div>
      </header>

      {isLoading ? (
        <div className="empty-state evidence-empty-state">Loading Evidence Pack...</div>
      ) : error ? (
        <div className="evidence-pack-unavailable">
          <span className={pillClass("not_verified")}>not_verified</span>
          <strong>Evidence Pack unavailable</strong>
          <p>{error.message || "Evidence Pack could not load for this decision."}</p>
        </div>
      ) : pack ? (
        <>
          <section className="evidence-print-cover" aria-label="Evidence Pack report">
            <div>
              <span>Zroky Evidence Pack</span>
              <strong>Evidence Pack report</strong>
              <p>{title}</p>
            </div>
            <dl>
              <div>
                <dt>Decision</dt>
                <dd>{pack.decision_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{statusLabel(pack.verification_status)}</dd>
              </div>
              <div>
                <dt>Evidence hash</dt>
                <dd>{pack.evidence_hash}</dd>
              </div>
              <div>
                <dt>Generated</dt>
                <dd>{formatDateTime(pack.generated_at)}</dd>
              </div>
            </dl>
          </section>

          <section className={`evidence-pack-status evidence-pack-status-${verificationState(pack.verification_status)}`}>
            <div>
              <span className="eyebrow">Outcome verification</span>
              <strong>{humanize(pack.verification_status)}</strong>
              <p>{verificationCopy(pack)}</p>
            </div>
            <span className={pillClass(pack.verification_status)}>{statusLabel(pack.verification_status)}</span>
          </section>

          <dl className="evidence-pack-proof-grid">
            <div>
              <dt>Decision ID</dt>
              <dd>
                <code>{pack.decision_id}</code>
              </dd>
            </div>
            <div className="evidence-pack-hash-cell">
              <dt>Evidence hash</dt>
              <dd>
                <code>{pack.evidence_hash}</code>
              </dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>{formatDateTime(pack.generated_at)}</dd>
            </div>
            <div>
              <dt>Schema</dt>
              <dd>{pack.schema_version}</dd>
            </div>
            <div>
              <dt>Hash algorithm</dt>
              <dd>{pack.hash_algorithm}</dd>
            </div>
            <div>
              <dt>Hash excludes</dt>
              <dd>{pack.hash_payload_excludes.join(", ") || "nothing"}</dd>
            </div>
            <div>
              <dt>Trace evidence</dt>
              <dd>
                {pack.decision.trace_id ? (
                  <Link href="/evidence">{pack.decision.trace_id}</Link>
                ) : (
                  "-"
                )}
              </dd>
            </div>
            <div>
              <dt>Call evidence</dt>
              <dd>
                {pack.decision.call_id ? (
                  <Link href="/evidence">{pack.decision.call_id}</Link>
                ) : (
                  "-"
                )}
              </dd>
            </div>
          </dl>

          <section className="evidence-pack-section">
            <div className="evidence-pack-section-heading">
              <h3>Policy decision</h3>
              <span>{humanize(pack.decision.decision)} / {humanize(pack.decision.status)}</span>
            </div>
            <dl className="evidence-pack-proof-grid compact">
              <div>
                <dt>Status</dt>
                <dd>{pack.decision.status}</dd>
              </div>
              <div>
                <dt>Runtime decision</dt>
                <dd>{pack.decision.decision}</dd>
              </div>
              <div>
                <dt>Tool</dt>
                <dd>{pack.decision.tool_name ?? "-"}</dd>
              </div>
              <div>
                <dt>Approval scope</dt>
                <dd>{pack.decision.approval_scope_hash ?? "-"}</dd>
              </div>
              <div>
                <dt>Resolved by</dt>
                <dd>{pack.decision.resolved_by ?? "-"}</dd>
              </div>
              <div>
                <dt>Resolved</dt>
                <dd>{formatDateTime(pack.decision.resolved_at)}</dd>
              </div>
            </dl>
            <pre>{compactJson(pack.decision.intended_action)}</pre>
          </section>

          <section className="evidence-pack-section">
            <div className="evidence-pack-section-heading">
              <h3>Mandate snapshot</h3>
              <span>Mandate at decision time</span>
            </div>
            <pre>{compactJson(pack.decision.policy_snapshot)}</pre>
          </section>

          <section className="evidence-pack-section">
            <div className="evidence-pack-section-heading">
              <h3>Approval audit</h3>
              <span>{pack.audit_log.length} event{pack.audit_log.length === 1 ? "" : "s"}</span>
            </div>
            {pack.audit_log.length === 0 ? (
              <p className="evidence-pack-muted">No approval audit events captured.</p>
            ) : (
              <ol className="evidence-pack-audit-list">
                {pack.audit_log.map((event) => (
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
            )}
          </section>

          <section className="evidence-pack-section">
            <div className="evidence-pack-section-heading">
              <h3>Real outcome reconciliation</h3>
              <span>{outcomes.length} linked check{outcomes.length === 1 ? "" : "s"}</span>
            </div>
            {outcomes.length === 0 ? (
              <div className="evidence-pack-notice">
                <span className={pillClass("not_verified")}>not_verified</span>
                <strong>Missing evidence</strong>
                <p>No matched system-of-record outcome verification is linked to this decision yet.</p>
              </div>
            ) : (
              <div className="evidence-pack-outcomes">
                {outcomes.map((outcome) => (
                  <article key={outcome.id} className={`evidence-pack-outcome evidence-pack-outcome-${verificationState(outcome.verdict)}`}>
                    <div className="evidence-pack-outcome-head">
                      <div>
                        <span className="eyebrow">{outcome.connector_type}</span>
                        <strong>{outcome.system_ref ?? outcome.id}</strong>
                        <p>{outcome.reason ? humanize(outcome.reason) : "Outcome comparison"}</p>
                      </div>
                      <span className={pillClass(outcome.verdict)}>{statusLabel(outcome.verdict)}</span>
                    </div>
                    <dl className="evidence-pack-proof-grid compact">
                      <div>
                        <dt>Action</dt>
                        <dd>{humanize(outcome.action_type)}</dd>
                      </div>
                      <div>
                        <dt>Amount</dt>
                        <dd>{outcome.amount_usd == null ? "-" : `${outcome.amount_usd} ${outcome.currency ?? "USD"}`}</dd>
                      </div>
                      <div>
                        <dt>Checked</dt>
                        <dd>{formatDateTime(outcome.checked_at)}</dd>
                      </div>
                      <div>
                        <dt>Check ID</dt>
                        <dd>{outcome.id}</dd>
                      </div>
                    </dl>
                    <div className="evidence-pack-json-grid">
                      <section>
                        <h4>Agent claim</h4>
                        <pre>{compactJson(outcome.claimed)}</pre>
                      </section>
                      <section>
                        <h4>Actual system record</h4>
                        <pre>{compactJson(outcome.actual)}</pre>
                      </section>
                      <section>
                        <h4>Field comparison</h4>
                        <pre>{compactJson(outcome.comparison)}</pre>
                      </section>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="empty-state evidence-empty-state">No Evidence Pack loaded.</div>
      )}
    </section>
  );
}

function decisionRow(decision: RuntimePolicyDecisionResponse): EvidenceRow {
  return {
    key: `decision:${decision.id}`,
    decisionId: decision.id,
    agentName: decision.agent_name,
    actionType: decision.action_type ?? decision.tool_name,
    decisionStatus: decision.status,
    decision: decision.decision,
    outcomeVerdict: null,
    systemRef: null,
    sourceLabel: "Runtime decision",
    createdAt: decision.created_at,
  };
}

function outcomeRow(outcome: OutcomeReconciliationView): EvidenceRow {
  return {
    key: `outcome:${outcome.id}`,
    decisionId: outcome.runtime_policy_decision_id,
    agentName: null,
    actionType: outcome.action_type,
    decisionStatus: null,
    decision: null,
    outcomeVerdict: outcome.verdict,
    systemRef: outcome.system_ref,
    sourceLabel: outcome.connector_type,
    createdAt: outcome.checked_at ?? outcome.created_at,
  };
}

function mergeEvidenceRows(
  decisions: RuntimePolicyDecisionResponse[],
  outcomes: OutcomeReconciliationView[],
) {
  const byDecision = new Map<string, EvidenceRow>();
  const rows: EvidenceRow[] = [];

  for (const decision of decisions) {
    const row = decisionRow(decision);
    byDecision.set(decision.id, row);
    rows.push(row);
  }

  for (const outcome of outcomes) {
    const decisionId = outcome.runtime_policy_decision_id;
    if (decisionId && byDecision.has(decisionId)) {
      const existing = byDecision.get(decisionId);
      if (existing) {
        existing.outcomeVerdict = outcome.verdict;
        existing.systemRef = outcome.system_ref;
        existing.sourceLabel = outcome.connector_type;
        existing.createdAt = outcome.checked_at ?? existing.createdAt;
      }
      continue;
    }
    rows.push(outcomeRow(outcome));
  }

  return rows.sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime());
}

export default function EvidencePage() {
  const [message, setMessage] = useState("");
  const [downloadingDecisionId, setDownloadingDecisionId] = useState<string | null>(null);
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const decisionsQuery = useQuery({
    queryKey: ["runtime-policy", "evidence-index"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
  });
  const outcomesQuery = useQuery({
    queryKey: ["outcomes", "evidence-index"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ limit: 50 }, signal),
  });
  const evidencePackQuery = useQuery({
    queryKey: ["runtime-policy", "evidence-pack", selectedDecisionId],
    enabled: Boolean(selectedDecisionId),
    queryFn: ({ signal }) => {
      if (!selectedDecisionId) throw new Error("Decision id is required.");
      return getRuntimePolicyEvidencePack(selectedDecisionId, signal);
    },
  });

  const rows = useMemo(
    () => mergeEvidenceRows(decisionsQuery.data?.items ?? [], outcomesQuery.data?.items ?? []),
    [decisionsQuery.data?.items, outcomesQuery.data?.items],
  );
  const focusedRow = useMemo(
    () => (selectedDecisionId ? rows.find((row) => row.decisionId === selectedDecisionId) ?? null : null),
    [rows, selectedDecisionId],
  );
  const linkedCount = rows.filter((row) => row.decisionId).length;
  const readyPackCount = rows.filter((row) => row.decisionId && row.outcomeVerdict === "matched").length;
  const matchedCount = rows.filter((row) => row.outcomeVerdict === "matched").length;
  const failedCount = rows.filter((row) => verificationState(row.outcomeVerdict ?? row.decisionStatus ?? row.decision) === "fail").length;
  const unlinkedCount = rows.filter((row) => !row.decisionId).length;
  const proofMissingCount = rows.filter(
    (row) => !row.decisionId || row.outcomeVerdict === "not_verified" || !row.outcomeVerdict,
  ).length;
  const loading = decisionsQuery.isLoading || outcomesQuery.isLoading;
  const error = decisionsQuery.error || outcomesQuery.error;
  const evidencePack = evidencePackQuery.data;
  const evidencePackError = evidencePackQuery.error instanceof Error ? evidencePackQuery.error : null;
  const focusedStatus = evidencePack?.verification_status ?? focusedRow?.outcomeVerdict ?? focusedRow?.decisionStatus ?? focusedRow?.decision ?? null;
  const focusedDownloading = Boolean(selectedDecisionId && downloadingDecisionId === selectedDecisionId);
  const focusedActionAvailable = Boolean(focusedRow || evidencePack);
  const focusedCopy = evidencePack
    ? "Policy decision, approval audit, real outcome, and evidence hash are loaded below."
    : evidencePackQuery.isLoading
      ? "Loading the linked Evidence Pack from runtime and outcome records."
      : evidencePackError
        ? "Evidence Pack API could not load this decision. Keep this action not_verified until outcome verification is available."
        : focusedRow
          ? "Linked from a protected-agent cockpit row. Export this exact customer or auditor Evidence Pack."
          : "This decision is not present in the current evidence window. Refresh capture data or widen backend evidence history.";
  const heroState = evidenceHeroState({
    error,
    failedCount,
    loading,
    proofMissingCount,
    readyPackCount,
    totalRows: rows.length,
  });

  useEffect(() => {
    setSelectedDecisionId(selectedDecisionIdFromLocation());
  }, []);

  useEffect(() => {
    if (selectedDecisionId || loading || rows.length === 0) return;
    const firstLinkedRow = rows.find((row) => row.decisionId);
    if (firstLinkedRow?.decisionId) {
      setSelectedDecisionId(firstLinkedRow.decisionId);
    }
  }, [loading, rows, selectedDecisionId]);

  async function downloadEvidence(decisionId: string, pack?: RuntimePolicyEvidencePackResponse) {
    setMessage("");
    setDownloadingDecisionId(decisionId);
    try {
      const evidencePackToDownload = pack ?? await getRuntimePolicyEvidencePack(decisionId);
      downloadJsonFile(evidencePackToDownload, `zroky-evidence-${safeFilePart(decisionId)}.json`);
      setMessage("Evidence Pack JSON exported.");
    } catch (downloadError) {
      setMessage(downloadError instanceof Error ? downloadError.message : "Evidence Pack download failed.");
    } finally {
      setDownloadingDecisionId(null);
    }
  }

  return (
    <div className="dashboard-page evidence-page evidence-ledger-page">
      {message ? <div className="alert-strip evidence-alert-strip">{message}</div> : null}

      <section className="page-header evidence-hero" data-tone={heroState.tone}>
        <div className="evidence-hero-copy">
          <span className="eyebrow">Evidence Pack export</span>
          <h1>{heroState.title}</h1>
          <p>{heroState.copy}</p>
        </div>
        <div className="evidence-hero-rail">
          <span className="evidence-verdict-pill">{heroState.badge}</span>
          <div className="evidence-hero-proof" aria-label="Evidence export summary">
            <span>Export-ready packs</span>
            <strong>{readyPackCount}</strong>
            <small>
              {matchedCount} matched outcomes / {proofMissingCount} needs verification
            </small>
          </div>
        </div>
        <div className="actions evidence-hero-actions">
          <Link href="/approvals" className="btn btn-soft">Open approvals</Link>
          <Link href="/outcomes" className="btn btn-primary">Open outcomes</Link>
        </div>
      </section>

      <section className="settings-summary-grid evidence-summary-grid evidence-metric-grid" aria-label="Evidence summary">
        <article className="panel settings-summary-card evidence-summary-card evidence-metric-card tone-success">
          <ShieldCheck aria-hidden="true" />
          <span>Export-ready packs</span>
          <strong>{readyPackCount}</strong>
          <small>Matched decisions ready for auditor or customer handoff.</small>
        </article>
        <article className="panel settings-summary-card evidence-summary-card evidence-metric-card">
          <FileJson aria-hidden="true" />
          <span>Linked decisions</span>
          <strong>{linkedCount}</strong>
          <small>Rows with a runtime policy decision id can export a full Evidence Pack.</small>
        </article>
        <article className="panel settings-summary-card evidence-summary-card evidence-metric-card tone-warning">
          <AlertTriangle aria-hidden="true" />
          <span>Needs verification</span>
          <strong>{proofMissingCount}</strong>
          <small>Rows without matched outcome verification stay not_verified.</small>
        </article>
        <article className="panel settings-summary-card evidence-summary-card evidence-metric-card">
          <Fingerprint aria-hidden="true" />
          <span>Ledger rows</span>
          <strong>{rows.length}</strong>
          <small>{unlinkedCount} unlinked outcome{unlinkedCount === 1 ? "" : "s"} still need a decision id.</small>
        </article>
      </section>

      <EvidenceExportContract />

      <div className="evidence-workspace">
        <section className="panel evidence-ledger-panel">
          <header className="panel-header evidence-ledger-head">
            <div>
              <span className="eyebrow">Evidence Pack queue</span>
              <h3>Evidence Pack ledger</h3>
              <p>Select a protected decision, then review the exact exportable Evidence Pack on the right.</p>
            </div>
            <strong>{rows.length} rows</strong>
          </header>

          {loading ? (
            <div className="empty-state evidence-empty-state">Loading evidence...</div>
          ) : error ? (
            <div className="empty-state evidence-empty-state">Evidence could not load. Verify backend connectivity and project access.</div>
          ) : rows.length === 0 ? (
            <div className="empty-state evidence-empty-state">No evidence yet. Run a protected action, approval, or connector reconciliation first.</div>
          ) : (
            <div className="list evidence-ledger-list">
              {rows.map((row) => {
                const status = row.outcomeVerdict ?? row.decisionStatus ?? row.decision;
                const title = row.agentName ?? row.systemRef ?? row.decisionId ?? "Unlinked outcome";
                const subtitle = [row.actionType, row.sourceLabel, row.systemRef].filter(Boolean).join(" - ");
                const isDownloading = Boolean(row.decisionId) && downloadingDecisionId === row.decisionId;
                const state = verificationState(status);
                const isFocused = Boolean(row.decisionId && row.decisionId === selectedDecisionId);
                return (
                  <div
                    className="list-row evidence-ledger-row"
                    data-focused={isFocused ? "true" : undefined}
                    data-state={state}
                    id={row.decisionId ? `evidence-${safeFilePart(row.decisionId)}` : undefined}
                    aria-current={isFocused ? "true" : undefined}
                    key={row.key}
                  >
                    <div className="list-main evidence-ledger-main">
                      <div className="evidence-ledger-titleline">
                        <strong>{title}</strong>
                        <span className={pillClass(status)}>{statusLabel(status)}</span>
                      </div>
                      <span>{subtitle || "Evidence row"}</span>
                      <dl className="evidence-ledger-meta">
                        <div>
                          <dt>Decision</dt>
                          <dd>
                            <code>{row.decisionId ?? "not_linked"}</code>
                          </dd>
                        </div>
                        <div>
                          <dt>System</dt>
                          <dd>{row.systemRef ?? "pending"}</dd>
                        </div>
                        <div>
                          <dt>Checked</dt>
                          <dd>{formatDateTime(row.createdAt)}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="evidence-row-actions">
                      {row.decisionId ? (
                        <Link href={evidencePackHref(row.decisionId)} className="btn btn-soft btn-sm evidence-details-link">
                          Open Evidence Pack
                        </Link>
                      ) : null}
                      <button
                        className="btn btn-soft btn-sm evidence-download-button"
                        type="button"
                        disabled={!row.decisionId || isDownloading}
                        onClick={() => row.decisionId && void downloadEvidence(row.decisionId)}
                      >
                        <Download aria-hidden="true" />
                        {isDownloading ? "Exporting..." : row.decisionId ? "Export Evidence JSON" : "Not linked"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <aside className="evidence-proof-column" aria-label="Selected Evidence Pack workspace">
          {selectedDecisionId ? (
            <section
              className={`panel evidence-focus-panel${!loading && !focusedRow && !evidencePack ? " is-missing" : ""}`}
              aria-label="Focused Evidence Pack"
            >
              <div className="evidence-focus-copy">
                <span className="eyebrow">Selected Evidence Pack</span>
                <strong>{selectedDecisionId}</strong>
                <p>{focusedCopy}</p>
              </div>
              <dl className="evidence-focus-meta">
                <div>
                  <dt>Status</dt>
                  <dd>
                    <span className={pillClass(focusedStatus)}>{statusLabel(focusedStatus)}</span>
                  </dd>
                </div>
                <div>
                  <dt>System</dt>
                  <dd>{focusedRow?.systemRef ?? "pending"}</dd>
                </div>
                <div>
                  <dt>Checked</dt>
                  <dd>{formatDateTime(focusedRow?.createdAt ?? null)}</dd>
                </div>
              </dl>
              <button
                className="btn btn-primary evidence-download-button evidence-focus-download"
                type="button"
                disabled={!focusedActionAvailable || focusedDownloading}
                onClick={() => selectedDecisionId && focusedActionAvailable && void downloadEvidence(selectedDecisionId, evidencePack)}
              >
                <Download aria-hidden="true" />
                {focusedDownloading ? "Exporting..." : focusedActionAvailable ? "Export Evidence JSON" : "Not available"}
              </button>
            </section>
          ) : (
            <section className="panel evidence-focus-panel is-missing" aria-label="Focused Evidence Pack">
              <div className="evidence-focus-copy">
                <span className="eyebrow">Selected Evidence Pack</span>
                <strong>No pack selected</strong>
                <p>Select a linked runtime decision to load policy decision, approval audit, real outcome, and evidence hash.</p>
              </div>
            </section>
          )}

          {selectedDecisionId ? (
            <EvidencePackDetail
              decisionId={selectedDecisionId}
              pack={evidencePack}
              isLoading={evidencePackQuery.isLoading}
              error={evidencePackError}
              isDownloading={focusedDownloading}
              onDownload={(decisionId, pack) => void downloadEvidence(decisionId, pack)}
            />
          ) : null}
        </aside>
      </div>
    </div>
  );
}
