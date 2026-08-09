"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ListChecks,
} from "lucide-react";

import type { ApprovalQueueFilter } from "@/lib/approval-queue";
import type { StatusTone } from "@/lib/action-status";
import { formatCount } from "@/lib/format";

type Metric = {
  label: string;
  value: number;
  atLimit?: boolean;
  helper: string;
  tone: StatusTone;
  Icon: ComponentType<{ size?: number; className?: string }>;
  filter: ApprovalQueueFilter;
};

type ApprovalsMetricStripProps = {
  pending: number;
  pendingAtLimit: boolean;
  approved: number;
  expiringSoon: number;
  stopped: number;
  total: number;
  activeFilter: ApprovalQueueFilter;
  onFilterChange: (filter: ApprovalQueueFilter) => void;
};

export function ApprovalsMetricStrip({
  approved,
  activeFilter,
  expiringSoon,
  onFilterChange,
  pending,
  pendingAtLimit,
  stopped,
  total,
}: ApprovalsMetricStripProps) {
  const metrics: Metric[] = [
    {
      label: "Pending",
      value: pending,
      atLimit: pendingAtLimit,
      helper: expiringSoon > 0
        ? `${formatCount(expiringSoon)} ${expiringSoon === 1 ? "hold expires" : "holds expire"} soon.`
        : "Actions waiting at the approval gate.",
      tone: pending > 0 ? "warning" : "success",
      Icon: Clock3,
      filter: "pending",
    },
    {
      label: "Approved",
      value: approved,
      helper: "Actions released by a completed human decision.",
      tone: approved > 0 ? "success" : "neutral",
      Icon: CheckCircle2,
      filter: "approved",
    },
    {
      label: "Stopped",
      value: stopped,
      helper: "Blocked, rejected, or expired actions that never ran.",
      tone: stopped > 0 ? "danger" : "neutral",
      Icon: AlertTriangle,
      filter: "stopped",
    },
    {
      label: "All decisions",
      value: total,
      helper: "Active holds plus the latest resolved decisions returned by the runtime gate.",
      tone: "neutral",
      Icon: ListChecks,
      filter: "all",
    },
  ];

  return (
    <section className="dashboard-metric-strip approval-v2-metric-filters" aria-label="Approval control filters">
      {metrics.map(({ Icon, atLimit, filter, helper, label, tone, value }) => (
        <button
          key={filter}
          type="button"
          className={`dashboard-metric-card approval-v2-metric-filter${activeFilter === filter ? " is-active" : ""}`}
          data-tone={tone}
          aria-label={label}
          aria-pressed={activeFilter === filter}
          onClick={() => onFilterChange(filter)}
        >
          <span className="dashboard-metric-head">
            <span className="dashboard-metric-icon"><Icon aria-hidden="true" size={16} /></span>
            {label}
          </span>
          <strong>{formatCount(value)}{atLimit ? "+" : ""}</strong>
          <p>{helper}</p>
        </button>
      ))}
    </section>
  );
}
