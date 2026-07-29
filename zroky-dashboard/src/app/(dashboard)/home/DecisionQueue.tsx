"use client";

import Link from "next/link";
import { ArrowRight, Inbox } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { HomeQueueRow } from "@/lib/home-queue";

export type HomeQueueFilter = "all" | "needs" | "bypass";

type DecisionQueueProps = {
  rows: HomeQueueRow[];
  selectedId: string | null;
  filter?: HomeQueueFilter;
  onFilterChange?: (filter: HomeQueueFilter) => void;
  onSelect?: (row: HomeQueueRow) => void;
  loading: boolean;
  maxRows?: number;
};

function matchesFilter(row: HomeQueueRow, filter: HomeQueueFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "bypass") {
    return row.kind === "bypass" || row.kind === "unmanaged";
  }
  return row.kind !== "bypass" && row.kind !== "unmanaged";
}

function filterLabel(filter: HomeQueueFilter, rows: HomeQueueRow[]): string {
  const count = rows.filter((row) => matchesFilter(row, filter)).length;
  if (filter === "all") return `All ${count}`;
  if (filter === "needs") return `Needs decision ${count}`;
  return `Bypass ${count}`;
}

export function DecisionQueue({
  rows,
  selectedId,
  filter = "all",
  onFilterChange,
  onSelect,
  loading,
  maxRows = 5,
}: DecisionQueueProps) {
  const filteredRows = rows.filter((row) => matchesFilter(row, filter)).slice(0, maxRows);

  return (
    <section className="mc-queue-panel" aria-label="Decision queue">
      <div className="mc-section-head">
        <div>
          <p className="mc-eyebrow">Decision queue</p>
          <h2>What needs attention</h2>
        </div>
        {onFilterChange ? (
          <div className="mc-filter-group" aria-label="Queue filter">
            {(["all", "needs", "bypass"] as const).map((item) => (
              <button
                className={`mc-filter-chip${filter === item ? " is-active" : ""}`}
                type="button"
                key={item}
                onClick={() => onFilterChange(item)}
              >
                {filterLabel(item, rows)}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {loading ? (
        <div className="mc-queue-list" aria-label="Loading decision queue">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="mc-queue-row mc-skeleton-row" key={index}>
              <span className="mc-skeleton mc-skeleton-label" />
              <span className="mc-skeleton mc-skeleton-value" />
              <span className="mc-skeleton mc-skeleton-line" />
            </div>
          ))}
        </div>
      ) : filteredRows.length > 0 ? (
        <div className="mc-queue-list">
          {filteredRows.map((row) => (
            <Link
              className={`mc-queue-row mc-tone-${row.tone}${selectedId === row.id ? " is-selected" : ""}`}
              href={row.href}
              key={row.id}
              onClick={() => onSelect?.(row)}
            >
              <span className="mc-priority">{row.priority}</span>
              <span className="mc-queue-content">
                <span className="mc-queue-title">{row.title}</span>
                <span className="mc-queue-agent">Agent: {row.agentName}</span>
                <span className="mc-queue-meta">
                  {row.reason} / {row.detail}
                </span>
              </span>
              <StatusPill value={row.status} tone={row.tone} />
              <ArrowRight className="mc-row-arrow" aria-hidden="true" size={15} />
            </Link>
          ))}
        </div>
      ) : (
        <div className="mc-empty-state">
          <Inbox aria-hidden="true" size={18} />
          <div>
            <strong>Protected. No action needs your decision.</strong>
            <p>Matched actions and quiet connectors stay available from Actions and Outcomes.</p>
          </div>
        </div>
      )}
    </section>
  );
}
