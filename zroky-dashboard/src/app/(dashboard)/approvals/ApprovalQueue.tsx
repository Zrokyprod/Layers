"use client";

import { ArrowRight } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { ApprovalQueueFilter, ApprovalQueueRow } from "@/lib/approval-queue";
import { formatDateTime, timeUntil } from "@/lib/format";

type ApprovalQueueProps = {
  rows: ApprovalQueueRow[];
  selectedId: string | null;
  filter: ApprovalQueueFilter;
  onSelect: (id: string) => void;
};

export function ApprovalQueue({
  filter,
  onSelect,
  rows,
  selectedId,
}: ApprovalQueueProps) {
  const isApprovalQueue = filter === "pending";
  const panelLabel = isApprovalQueue ? "Approval queue" : "Decision history";
  const countLabel = isApprovalQueue
    ? `${rows.length} pending action${rows.length === 1 ? "" : "s"}`
    : `${rows.length} decision${rows.length === 1 ? "" : "s"} shown`;

  return (
    <section className="approval-v2-queue-panel" aria-label={panelLabel}>
      <div className="approval-v2-section-head">
        <div>
          <span className="approval-v2-eyebrow">{panelLabel}</span>
          <strong>{countLabel}</strong>
        </div>
        <span className="approval-v2-live">{isApprovalQueue ? "live" : "history"}</span>
      </div>

      <div className="approval-v2-queue-list">
        {rows.length === 0 ? (
          <div className="approval-v2-empty-state">
            <h2>{isApprovalQueue ? "No pending approvals" : "No decisions in this view"}</h2>
            <p>
              {isApprovalQueue
                ? "When an agent reaches an approval gate, the action will appear here before commit."
                : "Resolved decisions stay in history after approval, rejection, or runtime block."}
            </p>
          </div>
        ) : (
          rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`approval-v2-queue-row approval-v2-tone-${row.priority.tone}${row.id === selectedId ? " is-selected" : ""}`}
              aria-pressed={row.id === selectedId}
              onClick={() => onSelect(row.id)}
            >
              <span className="approval-v2-priority">{row.priority.label}</span>
              <span className="approval-v2-queue-main">
                <span className="approval-v2-queue-kicker">
                  <span className="approval-v2-kind">{row.kind === "guard_only_hold" ? "Guard-only" : "Action intent"}</span>
                  <small>{formatDateTime(row.createdAt)}</small>
                </span>
                <strong>{row.title}</strong>
                <small>
                  {row.agentName} / {row.actionType}
                </small>
                <em>
                  {row.priority.detail} / {row.impactLabel}
                  {row.status === "pending_approval" ? ` / ${timeUntil(row.expiresAt)}` : ""}
                </em>
              </span>
              <span className="approval-v2-queue-side">
                <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
                <small>{row.approvalProgress}</small>
              </span>
              <ArrowRight className="approval-v2-row-arrow" aria-hidden="true" size={15} />
            </button>
          ))
        )}
      </div>
    </section>
  );
}
