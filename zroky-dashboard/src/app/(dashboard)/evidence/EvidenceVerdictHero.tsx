import { RefreshCw } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardVerdictHero } from "@/components/dashboard-scaffold";

type EvidenceVerdictHeroProps = {
  badge: string;
  copy: string;
  ctaHref: string;
  ctaLabel: string;
  isRefreshing: boolean;
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
  onRefresh,
  title,
  tone,
  updatedLabel,
}: EvidenceVerdictHeroProps) {
  return (
    <DashboardVerdictHero
      ariaLabel="Evidence verdict"
      eyebrow="Evidence"
      title={title}
      copy={copy}
      tone={tone}
      pill={badge}
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
  );
}
