import { RefreshCw } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardMetricStrip, DashboardVerdictHero } from "@/components/dashboard-scaffold";
import type { EvidenceProofMetric } from "./EvidenceProofStrip";

type EvidenceVerdictHeroProps = {
  badge: string;
  copy: string;
  ctaHref: string;
  ctaLabel: string;
  isRefreshing: boolean;
  metrics: EvidenceProofMetric[];
  onMetricClick?: (href: string) => void;
  onRefresh: () => void;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
  updatedLabel: string;
};

export function EvidenceVerdictHero({
  badge,
  copy,
  ctaHref,
  ctaLabel,
  isRefreshing,
  metrics,
  onMetricClick,
  onRefresh,
  title,
  tone,
  updatedLabel,
}: EvidenceVerdictHeroProps) {
  return (
    <>
      <DashboardVerdictHero
        ariaLabel="Evidence command center"
        className="ev-command-hero"
        copy={copy}
        eyebrow="Evidence"
        pill={badge}
        title={title}
        tone={tone}
        updatedLabel={updatedLabel}
        actions={(
          <>
            <DashboardButton icon={<RefreshCw />} onClick={onRefresh} disabled={isRefreshing} variant="soft">
              {isRefreshing ? "Refreshing" : "Refresh"}
            </DashboardButton>
            <DashboardButtonLink href={ctaHref} variant="primary">
              {ctaLabel}
            </DashboardButtonLink>
          </>
        )}
      />
      <DashboardMetricStrip
        ariaLabel="Evidence proof summary"
        className="ev-proof-summary-strip"
        columns={4}
        metrics={metrics.map((metric) => ({
          helper: metric.detail,
          href: metric.href,
          label: metric.label,
          tone: metric.tone,
          value: metric.value,
        }))}
        onMetricClick={onMetricClick ? (metric) => onMetricClick(metric.href ?? "/evidence") : undefined}
      />
    </>
  );
}
