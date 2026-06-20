"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Clock3,
  Download,
  FileText,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { formatDateTime } from "@/lib/format";
import {
  useApproveRuntimePolicyDecision,
  useRejectRuntimePolicyDecision,
  useRuntimePolicyEvidencePack,
  useRuntimePolicyApprovals,
  useSetRuntimePolicyKillSwitch,
} from "@/lib/hooks";
import type {
  RuntimePolicyDecisionResponse,
  RuntimePolicyDecisionStatus,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";

type Filter = RuntimePolicyDecisionStatus | "all";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "pending_approval", label: "Pending" },
  { id: "blocked", label: "Blocked" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "all", label: "All" },
];

function compactJson(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.length > 0 ? JSON.stringify(value, null, 2) : "[]";
  const entries = Object.entries(value as Record<string, unknown>).filter(
    ([, item]) => item != null && item !== "",
  );
  if (entries.length === 0) return "-";
  return JSON.stringify(Object.fromEntries(entries), null, 2);
}

function field(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function summary(value: Record<string, unknown>, fallback: string): string {
  const candidate = value.summary;
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

function queueTone(status: string): "danger" | "warning" | "success" | "neutral" {
  if (["blocked", "rejected", "fail", "mismatched"].includes(status)) return "danger";
  if (["pending_approval", "not_verified", "warn"].includes(status)) return "warning";
  if (["approved", "allowed", "pass", "matched", "verified"].includes(status)) return "success";
  return "neutral";
}

type RuntimePolicyActionLike = Pick<
  RuntimePolicyDecisionResponse,
  "action_type" | "tool_name" | "intended_action" | "policy_hit"
>;

const ACTION_CLASS_RULES: { label: string; terms: string[] }[] = [
  {
    label: "Financial action",
    terms: ["refund", "payment", "payout", "charge", "invoice", "ledger", "credit", "debit"],
  },
  {
    label: "Customer communication",
    terms: ["email", "sms", "message", "notification", "ticket", "campaign"],
  },
  {
    label: "Record/data mutation",
    terms: ["crm", "record", "database", "delete", "update", "create", "write", "export"],
  },
  {
    label: "Deployment/IT operation",
    terms: ["deploy", "rollback", "restart", "config", "infra", "server", "job", "workflow"],
  },
  {
    label: "Access/permission change",
    terms: ["access", "permission", "role", "credential", "token", "key", "user", "invite"],
  },
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
    return "Outcome proof failed. Check the reconciliation record before trusting this action.";
  }
  if (pack.outcome_reconciliation.length === 0) {
    return "No system-of-record outcome proof is linked yet.";
  }
  return "Outcome is not verified yet.";
}

function downloadEvidencePack(pack: RuntimePolicyEvidencePackResponse) {
  const blob = new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `zroky-evidence-${pack.decision_id.replace(/[^a-zA-Z0-9_.-]+/g, "_")}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function EvidencePackModal({
  decisionId,
  pack,
  isLoading,
  error,
  onClose,
}: {
  decisionId: string;
  pack: RuntimePolicyEvidencePackResponse | undefined;
  isLoading: boolean;
  error: Error | null;
  onClose: () => void;
}) {
  const outcomes = pack?.outcome_reconciliation ?? [];
  const decision = pack?.decision;

  return (
    <>
      <button
        type="button"
        className="alert-drawer-backdrop"
        aria-label="Close evidence pack"
        onClick={onClose}
      />

      <aside className="alert-drawer evidence-pack-drawer" role="dialog" aria-modal="true" aria-label="Evidence Pack">
        <header className="alert-drawer-header evidence-pack-header">
          <div>
            <span className="module-eyebrow">Evidence Pack</span>
            <h3>{decision ? summary(decision.intended_action, decision.tool_name ?? decision.action_type ?? "Agent action") : decisionId}</h3>
            <p>{decision ? `${decision.agent_name ?? "unknown agent"} / ${actionClassFor(decision)}` : "Loading proof bundle"}</p>
          </div>
          <button type="button" className="ai-close-btn" onClick={onClose} aria-label="Close evidence pack">
            <X aria-hidden="true" />
          </button>
        </header>

        <div className="alert-drawer-content evidence-pack-content">
          {isLoading ? (
            <div className="empty">Loading evidence pack...</div>
          ) : error ? (
            <div className="empty error">{error.message}</div>
          ) : pack ? (
            <>
              <section className={`evidence-pack-status tone-${queueTone(pack.verification_status)}`}>
                <div>
                  <span className="eyebrow">Verification</span>
                  <strong>{humanize(pack.verification_status)}</strong>
                  <p>{verificationCopy(pack)}</p>
                </div>
                <StatusPill value={pack.verification_status} />
              </section>

              <dl className="evidence-pack-meta">
                <div>
                  <dt>Decision ID</dt>
                  <dd>{pack.decision_id}</dd>
                </div>
                <div>
                  <dt>Action class</dt>
                  <dd>{actionClassFor(pack.decision)}</dd>
                </div>
                <div>
                  <dt>Agent</dt>
                  <dd>{pack.decision.agent_name ?? "-"}</dd>
                </div>
                <div>
                  <dt>Action</dt>
                  <dd>{humanize(pack.decision.action_type)}</dd>
                </div>
                <div>
                  <dt>Trace</dt>
                  <dd>
                    {pack.decision.trace_id ? (
                      <Link href={`/trace/${encodeURIComponent(pack.decision.trace_id)}`}>{pack.decision.trace_id}</Link>
                    ) : (
                      "-"
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Call</dt>
                  <dd>
                    {pack.decision.call_id ? (
                      <Link href={`/calls/${encodeURIComponent(pack.decision.call_id)}`}>{pack.decision.call_id}</Link>
                    ) : (
                      "-"
                    )}
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
              </dl>

              <section className="evidence-pack-hash" aria-label="Evidence hash">
                <div>
                  <span className="eyebrow">Evidence hash</span>
                  <code>{pack.evidence_hash}</code>
                  <p>
                    {pack.hash_algorithm}; excludes {pack.hash_payload_excludes.join(", ") || "nothing"}
                  </p>
                </div>
                <button className="btn btn-primary btn-sm" type="button" onClick={() => downloadEvidencePack(pack)}>
                  <Download size={15} />
                  Download JSON
                </button>
              </section>

              <section className="evidence-pack-section">
                <h4>Decision</h4>
                <dl className="evidence-pack-meta compact">
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
                </dl>
                <pre>{compactJson(pack.decision.intended_action)}</pre>
              </section>

              <section className="evidence-pack-section">
                <h4>Policy snapshot</h4>
                <pre>{compactJson(pack.decision.policy_snapshot)}</pre>
              </section>

              <section className="evidence-pack-section">
                <h4>Approval audit</h4>
                {pack.audit_log.length === 0 ? (
                  <p className="evidence-pack-muted">No approval audit events captured.</p>
                ) : (
                  <ol className="evidence-pack-audit-list">
                    {pack.audit_log.map((event) => (
                      <li key={event.id}>
                        <div>
                          <strong>{event.event_type}</strong>
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
                <h4>Outcome reconciliation</h4>
                {outcomes.length === 0 ? (
                  <div className="evidence-pack-notice">
                    <strong>Missing evidence</strong>
                    <p>No matched system-of-record outcome is linked to this decision yet.</p>
                  </div>
                ) : (
                  <div className="evidence-pack-outcomes">
                    {outcomes.map((outcome) => (
                      <article key={outcome.id} className={`evidence-pack-outcome tone-${queueTone(outcome.verdict)}`}>
                        <div>
                          <span className="eyebrow">{outcome.connector_type}</span>
                          <strong>{outcome.system_ref ?? outcome.id}</strong>
                          <p>{outcome.reason ? humanize(outcome.reason) : "Outcome comparison"}</p>
                        </div>
                        <StatusPill value={outcome.verdict} />
                        <dl className="evidence-pack-meta compact">
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
                            <h5>Claimed</h5>
                            <pre>{compactJson(outcome.claimed)}</pre>
                          </section>
                          <section>
                            <h5>Actual</h5>
                            <pre>{compactJson(outcome.actual)}</pre>
                          </section>
                          <section>
                            <h5>Comparison</h5>
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
            <div className="empty">No evidence pack loaded.</div>
          )}
        </div>
      </aside>
    </>
  );
}

function DecisionCard({
  item,
  busy,
  onViewEvidence,
  onApprove,
  onReject,
}: {
  item: RuntimePolicyDecisionResponse;
  busy: boolean;
  onViewEvidence: (id: string) => void;
  onApprove: (id: string, reason: string) => void;
  onReject: (id: string, reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const canResolve = item.status === "pending_approval";
  const disabled = busy || !canResolve || reason.trim().length < 3;

  return (
    <article className={`panel approval-card tone-${queueTone(item.status)}`}>
      <div className="approval-card-header">
        <div>
          <span className="eyebrow">Runtime policy</span>
          <h3>{summary(item.intended_action, item.tool_name ?? item.action_type ?? "Agent action")}</h3>
          <p>
            {item.agent_name ?? "unknown agent"} · {item.action_type ?? "unknown action"}
          </p>
        </div>
        <div className="approval-card-badges">
          <StatusPill value={item.status} />
          <span className="approval-action-class">{actionClassFor(item)}</span>
          <button className="btn btn-soft btn-sm" type="button" onClick={() => onViewEvidence(item.id)}>
            <FileText size={15} />
            Evidence Pack
          </button>
        </div>
      </div>

      <dl className="approval-meta-grid">
        <div>
          <dt>Agent</dt>
          <dd>{item.agent_name ?? field(item.trace_context.agent_name)}</dd>
        </div>
        <div>
          <dt>Trace</dt>
          <dd>
            {item.trace_id ? (
              <Link href={`/trace/${encodeURIComponent(item.trace_id)}`}>{item.trace_id}</Link>
            ) : (
              "-"
            )}
          </dd>
        </div>
        <div>
          <dt>Policy hit</dt>
          <dd>{field(item.policy_hit.policy)}</dd>
        </div>
        <div>
          <dt>Business impact</dt>
          <dd>{field(item.business_impact.risk_category ?? item.business_impact.summary)}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(item.created_at)}</dd>
        </div>
        <div>
          <dt>Expires</dt>
          <dd>{item.expires_at ? formatDateTime(item.expires_at) : "-"}</dd>
        </div>
        <div>
          <dt>Consumed</dt>
          <dd>{item.consumed_at ? formatDateTime(item.consumed_at) : "-"}</dd>
        </div>
      </dl>

      <div className="approval-evidence-grid">
        <section>
          <h4>Risk reason</h4>
          {item.reasons.length > 0 ? (
            <ul>
              {item.reasons.map((reasonItem) => (
                <li key={reasonItem}>{reasonItem}</li>
              ))}
            </ul>
          ) : (
            <p>-</p>
          )}
        </section>
        <section>
          <h4>Intended action</h4>
          <pre>{compactJson(item.intended_action)}</pre>
        </section>
        <section>
          <h4>Trace context</h4>
          <pre>{compactJson(item.trace_context)}</pre>
        </section>
        <section>
          <h4>Policy hit</h4>
          <pre>{compactJson(item.policy_hit)}</pre>
        </section>
        <section>
          <h4>Business impact</h4>
          <pre>{compactJson(item.business_impact)}</pre>
        </section>
        <section>
          <h4>Masked request</h4>
          <pre>{compactJson(item.request)}</pre>
        </section>
      </div>

      {item.resolution_reason ? (
        <div className="approval-resolution">
          <strong>{item.resolved_by ?? "resolved"}</strong>
          <span>{item.resolved_at ? formatDateTime(item.resolved_at) : ""}</span>
          <p>{item.resolution_reason}</p>
        </div>
      ) : null}

      <section className="approval-audit">
        <h4>Audit log</h4>
        {item.audit_log.length === 0 ? (
          <p>-</p>
        ) : (
          <ol>
            {item.audit_log.map((event) => (
              <li key={event.id}>
                <div>
                  <strong>{event.event_type}</strong>
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

      {canResolve ? (
        <div className="approval-actions">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason"
            aria-label="Decision reason"
          />
          <button
            className="btn btn-primary"
            type="button"
            disabled={disabled}
            onClick={() => onApprove(item.id, reason)}
          >
            <Check size={16} />
            Approve
          </button>
          <button
            className="btn btn-secondary"
            type="button"
            disabled={disabled}
            onClick={() => onReject(item.id, reason)}
          >
            <X size={16} />
            Reject
          </button>
        </div>
      ) : null}
    </article>
  );
}

export default function RuntimeApprovalsPage() {
  const [filter, setFilter] = useState<Filter>("pending_approval");
  const [message, setMessage] = useState<string | null>(null);
  const [evidenceDecisionId, setEvidenceDecisionId] = useState<string | null>(null);
  const approvalsQuery = useRuntimePolicyApprovals(filter);
  const evidencePackQuery = useRuntimePolicyEvidencePack(evidenceDecisionId);
  const approveMutation = useApproveRuntimePolicyDecision();
  const rejectMutation = useRejectRuntimePolicyDecision();
  const killSwitchMutation = useSetRuntimePolicyKillSwitch();

  const items = useMemo(() => approvalsQuery.data?.items ?? [], [approvalsQuery.data?.items]);
  const pendingCount = useMemo(
    () => items.filter((item) => item.status === "pending_approval").length,
    [items],
  );
  const busy = approveMutation.isPending || rejectMutation.isPending;

  const resolve = async (kind: "approve" | "reject", id: string, reason: string) => {
    setMessage(null);
    try {
      if (kind === "approve") {
        await approveMutation.mutateAsync({ decisionId: id, reason });
        setMessage("Approval recorded.");
      } else {
        await rejectMutation.mutateAsync({ decisionId: id, reason });
        setMessage("Rejection recorded.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Decision failed.");
    }
  };

  return (
    <div className="dashboard-page approvals-page">
      <section className="page-header">
        <div>
          <span className="eyebrow">Runtime gate</span>
          <h1>Approvals</h1>
          <p>Paused agent actions, policy hits, and owner/admin decisions.</p>
        </div>
        <div className="page-actions">
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => approvalsQuery.refetch()}
            disabled={approvalsQuery.isFetching}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            className="btn btn-secondary"
            type="button"
            disabled={killSwitchMutation.isPending}
            onClick={async () => {
              setMessage(null);
              try {
                await killSwitchMutation.mutateAsync(true);
                setMessage("Kill switch enabled.");
              } catch (error) {
                setMessage(error instanceof Error ? error.message : "Kill switch update failed.");
              }
            }}
          >
            <ShieldAlert size={16} />
            Kill switch
          </button>
        </div>
      </section>

      <section className="metric-grid compact">
        <article className="metric-card tone-warning">
          <Clock3 size={18} />
          <span>Pending</span>
          <strong>{pendingCount}</strong>
        </article>
        <article className="metric-card tone-danger">
          <AlertTriangle size={18} />
          <span>Blocked</span>
          <strong>{items.filter((item) => item.status === "blocked").length}</strong>
        </article>
        <article className="metric-card tone-neutral">
          <LockKeyhole size={18} />
          <span>Visible traces</span>
          <strong>{items.filter((item) => item.trace_id).length}</strong>
        </article>
      </section>

      <section className="filter-bar" aria-label="Approval filters">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            className={`filter-chip ${filter === item.id ? "active" : ""}`}
            type="button"
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </section>

      {message ? <div className="notice">{message}</div> : null}

      {approvalsQuery.isLoading ? (
        <div className="empty">Loading runtime approvals...</div>
      ) : approvalsQuery.isError ? (
        <div className="empty error">{approvalsQuery.error.message}</div>
      ) : items.length === 0 ? (
        <div className="empty">No runtime policy approvals in this view.</div>
      ) : (
        <section className="approval-list">
          {items.map((item) => (
            <DecisionCard
              key={item.id}
              item={item}
              busy={busy}
              onViewEvidence={setEvidenceDecisionId}
              onApprove={(id, reason) => resolve("approve", id, reason)}
              onReject={(id, reason) => resolve("reject", id, reason)}
            />
          ))}
        </section>
      )}

      {evidenceDecisionId ? (
        <EvidencePackModal
          decisionId={evidenceDecisionId}
          pack={evidencePackQuery.data}
          isLoading={evidencePackQuery.isLoading}
          error={evidencePackQuery.error instanceof Error ? evidencePackQuery.error : null}
          onClose={() => setEvidenceDecisionId(null)}
        />
      ) : null}
    </div>
  );
}
