"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Clock3,
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
  useRuntimePolicyApprovals,
  useSetRuntimePolicyKillSwitch,
} from "@/lib/hooks";
import type {
  RuntimePolicyDecisionResponse,
  RuntimePolicyDecisionStatus,
} from "@/lib/api";

type Filter = RuntimePolicyDecisionStatus | "all";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "pending_approval", label: "Pending" },
  { id: "blocked", label: "Blocked" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "all", label: "All" },
];

function compactJson(value: Record<string, unknown>): string {
  const entries = Object.entries(value).filter(([, item]) => item != null && item !== "");
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

function queueTone(status: string): "danger" | "warning" | "success" | "neutral" {
  if (status === "blocked" || status === "rejected") return "danger";
  if (status === "pending_approval") return "warning";
  if (status === "approved" || status === "allowed") return "success";
  return "neutral";
}

function DecisionCard({
  item,
  busy,
  onApprove,
  onReject,
}: {
  item: RuntimePolicyDecisionResponse;
  busy: boolean;
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
        <StatusPill value={item.status} />
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
  const approvalsQuery = useRuntimePolicyApprovals(filter);
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
              onApprove={(id, reason) => resolve("approve", id, reason)}
              onReject={(id, reason) => resolve("reject", id, reason)}
            />
          ))}
        </section>
      )}
    </div>
  );
}
