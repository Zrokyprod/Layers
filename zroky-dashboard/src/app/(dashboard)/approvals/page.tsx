"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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
type VerdictTone = "danger" | "warning" | "success" | "neutral";

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

function statusVerb(status: string): string {
  if (status === "pending_approval") return "Hold";
  if (status === "blocked") return "Blocked";
  if (status === "approved") return "Approved";
  if (status === "rejected") return "Rejected";
  if (status === "allowed") return "Allowed";
  return humanize(status);
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

function titleFor(item: RuntimePolicyDecisionResponse): string {
  return summary(item.intended_action, item.tool_name ?? item.action_type ?? "Agent action");
}

function riskSummary(item: RuntimePolicyDecisionResponse): string {
  return item.reasons[0] ?? field(item.policy_hit.risk_reasons) ?? field(item.policy_hit.policy);
}

function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function moneyValue(item: RuntimePolicyDecisionResponse): string {
  const amount =
    numberFrom(item.business_impact.amount_usd) ??
    numberFrom(item.business_impact.estimated_value_usd) ??
    numberFrom(item.request.amount_usd) ??
    numberFrom(item.intended_action.amount_usd);
  if (amount == null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);
}

function timeUntil(value: string | null): string {
  if (!value) return "-";
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "-";
  const diff = time - Date.now();
  if (diff <= 0) return "Expired";
  const minutes = Math.ceil(diff / 60_000);
  if (minutes < 60) return `${minutes}m left`;
  const hours = Math.ceil(minutes / 60);
  if (hours < 48) return `${hours}h left`;
  return `${Math.ceil(hours / 24)}d left`;
}

function timeSince(value: string | null): string {
  if (!value) return "-";
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "-";
  const diff = Math.max(0, Date.now() - time);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h old`;
  return `${Math.floor(hours / 24)}d old`;
}

function priorityFor(item: RuntimePolicyDecisionResponse): { score: number; label: string; detail: string } {
  const actionClass = actionClassFor(item);
  const isFinancial = actionClass === "Financial action";
  const expired = item.expires_at ? new Date(item.expires_at).getTime() <= Date.now() : false;
  if (item.status === "pending_approval" && (isFinancial || expired)) {
    return { score: 0, label: "P0", detail: expired ? "expired hold" : "money-action hold" };
  }
  if (item.status === "blocked" || item.status === "rejected") {
    return { score: 1, label: "P0", detail: "damage stopped" };
  }
  if (item.status === "pending_approval") {
    return { score: 2, label: "P1", detail: "needs decision" };
  }
  if (item.status === "approved") {
    return { score: 3, label: "P2", detail: "approved action" };
  }
  return { score: 4, label: "P3", detail: "audit only" };
}

function proofStatus(pack: RuntimePolicyEvidencePackResponse | undefined, isLoading: boolean, error: Error | null) {
  if (isLoading) return { label: "Loading proof", detail: "Evidence Pack is being loaded.", tone: "neutral" as const };
  if (error) return { label: "Proof unavailable", detail: error.message, tone: "danger" as const };
  if (!pack) return { label: "Not verified", detail: "Open the Evidence Pack to load outcome proof.", tone: "warning" as const };
  if (pack.verification_status === "pass") {
    return { label: "Outcome verified", detail: "Matched system-of-record outcome is linked.", tone: "success" as const };
  }
  if (pack.verification_status === "fail") {
    return { label: "Outcome failed", detail: "System-of-record reconciliation failed.", tone: "danger" as const };
  }
  if (pack.outcome_reconciliation.length === 0) {
    return { label: "Not verified", detail: "No system-of-record outcome proof is linked.", tone: "warning" as const };
  }
  return { label: humanize(pack.verification_status), detail: "Outcome verification needs review.", tone: "warning" as const };
}

function verificationCopy(pack: RuntimePolicyEvidencePackResponse): string {
  if (pack.verification_status === "pass") {
    return "Outcome verified against the system of record.";
  }
  if (pack.verification_status === "fail") {
    return "Outcome verification failed. Check the reconciliation record before trusting this action.";
  }
  if (pack.outcome_reconciliation.length === 0) {
    return "No system-of-record outcome proof is linked yet.";
  }
  return "Outcome is not verified yet.";
}

function approvalsVerdict({
  items,
  pendingCount,
  blockedCount,
  killSwitchArmed,
  isLoading,
  isError,
}: {
  items: RuntimePolicyDecisionResponse[];
  pendingCount: number;
  blockedCount: number;
  killSwitchArmed: boolean;
  isLoading: boolean;
  isError: boolean;
}): { title: string; description: string; pill: string; tone: VerdictTone } {
  if (killSwitchArmed) {
    return {
      title: "Kill switch confirmation armed",
      description:
        "No global hold is enabled until you confirm. Use it only when proof or mandate boundaries look unsafe.",
      pill: "confirmation armed",
      tone: "danger",
    };
  }
  if (isError) {
    return {
      title: "Approval state unavailable",
      description: "The runtime gate could not refresh this queue. Keep high-stakes decisions conservative until it recovers.",
      pill: "refresh failed",
      tone: "danger",
    };
  }
  if (isLoading) {
    return {
      title: "Loading runtime gate",
      description: "Fetching held actions, mandate hits, approval audit, and linked outcome proof.",
      pill: "loading",
      tone: "neutral",
    };
  }
  if (pendingCount > 0) {
    const heldCopy =
      pendingCount === 1
        ? "Zroky is holding one high-stakes action"
        : `Zroky is holding ${pendingCount} high-stakes actions`;
    return {
      title: "Risky actions held before commit",
      description: `${heldCopy} until approval, mandate proof, and outcome evidence are reviewed.`,
      pill: `${pendingCount} held`,
      tone: "warning",
    };
  }
  if (blockedCount > 0) {
    const blockedCopy =
      blockedCount === 1
        ? "One blocked or rejected decision is"
        : `${blockedCount} blocked or rejected decisions are`;
    return {
      title: "Unsafe action stopped",
      description: `${blockedCopy} preserved with policy, approval audit, and Evidence Pack proof.`,
      pill: `${blockedCount} stopped`,
      tone: "danger",
    };
  }
  if (items.length === 0) {
    return {
      title: "Approval gate clear",
      description: "The runtime gate is ready. High-stakes agent actions will land here before commit.",
      pill: "clear",
      tone: "neutral",
    };
  }
  return {
    title: "Actions controlled and proved",
    description: "Resolved actions are linked to mandate hits, approval reasons, outcome checks, and Evidence Packs.",
    pill: `${items.length} audited`,
    tone: "success",
  };
}

function ApprovalControlContract() {
  const states: {
    status: RuntimePolicyDecisionStatus;
    title: string;
    body: string;
    tone: VerdictTone;
  }[] = [
    {
      status: "pending_approval",
      title: "Hold before commit",
      body: "High-stakes tool calls wait here until mandate, amount, arguments, and risk are reviewed.",
      tone: "warning",
    },
    {
      status: "approved",
      title: "Release with audit",
      body: "Approval stores resolver, reason, timestamp, and scope; it does not replace real outcome proof.",
      tone: "success",
    },
    {
      status: "rejected",
      title: "Keep stopped",
      body: "Unsafe, unclear, or out-of-mandate actions stay stopped and remain visible for the Evidence Pack.",
      tone: "danger",
    },
    {
      status: "expired",
      title: "Fail closed",
      body: "Stale approvals are not auto-released; the agent must retry through the policy gate.",
      tone: "neutral",
    },
  ];

  return (
    <section className="approval-control-contract" aria-label="Approval control contract">
      <div className="approval-control-contract-head">
        <span className="eyebrow">Approval contract</span>
        <h2>Human approval releases the action; outcome verification proves what happened.</h2>
        <p>
          This page controls the before-action decision. The Evidence Pack becomes customer-ready only after matched
          system-of-record proof is linked.
        </p>
      </div>
      <div className="approval-control-state-grid">
        {states.map((state) => (
          <article key={state.status} data-tone={state.tone}>
            <StatusPill value={state.status} />
            <strong>{state.title}</strong>
            <span>{state.body}</span>
          </article>
        ))}
      </div>
    </section>
  );
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

function ApprovalQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: RuntimePolicyDecisionResponse[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="approval-queue-panel" aria-label="Held action queue">
      <div className="approval-panel-head">
        <div>
          <span className="eyebrow">Held action queue</span>
          <strong>{items.length} action{items.length === 1 ? "" : "s"} under control</strong>
        </div>
        <span className="approval-live-dot">live</span>
      </div>
      <div className="approval-queue-list">
        {items.map((item) => {
          const priority = priorityFor(item);
          const selected = item.id === selectedId;
          return (
            <button
              key={item.id}
              type="button"
              className={`approval-queue-row tone-${queueTone(item.status)}${selected ? " selected" : ""}`}
              onClick={() => onSelect(item.id)}
            >
              <span className="approval-priority">{priority.label}</span>
              <span className="approval-queue-main">
                <strong>{titleFor(item)}</strong>
                <small>
                  {item.agent_name ?? "unknown agent"} / {actionClassFor(item)}
                </small>
                <em>{riskSummary(item)}</em>
              </span>
              <span className="approval-queue-side">
                <StatusPill value={item.status} />
                <small>{priority.detail}</small>
                <small>{timeUntil(item.expires_at)}</small>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function AuditTrail({ item }: { item: RuntimePolicyDecisionResponse }) {
  return (
    <section className="approval-audit approval-inspector-audit">
      <h4>Approval audit</h4>
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
  );
}

function ApprovalInspector({
  item,
  pack,
  packLoading,
  packError,
  reason,
  setReason,
  busy,
  onViewEvidence,
  onApprove,
  onReject,
}: {
  item: RuntimePolicyDecisionResponse | null;
  pack: RuntimePolicyEvidencePackResponse | undefined;
  packLoading: boolean;
  packError: Error | null;
  reason: string;
  setReason: (value: string) => void;
  busy: boolean;
  onViewEvidence: (id: string) => void;
  onApprove: (id: string, reason: string) => void;
  onReject: (id: string, reason: string) => void;
}) {
  if (!item) {
    return (
      <section className="approval-inspector-panel empty-state">
        <ShieldAlert size={22} aria-hidden="true" />
        <h2>Select a held action.</h2>
        <p>High-stakes agent actions appear here before commit after the SDK or gateway calls the policy gate.</p>
      </section>
    );
  }

  const canResolve = item.status === "pending_approval";
  const disabled = busy || !canResolve || reason.trim().length < 3;
  const proof = proofStatus(pack, packLoading, packError);
  const requiredApprovalCount = Math.max(1, item.required_approval_count ?? 1);
  const approvalCount = Math.max(0, item.approval_count ?? 0);
  const remainingApprovals = Math.max(0, requiredApprovalCount - approvalCount);
  const approvalLabel =
    requiredApprovalCount > 1
      ? `${approvalCount}/${requiredApprovalCount} approvals recorded`
      : approvalCount > 0
        ? "Approved"
        : "Single approval required";
  const approveButtonLabel =
    requiredApprovalCount > 1 && remainingApprovals > 1 ? "Record Approval" : "Approve";

  return (
    <section className="approval-inspector-panel" aria-label="Selected action control">
      <div className="approval-inspector-header">
        <div>
          <span className="eyebrow">Risky action control</span>
          <h2>{titleFor(item)}</h2>
          <p>
            {item.agent_name ?? "unknown agent"} / {statusVerb(item.status)} / {actionClassFor(item)}
          </p>
        </div>
        <div className="approval-inspector-actions">
          <StatusPill value={item.status} />
          <button className="btn btn-soft btn-sm" type="button" onClick={() => onViewEvidence(item.id)}>
            <FileText size={15} />
            Open Evidence Pack
          </button>
        </div>
      </div>

      <section className={`approval-proof-strip tone-${proof.tone}`}>
        <div>
          <span className="eyebrow">After-action proof</span>
          <strong>{proof.label}</strong>
          <p>{proof.detail}</p>
        </div>
        {pack ? <StatusPill value={pack.verification_status} /> : <StatusPill value="not_verified" />}
      </section>

      <dl className="approval-inspector-metrics">
        <div>
          <dt>Impact</dt>
          <dd>{moneyValue(item)}</dd>
        </div>
        <div>
          <dt>Age</dt>
          <dd>{timeSince(item.created_at)}</dd>
        </div>
        <div>
          <dt>Expires</dt>
          <dd>{timeUntil(item.expires_at)}</dd>
        </div>
        <div>
          <dt>Approval progress</dt>
          <dd>{approvalLabel}</dd>
        </div>
        <div>
          <dt>Trace evidence</dt>
          <dd>
            {item.trace_id ? <Link href="/evidence">{item.trace_id}</Link> : "-"}
          </dd>
        </div>
        <div>
          <dt>Call evidence</dt>
          <dd>
            {item.call_id ? <Link href="/evidence">{item.call_id}</Link> : "-"}
          </dd>
        </div>
        <div>
          <dt>Decision ID</dt>
          <dd>{item.id}</dd>
        </div>
      </dl>

      <div className="approval-inspector-grid">
        <section>
          <h3>Policy mandate hit</h3>
          <ul>
            {item.reasons.length > 0 ? item.reasons.map((reasonItem) => <li key={reasonItem}>{reasonItem}</li>) : <li>-</li>}
          </ul>
          <pre>{compactJson(item.policy_hit)}</pre>
        </section>
        <section>
          <h3>Intended action</h3>
          <pre>{compactJson(item.intended_action)}</pre>
        </section>
        <section>
          <h3>Business impact</h3>
          <pre>{compactJson(item.business_impact)}</pre>
        </section>
        <section>
          <h3>Masked request</h3>
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

      <AuditTrail item={item} />

      <section className="approval-decision-console">
        <div>
          <span className="eyebrow">Human decision</span>
          <strong>
            {canResolve
              ? requiredApprovalCount > 1
                ? `${remainingApprovals} more distinct approval${remainingApprovals === 1 ? "" : "s"} required.`
                : "Approve or reject this held action."
              : "Decision already resolved."}
          </strong>
          <p>This reason is written into the approval audit trail and Evidence Pack.</p>
        </div>
        <div className="approval-actions">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason for approving or rejecting"
            aria-label="Decision reason"
            disabled={!canResolve}
          />
          <button
            className="btn btn-primary"
            type="button"
            disabled={disabled}
            onClick={() => onApprove(item.id, reason)}
          >
            <Check size={16} />
            {approveButtonLabel}
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
      </section>
    </section>
  );
}

function KillSwitchPanel({
  armed,
  setArmed,
  isPending,
  onConfirm,
}: {
  armed: boolean;
  setArmed: (value: boolean) => void;
  isPending: boolean;
  onConfirm: () => void;
}) {
  return (
    <section className={`approval-kill-panel${armed ? " armed" : ""}`} aria-label="Runtime kill switch">
      <div>
        <span className="eyebrow">Runtime kill switch</span>
        <strong>{armed ? "Confirm global runtime hold" : "Fail closed when proof is unsafe"}</strong>
        <p>
          Pause high-stakes runtime approvals when evidence, connector, or mandate boundaries are unreliable.
        </p>
      </div>
      {armed ? (
        <div className="approval-kill-actions">
          <button className="btn btn-secondary" type="button" onClick={() => setArmed(false)} disabled={isPending}>
            Cancel
          </button>
          <button className="btn btn-primary" type="button" onClick={onConfirm} disabled={isPending}>
            <ShieldAlert size={16} />
            Confirm kill switch
          </button>
        </div>
      ) : (
        <button className="btn btn-secondary" type="button" onClick={() => setArmed(true)} disabled={isPending}>
          <ShieldAlert size={16} />
          Arm kill switch confirmation
        </button>
      )}
    </section>
  );
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
                  <span className="eyebrow">Outcome verification</span>
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
                  Export Evidence JSON
                </button>
              </section>

              <section className="evidence-pack-section">
                <h4>Policy decision</h4>
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
                <h4>Mandate snapshot</h4>
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
                <h4>Real outcome reconciliation</h4>
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

export default function RuntimeApprovalsPage() {
  const [filter, setFilter] = useState<Filter>("pending_approval");
  const [message, setMessage] = useState<string | null>(null);
  const [evidenceDecisionId, setEvidenceDecisionId] = useState<string | null>(null);
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [killSwitchArmed, setKillSwitchArmed] = useState(false);
  const approvalsQuery = useRuntimePolicyApprovals(filter);
  const evidencePackQuery = useRuntimePolicyEvidencePack(evidenceDecisionId);
  const approveMutation = useApproveRuntimePolicyDecision();
  const rejectMutation = useRejectRuntimePolicyDecision();
  const killSwitchMutation = useSetRuntimePolicyKillSwitch();

  const items = useMemo(() => approvalsQuery.data?.items ?? [], [approvalsQuery.data?.items]);
  const sortedItems = useMemo(
    () =>
      [...items].sort((a, b) => {
        const priorityDiff = priorityFor(a).score - priorityFor(b).score;
        if (priorityDiff !== 0) return priorityDiff;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }),
    [items],
  );
  const selectedItem = useMemo(
    () => sortedItems.find((item) => item.id === selectedDecisionId) ?? sortedItems[0] ?? null,
    [selectedDecisionId, sortedItems],
  );
  const selectedEvidenceQuery = useRuntimePolicyEvidencePack(selectedItem?.id ?? null);
  const pendingCount = useMemo(
    () => items.filter((item) => item.status === "pending_approval").length,
    [items],
  );
  const blockedCount = useMemo(
    () => items.filter((item) => item.status === "blocked" || item.status === "rejected").length,
    [items],
  );
  const evidenceLinkedCount = useMemo(() => items.filter((item) => item.trace_id || item.call_id).length, [items]);
  const financialCount = useMemo(
    () => items.filter((item) => actionClassFor(item) === "Financial action").length,
    [items],
  );
  const busy = approveMutation.isPending || rejectMutation.isPending;
  const hero = approvalsVerdict({
    items,
    pendingCount,
    blockedCount,
    killSwitchArmed,
    isLoading: approvalsQuery.isLoading,
    isError: approvalsQuery.isError,
  });

  useEffect(() => {
    if (sortedItems.length === 0) {
      setSelectedDecisionId(null);
      return;
    }
    if (!selectedDecisionId || !sortedItems.some((item) => item.id === selectedDecisionId)) {
      setSelectedDecisionId(sortedItems[0].id);
    }
  }, [selectedDecisionId, sortedItems]);

  useEffect(() => {
    setDecisionReason("");
  }, [selectedItem?.id]);

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
      setDecisionReason("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Decision failed.");
    }
  };

  return (
    <div className="dashboard-page approvals-page approvals-cockpit">
      <section className="approvals-hero" data-tone={hero.tone}>
        <div>
          <span className="eyebrow">Runtime gate</span>
          <h1>{hero.title}</h1>
          <p>{hero.description}</p>
        </div>
        <div className="approvals-hero-rail">
          <span className="approval-hero-pill">{hero.pill}</span>
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => approvalsQuery.refetch()}
            disabled={approvalsQuery.isFetching}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </section>

      <section className="approvals-metric-grid">
        <article className="approval-metric-card tone-warning">
          <Clock3 size={18} />
          <span>Pending holds</span>
          <strong>{pendingCount}</strong>
        </article>
        <article className="approval-metric-card tone-danger">
          <AlertTriangle size={18} />
          <span>Damage stopped</span>
          <strong>{blockedCount}</strong>
        </article>
        <article className="approval-metric-card tone-neutral">
          <LockKeyhole size={18} />
          <span>Evidence-linked</span>
          <strong>{evidenceLinkedCount}</strong>
        </article>
        <article className="approval-metric-card tone-success">
          <FileText size={18} />
          <span>Money-touching</span>
          <strong>{financialCount}</strong>
        </article>
      </section>

      <ApprovalControlContract />

      <section className="approval-cockpit-toolbar" aria-label="Approval filters">
        <div className="filter-bar">
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
        </div>
        <span>{approvalsQuery.isFetching ? "Refreshing held actions..." : "Live approval gate"}</span>
      </section>

      {message ? <div className="notice">{message}</div> : null}

      {approvalsQuery.isLoading ? (
        <div className="empty">Loading runtime approvals...</div>
      ) : approvalsQuery.isError ? (
        <div className="empty error">{approvalsQuery.error.message}</div>
      ) : items.length === 0 ? (
        <section className="approval-empty-state">
          <ShieldAlert size={24} aria-hidden="true" />
          <h2>No held actions in this view.</h2>
          <p>When an agent attempts a high-stakes action, Zroky will hold it here before commit.</p>
          <Link className="btn btn-secondary" href="/policies">
            Review mandates
          </Link>
        </section>
      ) : (
        <section className="approval-cockpit-grid">
          <ApprovalQueue
            items={sortedItems}
            selectedId={selectedItem?.id ?? null}
            onSelect={setSelectedDecisionId}
          />
          <div className="approval-cockpit-detail">
            <ApprovalInspector
              item={selectedItem}
              pack={selectedEvidenceQuery.data}
              packLoading={selectedEvidenceQuery.isLoading}
              packError={selectedEvidenceQuery.error instanceof Error ? selectedEvidenceQuery.error : null}
              reason={decisionReason}
              setReason={setDecisionReason}
              busy={busy}
              onViewEvidence={setEvidenceDecisionId}
              onApprove={(id, reason) => resolve("approve", id, reason)}
              onReject={(id, reason) => resolve("reject", id, reason)}
            />
            <KillSwitchPanel
              armed={killSwitchArmed}
              setArmed={setKillSwitchArmed}
              isPending={killSwitchMutation.isPending}
              onConfirm={async () => {
                setMessage(null);
                try {
                  await killSwitchMutation.mutateAsync(true);
                  setKillSwitchArmed(false);
                  setMessage("Kill switch enabled.");
                } catch (error) {
                  setMessage(error instanceof Error ? error.message : "Kill switch update failed.");
                }
              }}
            />
          </div>
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
