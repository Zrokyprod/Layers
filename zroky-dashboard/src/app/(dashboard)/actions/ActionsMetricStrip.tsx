import type { ComponentType } from "react";
import {
  CheckCircle2,
  Clock3,
  ShieldAlert,
  ShieldCheck,
  UserRoundCheck,
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
  waitingApproval: string;
  awaitingRunner: string;
  verifiedOutcomes: string;
  bypassRisk: string;
  protectedHelper: string;
  approvalHelper: string;
  awaitingRunnerHelper: string;
  outcomeHelper: string;
  bypassHelper: string;
  tones: {
    protectedActions: StatusTone;
    waitingApproval: StatusTone;
    awaitingRunner: StatusTone;
    verifiedOutcomes: StatusTone;
    bypassRisk: StatusTone;
  };
};

export function ActionsMetricStrip({
  approvalHelper,
  awaitingRunner,
  awaitingRunnerHelper,
  bypassHelper,
  bypassRisk,
  outcomeHelper,
  protectedHelper,
  protectedActions,
  tones,
  verifiedOutcomes,
  waitingApproval,
}: ActionsMetricStripProps) {
  const metrics: Metric[] = [
    {
      label: "Protected actions",
      value: protectedActions,
      helper: protectedHelper,
      tone: tones.protectedActions,
      href: "/actions",
      Icon: ShieldCheck,
    },
    {
      label: "Waiting approval",
      value: waitingApproval,
      helper: approvalHelper,
      tone: tones.waitingApproval,
      href: "/approvals",
      Icon: UserRoundCheck,
    },
    {
      label: "Awaiting runner",
      value: awaitingRunner,
      helper: awaitingRunnerHelper,
      tone: tones.awaitingRunner,
      href: "/agents",
      Icon: Clock3,
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
      columns={5}
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
