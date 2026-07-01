import type { ComponentType } from "react";
import {
  CheckCircle2,
  Gauge,
  ReceiptText,
  ShieldAlert,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { DashboardMetricStrip, type DashboardMetric } from "@/components/dashboard-scaffold";
import type { StatusTone } from "@/lib/action-status";

type Metric = {
  label: string;
  value: string;
  helper: string;
  tone: StatusTone;
  href: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
};

type ActionsMetricStripProps = {
  protectedActions: string;
  policyChecks: string;
  runnerExecutions: string;
  receipts: string;
  verifiedOutcomes: string;
  bypassRisk: string;
  policyHelper: string;
  runnerHelper: string;
  receiptHelper: string;
  outcomeHelper: string;
  bypassHelper: string;
  tones: {
    protectedActions: StatusTone;
    policyChecks: StatusTone;
    runnerExecutions: StatusTone;
    receipts: StatusTone;
    verifiedOutcomes: StatusTone;
    bypassRisk: StatusTone;
  };
};

export function ActionsMetricStrip({
  bypassHelper,
  bypassRisk,
  outcomeHelper,
  policyChecks,
  policyHelper,
  protectedActions,
  receiptHelper,
  receipts,
  runnerExecutions,
  runnerHelper,
  tones,
  verifiedOutcomes,
}: ActionsMetricStripProps) {
  const metrics: Metric[] = [
    {
      label: "Protected actions",
      value: protectedActions,
      helper: "Action intents routed through the kernel.",
      tone: tones.protectedActions,
      href: "/actions",
      Icon: ShieldCheck,
    },
    {
      label: "Policy checks",
      value: policyChecks,
      helper: policyHelper,
      tone: tones.policyChecks,
      href: "/approvals",
      Icon: Gauge,
    },
    {
      label: "Runner executions",
      value: runnerExecutions,
      helper: runnerHelper,
      tone: tones.runnerExecutions,
      href: "/agents",
      Icon: Workflow,
    },
    {
      label: "Receipts",
      value: receipts,
      helper: receiptHelper,
      tone: tones.receipts,
      href: "/evidence",
      Icon: ReceiptText,
    },
    {
      label: "Verified outcomes",
      value: verifiedOutcomes,
      helper: outcomeHelper,
      tone: tones.verifiedOutcomes,
      href: "/outcomes",
      Icon: CheckCircle2,
    },
    {
      label: "Bypass risk",
      value: bypassRisk,
      helper: bypassHelper,
      tone: tones.bypassRisk,
      href: "/outcomes",
      Icon: ShieldAlert,
    },
  ];

  return (
    <DashboardMetricStrip
      ariaLabel="Action lifecycle metrics"
      columns={6}
      metrics={metrics.map<DashboardMetric>(({ Icon, helper, href, label, tone, value }) => ({
        helper,
        href,
        icon: <Icon aria-hidden="true" size={16} />,
        label,
        tone,
        value,
      }))}
    />
  );
}
