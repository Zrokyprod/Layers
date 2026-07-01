"use client";

import { RefreshCw } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { DashboardVerdictHero } from "@/components/dashboard-scaffold";
import type { StatusTone } from "@/lib/action-status";

type ApprovalsVerdictHeroProps = {
  title: string;
  copy: string;
  pill: string;
  tone: StatusTone;
  refreshing: boolean;
  onRefresh: () => void;
};

export function ApprovalsVerdictHero({
  copy,
  onRefresh,
  pill,
  refreshing,
  title,
  tone,
}: ApprovalsVerdictHeroProps) {
  return (
    <DashboardVerdictHero
      eyebrow="Runtime gate"
      title={title}
      copy={copy}
      tone={tone}
      pill={pill}
      updatedLabel="Live approval gate"
      actions={(
        <DashboardButton icon={<RefreshCw />} onClick={onRefresh} disabled={refreshing} variant="soft">
          Refresh
        </DashboardButton>
      )}
    />
  );
}
