import { RefreshCw } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardMetricStrip } from "@/components/dashboard-scaffold";
import type { EvidenceProofMetric } from "./EvidenceProofStrip";

type EvidenceVerdictHeroProps = {
  badge: string;
  copy: string;
  ctaHref: string;
  ctaLabel: string;
  isRefreshing: boolean;
  metrics: EvidenceProofMetric[];
  onCtaClick?: (href: string) => void;
  onMetricClick?: (href: string) => void;
  onRefresh: () => void;
  summaryDetail: string;
  summaryTitle: string;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
};

export function EvidenceVerdictHero({
  copy,
  ctaHref,
  ctaLabel,
  isRefreshing,
  metrics,
  onCtaClick,
  onMetricClick,
  onRefresh,
  summaryDetail,
  summaryTitle,
  title,
}: EvidenceVerdictHeroProps) {
  return (
    <>
      <section className="ev-operator-hero" aria-label="Evidence command center">
        <div className="ev-operator-hero-top">
          <div>
            <span className="ev-operator-kicker">Evidence</span>
            <h1>{title}</h1>
            <p>{copy}</p>
          </div>
          <div className="ev-operator-summary" aria-label="Evidence summary">
            <strong>{summaryTitle}</strong>
            <span>{summaryDetail}</span>
          </div>
        </div>
        <div className="ev-operator-actions">
          <DashboardButtonLink
            href={ctaHref}
            onClick={(event) => {
              if (onCtaClick && ctaHref.startsWith("/evidence")) {
                event.preventDefault();
                onCtaClick(ctaHref);
              }
            }}
            variant="primary"
          >
            {ctaLabel}
          </DashboardButtonLink>
          <DashboardButton
            aria-label={isRefreshing ? "Refreshing evidence" : "Refresh evidence"}
            icon={<RefreshCw />}
            onClick={onRefresh}
            disabled={isRefreshing}
            size="icon"
            title={isRefreshing ? "Refreshing" : "Refresh"}
            variant="soft"
          />
        </div>
      </section>
      <DashboardMetricStrip
        ariaLabel="Evidence proof summary"
        className="ev-proof-summary-strip"
        columns={metrics.length}
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
