"use client";

import { ArrowRight } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import {
  type ActionLifecycleFilter,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";
import { formatDateTime } from "@/lib/format";

const FILTERS: Array<{ id: ActionLifecycleFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "held", label: "Held" },
  { id: "executing", label: "Executing" },
  { id: "mismatched", label: "Mismatched" },
  { id: "not_verified", label: "Not verified" },
];

type ActionLifecycleQueueProps = {
  rows: ActionLifecycleRow[];
  selectedId: string | null;
  filter: ActionLifecycleFilter;
  onFilterChange: (filter: ActionLifecycleFilter) => void;
  onSelect: (id: string) => void;
};

export function ActionLifecycleQueue({
  filter,
  onFilterChange,
  onSelect,
  rows,
  selectedId,
}: ActionLifecycleQueueProps) {
  return (
    <section className="al-queue-panel" aria-label="Action lifecycle queue">
      <div className="al-section-head">
        <div>
          <span className="al-eyebrow">Lifecycle cockpit</span>
          <strong>{rows.length} action{rows.length === 1 ? "" : "s"} shown</strong>
        </div>
        <span className="al-queue-live">live</span>
      </div>

      <div className="al-filter-group" aria-label="Lifecycle filters">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`al-filter-chip${filter === item.id ? " is-active" : ""}`}
            onClick={() => onFilterChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="al-queue-list">
        {rows.length === 0 ? (
          <div className="al-empty-state">
            <h2>No actions match this filter</h2>
            <p>Protected action lifecycle rows will appear as agents route work through Zroky.</p>
          </div>
        ) : (
          rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`al-queue-row al-tone-${row.stage.tone}${row.id === selectedId ? " is-selected" : ""}`}
              onClick={() => onSelect(row.id)}
            >
              <span className="al-queue-content">
                <span className="al-queue-kicker">
                  <span className="al-stage-marker" data-tone={row.stage.tone}>
                    <span className="al-stage-dot" aria-hidden="true" />
                    {row.kind === "orphan_decision" ? "Guard-only" : row.stage.label}
                  </span>
                  <small>{formatDateTime(row.updatedAt ?? row.createdAt)}</small>
                </span>
                <strong>{row.title}</strong>
                <small className="al-queue-meta">
                  {row.agentName} / {row.actionType}
                </small>
                <em>{row.stage.detail}</em>
              </span>
              <span className="al-row-pills">
                <StatusPill value={row.proofStatus} label={row.proofLabel} tone={row.proofTone} />
                <StatusPill value={row.receiptStatus} label={row.receiptLabel} tone={row.receiptTone} />
              </span>
              <ArrowRight className="al-row-arrow" aria-hidden="true" size={15} />
            </button>
          ))
        )}
      </div>
    </section>
  );
}
