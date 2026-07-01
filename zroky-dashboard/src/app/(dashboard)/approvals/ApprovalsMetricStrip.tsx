"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  Clock3,
  FileText,
  LockKeyhole,
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
  damageStopped: number;
  moneyTouching: number;
  guardOnly: number;
};

export function ApprovalsMetricStrip({
  damageStopped,
  guardOnly,
  moneyTouching,
  pending,
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
      label: "Damage stopped",
      value: damageStopped,
      helper: "Blocked or rejected actions preserved for audit.",
      tone: damageStopped > 0 ? "danger" : "neutral",
      Icon: AlertTriangle,
    },
    {
      label: "Money-touching",
      value: moneyTouching,
      helper: "Held actions with explicit monetary impact.",
      tone: moneyTouching > 0 ? "warning" : "neutral",
      Icon: FileText,
    },
    {
      label: "Guard-only",
      value: guardOnly,
      helper: "Runtime guard decisions without kernel intent.",
      tone: guardOnly > 0 ? "neutral" : "success",
      Icon: LockKeyhole,
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
