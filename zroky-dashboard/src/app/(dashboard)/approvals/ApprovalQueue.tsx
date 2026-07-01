"use client";

import { ArrowRight } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { RuntimePolicyDecisionStatus } from "@/lib/api";
import type { ApprovalQueueRow } from "@/lib/approval-queue";
import { formatDateTime, timeUntil } from "@/lib/format";

export type ApprovalFilter = RuntimePolicyDecisionStatus | "all";

const FILTERS: Array<{ id: ApprovalFilter; label: string }> = [
  { id: "pending_approval", label: "Pending" },
  { id: "blocked", label: "Blocked" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "all", label: "All" },
];

type ApprovalQueueProps = {
  rows: ApprovalQueueRow[];
  selectedId: string | null;
  filter: ApprovalFilter;
  onFilterChange: (filter: ApprovalFilter) => void;
  onSelect: (id: string) => void;
};

export function ApprovalQueue({
  filter,
  onFilterChange,
  onSelect,
  rows,
  selectedId,
}: ApprovalQueueProps) {
  return (
    <section className="approval-v2-queue-panel" aria-label="Held action queue">
      <div className="approval-v2-section-head">
        <div>
          <span className="approval-v2-eyebrow">Held action queue</span>
          <strong>{rows.length} action{rows.length === 1 ? "" : "s"} shown</strong>
        </div>
        <span className="approval-v2-live">live</span>
      </div>

      <div className="approval-v2-filter-group" aria-label="Approval filters">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`approval-v2-filter-chip${filter === item.id ? " is-active" : ""}`}
            onClick={() => onFilterChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="approval-v2-queue-list">
        {rows.length === 0 ? (
          <div className="approval-v2-empty-state">
            <h2>No held actions in this view</h2>
            <p>When an agent reaches an approval gate, the action hold will appear here.</p>
          </div>
        ) : (
          rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`approval-v2-queue-row approval-v2-tone-${row.priority.tone}${row.id === selectedId ? " is-selected" : ""}`}
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
                  {row.priority.detail} / {row.impactLabel} / {timeUntil(row.expiresAt)}
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
