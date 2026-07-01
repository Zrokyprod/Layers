"use client";

import { RefreshCw } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardVerdictHero } from "@/components/dashboard-scaffold";
import type { StatusTone } from "@/lib/action-status";

type ActionsVerdictHeroProps = {
  title: string;
  copy: string;
  pill: string;
  tone: StatusTone;
  ctaHref: string;
  ctaLabel: string;
  updatedLabel: string;
  onRefresh: () => void;
};

export function ActionsVerdictHero({
  copy,
  ctaHref,
  ctaLabel,
  onRefresh,
  pill,
  title,
  tone,
  updatedLabel,
}: ActionsVerdictHeroProps) {
  return (
    <DashboardVerdictHero
      eyebrow="Actions"
      title={title}
      copy={copy}
      tone={tone}
      pill={pill}
      updatedLabel={updatedLabel}
      actions={
        <>
          <DashboardButton icon={<RefreshCw />} onClick={onRefresh} variant="soft">
            Refresh
          </DashboardButton>
          <DashboardButtonLink href={ctaHref} variant="primary">
            {ctaLabel}
          </DashboardButtonLink>
        </>
      }
    />
  );
}
