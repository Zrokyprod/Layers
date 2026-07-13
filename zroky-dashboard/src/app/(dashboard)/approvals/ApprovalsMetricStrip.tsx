"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
} from "lucide-react";

import { DashboardMetricStrip, type DashboardMetric } from "@/components/dashboard-scaffold";
import type { StatusTone } from "@/lib/action-status";
import { formatCount } from "@/lib/format";

type Metric = {
  label: string;
  value: number;
  helper: string;
  tone: StatusTone;
  Icon: ComponentType<{ size?: number; className?: string }>;
};

type ApprovalsMetricStripProps = {
  pending: number;
  approved: number;
  expiringSoon: number;
  stopped: number;
};

export function ApprovalsMetricStrip({
  approved,
  expiringSoon,
  pending,
  stopped,
}: ApprovalsMetricStripProps) {
  const metrics: Metric[] = [
    {
      label: "Pending holds",
      value: pending,
      helper: "Actions waiting at the approval gate.",
      tone: pending > 0 ? "warning" : "success",
      Icon: Clock3,
    },
    {
      label: "Expiring soon",
      value: expiringSoon,
      helper: "Pending holds near their approval deadline.",
      tone: expiringSoon > 0 ? "warning" : "success",
      Icon: Clock3,
    },
    {
      label: "Approved",
      value: approved,
      helper: "Actions released by a completed human decision.",
      tone: approved > 0 ? "success" : "neutral",
      Icon: CheckCircle2,
    },
    {
      label: "Stopped",
      value: stopped,
      helper: "Blocked, rejected, or expired actions that never ran.",
      tone: stopped > 0 ? "danger" : "neutral",
      Icon: AlertTriangle,
    },
  ];

  return (
    <DashboardMetricStrip
      ariaLabel="Approval control metrics"
      columns={4}
      metrics={metrics.map<DashboardMetric>(({ Icon, helper, label, tone, value }) => ({
        helper,
        icon: <Icon aria-hidden="true" size={16} />,
        label,
        tone,
        value: formatCount(value),
      }))}
    />
  );
}
